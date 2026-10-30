from concurrent.futures import ThreadPoolExecutor
from collections import deque
import threading
from uuid import uuid4

import store


def init():
    with store.connect() as conn:
        conn.execute("""
            CREATE SCHEMA IF NOT EXISTS admission_lab;
            SET LOCAL search_path=admission_lab;
            CREATE TABLE IF NOT EXISTS tenant_work_budgets(
              tenant_id TEXT PRIMARY KEY, pending_units INTEGER NOT NULL,
              pending_limit INTEGER NOT NULL, CHECK(pending_units BETWEEN 0 AND pending_limit));
            CREATE TABLE IF NOT EXISTS jobs(
              id UUID PRIMARY KEY, tenant_id TEXT REFERENCES tenant_work_budgets(tenant_id),
              status TEXT NOT NULL, reserved_units INTEGER NOT NULL CHECK(reserved_units>0),
              reservation_released_at TIMESTAMPTZ, idempotency_key TEXT UNIQUE NOT NULL);
            CREATE TABLE IF NOT EXISTS work_admissions(
              id UUID PRIMARY KEY, tenant_id TEXT NOT NULL, job_id UUID UNIQUE REFERENCES jobs(id),
              decision TEXT NOT NULL, reserved_units INTEGER NOT NULL, decided_at TIMESTAMPTZ NOT NULL);
            CREATE TABLE IF NOT EXISTS outbox(
              id UUID PRIMARY KEY, aggregate_id UUID REFERENCES jobs(id),
              event_type TEXT NOT NULL, payload JSONB NOT NULL);
            """)


def admit(tenant_id, job_id, units, barrier):
    with store.connect() as conn:
        conn.execute("SET LOCAL search_path=admission_lab")
        barrier.wait(timeout=5)
        return conn.execute("""
            WITH reserved AS (
              UPDATE tenant_work_budgets SET pending_units=pending_units+%(units)s
              WHERE tenant_id=%(tenant)s AND pending_units+%(units)s<=pending_limit RETURNING tenant_id
            ), created_job AS (
              INSERT INTO jobs(id,tenant_id,status,reserved_units,idempotency_key)
              SELECT %(job)s,tenant_id,'PENDING',%(units)s,%(key)s FROM reserved RETURNING *
            ), evidence AS (
              INSERT INTO work_admissions SELECT %(admission)s,tenant_id,id,'ACCEPTED',reserved_units,now() FROM created_job
            ), delivery AS (
              INSERT INTO outbox SELECT %(message)s,id,'job.ready',jsonb_build_object('job_id',id) FROM created_job
            ) SELECT id FROM created_job
            """,{'units':units,'tenant':tenant_id,'job':job_id,'key':str(job_id),'admission':uuid4(),'message':uuid4()}).fetchone()


def cancel_and_release(tenant_id,job_id):
    with store.connect() as conn:
        conn.execute("SET LOCAL search_path=admission_lab")
        return conn.execute("""
            WITH cancelled AS (
              UPDATE jobs SET status='CANCELLED',reservation_released_at=now()
              WHERE id=%s AND tenant_id=%s AND status='PENDING' AND reservation_released_at IS NULL
              RETURNING tenant_id,reserved_units
            ) UPDATE tenant_work_budgets b SET pending_units=pending_units-c.reserved_units
              FROM cancelled c WHERE b.tenant_id=c.tenant_id RETURNING pending_units
            """,(job_id,tenant_id)).fetchone()


def test_final_units_and_duplicate_release():
    init()
    tenant = str(uuid4())
    with store.connect() as conn:
        conn.execute("INSERT INTO admission_lab.tenant_work_budgets VALUES (%s,90,100)",(tenant,))
    barrier = threading.Barrier(2)
    def contender(_): return admit(tenant,uuid4(),10,barrier)
    with ThreadPoolExecutor(2) as pool:
        winners = [r for r in pool.map(contender,range(2)) if r]
    assert len(winners) == 1
    with store.connect() as conn:
        assert conn.execute("SELECT pending_units FROM admission_lab.tenant_work_budgets WHERE tenant_id=%s",(tenant,)).fetchone()['pending_units'] == 100
        for table in ('jobs','work_admissions'):
            # Static identifiers selected by this test, never caller input.
            assert conn.execute(f"SELECT count(*) AS n FROM admission_lab.{table} WHERE tenant_id=%s",(tenant,)).fetchone()['n'] == 1
        assert conn.execute("SELECT count(*) AS n FROM admission_lab.outbox WHERE aggregate_id=%s",(winners[0]['id'],)).fetchone()['n'] == 1
    assert cancel_and_release(tenant,winners[0]['id'])['pending_units'] == 90
    assert cancel_and_release(tenant,winners[0]['id']) is None


def test_round_robin_serves_cold_tenant():
    # Selection model only. Distributed dispatch also needs durable leases.
    queues = {'A':deque(range(1000)), 'B':deque([42])}
    turns = deque(queues)
    started = []
    while turns and len(started)<4:
        tenant = turns.popleft()
        started.append((tenant,queues[tenant].popleft()))
        if queues[tenant]: turns.append(tenant)
    assert [tenant for tenant,_ in started] == ['A','B','A','A']
