"""Local payment effect + saved response share one fenced transaction."""
import hashlib
import json
import os
from dataclasses import dataclass
from psycopg.types.json import Jsonb
from advanced_db import connect

class Conflict(Exception): pass
class Busy(Exception): pass
class StaleOwner(Exception): pass

@dataclass(frozen=True)
class Claim:
    id: int
    generation: int
    replay: tuple | None = None


def claim(tenant, endpoint, key, payload, *, lease_seconds=30):
    if not key or len(key)>200 or lease_seconds <= 0:
        raise ValueError('Invalid key/lease')
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    with connect() as db:
        inserted = db.execute('''INSERT INTO advanced_idempotency
            (tenant,endpoint,request_key,request_hash,lease_until)
            VALUES(%s,%s,%s,%s,clock_timestamp()+(%s * interval '1 second'))
            ON CONFLICT DO NOTHING RETURNING id,generation''',
            (tenant,endpoint,key,digest,lease_seconds)).fetchone()
        if inserted:
            return Claim(**inserted)
        row = db.execute('''SELECT *, lease_until>clock_timestamp() AS live
            FROM advanced_idempotency WHERE tenant=%s AND endpoint=%s AND request_key=%s FOR UPDATE''',
            (tenant,endpoint,key)).fetchone()
        if row['request_hash'] != digest:
            raise Conflict('Key has different meaning')
        if row['status']=='DONE':
            return Claim(row['id'],row['generation'],(row['response_status'],row['response_body']))
        if row['live']:
            raise Busy('Operation still pending')
        generation = db.execute('''UPDATE advanced_idempotency SET generation=generation+1,
            lease_until=clock_timestamp()+(%s * interval '1 second') WHERE id=%s RETURNING generation''',
            (lease_seconds,row['id'])).fetchone()['generation']
        return Claim(row['id'],generation)


def complete_local(owner, amount, *, crash_after_effect=False):
    if owner.replay:
        return owner.replay
    with connect() as db:
        row = db.execute('''SELECT *, lease_until>clock_timestamp() AS live
            FROM advanced_idempotency WHERE id=%s FOR UPDATE''', (owner.id,)).fetchone()
        if row['generation'] != owner.generation or row['status']!='PENDING' or not row['live']:
            raise StaleOwner('Lease generation no longer owns completion')
        expected = hashlib.sha256(json.dumps({'amount': amount}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if row['request_hash'] != expected:
            raise Conflict('Effect differs from claimed payment payload')
        # SQL effect is in THIS transaction. Arbitrary HTTP/email callbacks are forbidden here.
        db.execute('INSERT INTO advanced_payments(operation_id,amount) VALUES(%s,%s)', (owner.id,amount))
        if crash_after_effect:
            os._exit(17)  # Integration test: server rolls back the uncommitted effect.
        body = {'payment_id': owner.id, 'amount': amount}
        db.execute('''UPDATE advanced_idempotency SET status='DONE',response_status=201,
            response_body=%s WHERE id=%s''', (Jsonb(body),owner.id))
        return 201, body


def provider_key(tenant, endpoint, client_key):
    # Generation must NOT be included: a replacement owner is the same remote operation.
    meaning = json.dumps(['payments-v1',tenant,endpoint,client_key],separators=(',', ':'))
    return 'payment-' + hashlib.sha256(meaning.encode()).hexdigest()
