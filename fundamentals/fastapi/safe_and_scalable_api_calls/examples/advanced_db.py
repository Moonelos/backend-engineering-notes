"""Shared PostgreSQL fixture, explicitly named laboratory tables."""
import os
import psycopg
from psycopg.rows import dict_row

DSN = os.environ.get('ADVANCED_DATABASE_URL', 'postgresql://advanced:local-only@localhost:57432/advanced')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS advanced_idempotency (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 tenant text NOT NULL, endpoint text NOT NULL, request_key text NOT NULL, request_hash text NOT NULL,
 generation integer NOT NULL DEFAULT 1, lease_until timestamptz NOT NULL,
 status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DONE')),
 response_status integer, response_body jsonb,
 UNIQUE(tenant,endpoint,request_key));
CREATE TABLE IF NOT EXISTS advanced_payments (
 operation_id bigint PRIMARY KEY REFERENCES advanced_idempotency(id), amount integer NOT NULL CHECK(amount>0));
CREATE TABLE IF NOT EXISTS advanced_budget_windows (
 tenant text NOT NULL, window_date date NOT NULL, spent bigint NOT NULL DEFAULT 0,
 reserved bigint NOT NULL DEFAULT 0, ceiling bigint NOT NULL,
 PRIMARY KEY(tenant,window_date), CHECK(spent>=0 AND reserved>=0 AND spent+reserved<=ceiling));
CREATE TABLE IF NOT EXISTS advanced_budget_ops (
 operation_id text PRIMARY KEY, tenant text NOT NULL, window_date date NOT NULL,
 input_cap integer NOT NULL, output_cap integer NOT NULL, max_attempts integer NOT NULL,
 reservation bigint NOT NULL, state text NOT NULL DEFAULT 'RESERVED', actual bigint,
 FOREIGN KEY(tenant,window_date) REFERENCES advanced_budget_windows(tenant,window_date),
 CHECK(state IN ('RESERVED','UNKNOWN','SETTLED')));
CREATE TABLE IF NOT EXISTS advanced_budget_attempts (
 operation_id text REFERENCES advanced_budget_ops(operation_id), attempt integer NOT NULL,
 state text NOT NULL DEFAULT 'UNKNOWN', usage bigint,
 PRIMARY KEY(operation_id,attempt), CHECK(state IN ('UNKNOWN','KNOWN')));
'''

def connect():
    return psycopg.connect(DSN, row_factory=dict_row)

def initialize():
    with connect() as db:
        db.execute(SCHEMA)

if __name__ == '__main__':
    initialize()
    print('Advanced laboratory schema ready')
