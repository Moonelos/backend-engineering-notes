"""Durable hard token reservation; original window survives retries and settlement."""
from datetime import datetime, timezone
from advanced_db import connect

class BudgetDenied(Exception): pass
class UsageConflict(Exception): pass


def reserve(operation_id, tenant, *, input_cap, output_cap, max_attempts, ceiling, window=None):
    if min(input_cap, output_cap, max_attempts, ceiling)<1:
        raise ValueError('Positive caps required')
    window = window or datetime.now(timezone.utc).date()
    cap = (input_cap+output_cap)*max_attempts
    with connect() as db:
        # Lock the operation before its window; repeat calls verify the original meaning.
        # An advisory transaction lock serializes creation even before the row exists.
        db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(operation_id,))
        old = db.execute('SELECT * FROM advanced_budget_ops WHERE operation_id=%s FOR UPDATE',
                         (operation_id,)).fetchone()
        if old:
            if (old['tenant'],old['input_cap'],old['output_cap'],old['max_attempts']) != \
                    (tenant,input_cap,output_cap,max_attempts):
                raise UsageConflict('Operation reservation changed')
            return old  # Original day; do not move it to today's bucket.
        db.execute('''INSERT INTO advanced_budget_windows(tenant,window_date,ceiling)
            VALUES(%s,%s,%s) ON CONFLICT DO NOTHING''',(tenant,window,ceiling))
        row = db.execute('''UPDATE advanced_budget_windows SET reserved=reserved+%s
            WHERE tenant=%s AND window_date=%s AND spent+reserved+%s<=ceiling RETURNING *''',
            (cap,tenant,window,cap)).fetchone()
        if not row:
            raise BudgetDenied('Hard token budget exhausted')
        return db.execute('''INSERT INTO advanced_budget_ops
            (operation_id,tenant,window_date,input_cap,output_cap,max_attempts,reservation)
            VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
            (operation_id,tenant,window,input_cap,output_cap,max_attempts,cap)).fetchone()


def start_attempt(operation_id, attempt, input_tokens):
    with connect() as db:
        op = db.execute('SELECT * FROM advanced_budget_ops WHERE operation_id=%s FOR UPDATE',
                        (operation_id,)).fetchone()
        if op['state']!='RESERVED' or not 0<=attempt<op['max_attempts'] or not 0<=input_tokens<=op['input_cap']:
            raise BudgetDenied('Attempt exceeds reserved contract')
        # Persist UNKNOWN before dispatch. Crash after this commit cannot imply zero cost.
        db.execute('INSERT INTO advanced_budget_attempts(operation_id,attempt) VALUES(%s,%s)',
                   (operation_id,attempt))
        return {'max_output_tokens':op['output_cap']}  # Must be enforced by the provider adapter.


def record_usage(operation_id, attempt, usage):
    if usage is None:
        return  # No usage evidence; UNKNOWN remains durable.
    with connect() as db:
        op = db.execute('SELECT * FROM advanced_budget_ops WHERE operation_id=%s FOR UPDATE',
                        (operation_id,)).fetchone()
        row = db.execute('SELECT * FROM advanced_budget_attempts WHERE operation_id=%s AND attempt=%s FOR UPDATE',
                         (operation_id,attempt)).fetchone()
        if row is None:
            raise UsageConflict('Attempt was never reserved')
        if row['state']=='KNOWN':
            if row['usage']!=usage:
                raise UsageConflict('Conflicting usage evidence')
            return
        if op['state']=='SETTLED' or not 0<=usage<=op['input_cap']+op['output_cap']:
            raise UsageConflict('Usage exceeds enforced reservation; investigate contract')
        db.execute('''UPDATE advanced_budget_attempts SET state='KNOWN',usage=%s
            WHERE operation_id=%s AND attempt=%s''',(usage,operation_id,attempt))


def settle(operation_id):
    with connect() as db:
        op = db.execute('SELECT * FROM advanced_budget_ops WHERE operation_id=%s FOR UPDATE',
                        (operation_id,)).fetchone()
        if op['state']=='SETTLED':
            return op['actual']
        evidence = db.execute('''SELECT count(*) FILTER(WHERE state='UNKNOWN') AS unknown,
            coalesce(sum(usage),0) AS actual FROM advanced_budget_attempts WHERE operation_id=%s''',
            (operation_id,)).fetchone()
        if evidence['unknown']:
            db.execute("UPDATE advanced_budget_ops SET state='UNKNOWN' WHERE operation_id=%s",(operation_id,))
            return None
        actual = int(evidence['actual'])
        db.execute('''UPDATE advanced_budget_windows SET reserved=reserved-%s,spent=spent+%s
            WHERE tenant=%s AND window_date=%s''',
            (op['reservation'],actual,op['tenant'],op['window_date']))
        db.execute("UPDATE advanced_budget_ops SET state='SETTLED',actual=%s WHERE operation_id=%s",
                   (actual,operation_id))
        return actual
