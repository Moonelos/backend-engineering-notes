import asyncio
import json
import os
import time
from pathlib import Path

import httpx
import pytest

os.environ.setdefault('BILLING_WEBHOOK_SECRETS', 'local-test-only-' + 'x' * 32)
from .app import app, SIGNING_SECRETS
from .webhook_security import sign_webhook
from .worker import process_one


def test_signed_admission_duplicate_and_transaction_recovery():
    if not os.environ.get('DATABASE_URL'):
        pytest.skip('Set DATABASE_URL to the dedicated webhook_lab PostgreSQL database')
    async def scenario():
        async with app.router.lifespan_context(app):
            pool = app.state.pool
            assert await pool.fetchval('select current_database()') == 'webhook_lab'
            # Destructive setup is confined to the explicitly named disposable lab database.
            await pool.execute('DROP TABLE IF EXISTS webhook_inbox, processed_provider_events, invoices')
            await pool.execute(Path(__file__).with_name('schema.sql').read_text())
            body = json.dumps({'id':'evt_1','type':'invoice.paid','schema_version':1,
                'occurred_at':'2026-10-30T10:00:00Z','producer':'billing',
                'data':{'invoice_id':'inv_123'}}, separators=(',', ':')).encode()
            timestamp = int(time.time())
            headers = {'webhook-id':'evt_1','webhook-timestamp':str(timestamp),
                'webhook-signature':sign_webhook(body=body, message_id='evt_1',
                    timestamp=timestamp, secrets=SIGNING_SECRETS)}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://lab') as client:
                assert (await client.post('/webhooks/billing',content=body,headers=headers)).status_code == 204
                assert (await client.post('/webhooks/billing',content=body+b' ',headers=headers)).status_code == 401
                responses = await asyncio.gather(*(client.post('/webhooks/billing',content=body,headers=headers) for _ in range(2)))
                assert [r.status_code for r in responses] == [204,204]
            assert await pool.fetchval('SELECT count(*) FROM webhook_inbox') == 1
            assert await pool.fetchval('SELECT effect_count FROM invoices') == 0
            with pytest.raises(RuntimeError, match='Injected crash'):
                await process_one(pool, crash_after_effect=True)
            assert await pool.fetchval('SELECT count(*) FROM processed_provider_events') == 0
            assert await pool.fetchval('SELECT effect_count FROM invoices') == 0
            assert await process_one(pool)
            # Replay the worker state while keeping the durable effect guard.
            await pool.execute("UPDATE webhook_inbox SET state='received'")
            assert await process_one(pool)
            assert await pool.fetchval('SELECT effect_count FROM invoices') == 1
            assert await pool.fetchval("SELECT count(*) FROM webhook_inbox WHERE state='processed'") == 1
            async def admit(client, event_id, invoice_id):
                event = json.loads(body)
                event['id'] = event_id
                event['data']['invoice_id'] = invoice_id
                encoded = json.dumps(event, separators=(',', ':')).encode()
                signed_headers = {'webhook-id': event_id, 'webhook-timestamp': str(timestamp),
                    'webhook-signature': sign_webhook(body=encoded, message_id=event_id,
                        timestamp=timestamp, secrets=SIGNING_SECRETS)}
                assert (await client.post('/webhooks/billing', content=encoded,
                                          headers=signed_headers)).status_code == 204
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://lab') as client:
                await admit(client, 'evt_2_poison', 'inv_other_account')
                await admit(client, 'evt_3_valid', 'inv_123')
                assert await process_one(pool)
                assert await pool.fetchval("SELECT state FROM webhook_inbox WHERE event_id='evt_2_poison'") == 'quarantined'
                assert await process_one(pool)
                assert await pool.fetchval('SELECT effect_count FROM invoices') == 2
                assert not await process_one(pool)
                await pool.execute("DELETE FROM invoices WHERE id='inv_123'")
                await admit(client, 'evt_4_missing', 'inv_123')
                assert await process_one(pool)
                assert await pool.fetchval("SELECT last_error_code FROM webhook_inbox WHERE event_id='evt_4_missing'") == 'INVOICE_NOT_FOUND'
                assert await pool.fetchval("SELECT count(*) FROM processed_provider_events WHERE event_id='evt_4_missing'") == 0
    asyncio.run(scenario())
