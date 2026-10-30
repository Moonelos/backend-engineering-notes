"""Short local effects share the inbox transaction; no network I/O under this row lock."""
import json

async def process_one(pool, *, crash_after_effect=False):
    async with pool.acquire() as connection:
        async with connection.transaction():
            row = await connection.fetchrow('''
                SELECT producer, event_id, payload FROM webhook_inbox
                WHERE state='received' ORDER BY received_at, event_id
                FOR UPDATE SKIP LOCKED LIMIT 1
            ''')
            if row is None:
                return False
            event = json.loads(row['payload'])
            async def quarantine(code):
                await connection.execute("""UPDATE webhook_inbox SET state='quarantined',
                    last_error_code=$3 WHERE producer=$1 AND event_id=$2""",
                    row['producer'], row['event_id'], code)

            if event['type'] != 'invoice.paid' or event['schema_version'] != 1:
                await quarantine('UNSUPPORTED_EVENT')
                return True
            invoice_id = event['data'].get('invoice_id')
            # This lab's secret authorizes one billing account containing inv_123.
            # Multi-account production schemas include account/tenant in every key/predicate.
            if invoice_id != 'inv_123':
                await quarantine('UNAUTHORIZED_INVOICE')
                return True
            invoice = await connection.fetchval('SELECT id FROM invoices WHERE id=$1 FOR UPDATE', invoice_id)
            if invoice is None:
                await quarantine('INVOICE_NOT_FOUND')
                return True
            admitted = await connection.fetchval('''
                INSERT INTO processed_provider_events(producer, event_id)
                VALUES ($1,$2) ON CONFLICT DO NOTHING RETURNING event_id
            ''', row['producer'], row['event_id'])
            if admitted is not None:
                updated = await connection.fetchval("""UPDATE invoices SET status='paid', effect_count=effect_count+1
                    WHERE id=$1 RETURNING id""", invoice_id)
                assert updated == invoice_id
            if crash_after_effect:
                raise RuntimeError('Injected crash before transaction commit')
            await connection.execute("""UPDATE webhook_inbox SET state='processed', processed_at=now()
                WHERE producer=$1 AND event_id=$2""", row['producer'], row['event_id'])
            return True
