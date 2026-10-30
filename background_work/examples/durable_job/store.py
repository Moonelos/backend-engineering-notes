"""Small synchronous DB adapter; every operation owns and closes its transaction."""
import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

TENANT = UUID("00000000-0000-0000-0000-000000000042")


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def initialize():
    with connect() as conn:
        conn.execute(Path(__file__).with_name("schema.sql").read_text())


def submit(key: str, content: str):
    digest = hashlib.sha256(content.encode()).hexdigest()
    with connect() as conn:
        conn.execute("INSERT INTO document_inputs VALUES (%s,%s) ON CONFLICT DO NOTHING", (digest, content))
        row = conn.execute("""
            INSERT INTO document_parse_jobs(id,tenant_id,request_key,request_hash,input_ref,status)
            VALUES (%s,%s,%s,%s,%s,'PENDING')
            ON CONFLICT (tenant_id,request_key) DO UPDATE SET request_key=EXCLUDED.request_key
            RETURNING *, (xmax=0) AS inserted
            """, (uuid4(), TENANT, key, digest, digest)).fetchone()
        if row["request_hash"] != digest:
            raise ValueError("idempotency key reused with different input")
        if row.pop("inserted"):
            conn.execute("INSERT INTO job_outbox(id,job_id) VALUES (%s,%s)", (uuid4(), row["id"]))
        return row


def get_job(job_id):
    with connect() as conn:
        return conn.execute("""
            SELECT j.*, r.words FROM document_parse_jobs j
            LEFT JOIN document_parse_results r ON r.job_id=j.id
            WHERE j.id=%s AND j.tenant_id=%s
            """, (job_id, TENANT)).fetchone()


def recover(batch_size=100):
    # A dead worker is repaired only after its lease ends. An exhausted/aged job
    # becomes terminal instead of being left PENDING without a possible claim.
    if not isinstance(batch_size, int) or not 1 <= batch_size <= 1000:
        raise ValueError("recovery batch must be between 1 and 1000")
    with connect() as conn:
        rows = conn.execute("""
            WITH expired AS (
              SELECT id FROM document_parse_jobs
              WHERE status='RUNNING' AND lease_expires_at<=now()
              ORDER BY lease_expires_at,id LIMIT %s FOR UPDATE SKIP LOCKED
            ) UPDATE document_parse_jobs j SET
              status=CASE WHEN attempt>=max_attempts OR retry_deadline<=now() THEN 'FAILED' ELSE 'PENDING' END,
              finished_at=CASE WHEN attempt>=max_attempts OR retry_deadline<=now() THEN now() ELSE NULL END,
              attempt_token=NULL, lease_expires_at=NULL, next_attempt_at=now(),
              last_error_class='WorkerLost'
            FROM expired WHERE j.id=expired.id RETURNING j.id,j.status
            """, (batch_size,)).fetchall()
        for row in rows:
            if row["status"] == "PENDING":
                conn.execute("INSERT INTO job_outbox(id,job_id) VALUES (%s,%s)", (uuid4(),row["id"]))
        conn.execute("""
            WITH exhausted AS (
              SELECT id FROM document_parse_jobs
              WHERE status='PENDING' AND (attempt>=max_attempts OR retry_deadline<=now())
              ORDER BY retry_deadline,id LIMIT %s FOR UPDATE SKIP LOCKED
            ) UPDATE document_parse_jobs j SET status='FAILED', finished_at=now(), last_error_class='BudgetExhausted'
            FROM exhausted WHERE j.id=exhausted.id
            """, (batch_size,))
        return len(rows)


def claim(job_id=None, lease_seconds=90):
    with connect() as conn:
        return conn.execute("""
            WITH candidate AS (
              SELECT id FROM document_parse_jobs
              WHERE status='PENDING' AND next_attempt_at<=now()
                AND attempt<max_attempts AND retry_deadline>now()
                AND (%s::uuid IS NULL OR id=%s::uuid)
              ORDER BY next_attempt_at,created_at FOR UPDATE SKIP LOCKED LIMIT 1
            ) UPDATE document_parse_jobs j SET status='RUNNING', attempt=j.attempt+1,
              attempt_token=%s, lease_expires_at=now()+(%s * interval '1 second')
            FROM candidate WHERE j.id=candidate.id RETURNING j.*
            """, (job_id,job_id,uuid4(),lease_seconds)).fetchone()


def complete(job, words):
    with connect() as conn:
        won = conn.execute("""
            UPDATE document_parse_jobs SET status='SUCCEEDED', result_ref='db:document_parse_results/'||id,
              finished_at=now(), attempt_token=NULL, lease_expires_at=NULL, last_error_class=NULL
            WHERE id=%s AND status='RUNNING' AND attempt_token=%s AND lease_expires_at>now()
            RETURNING id
            """, (job["id"],job["attempt_token"])).fetchone()
        if won:
            conn.execute("INSERT INTO document_parse_results VALUES (%s,%s)", (job["id"],words))
        return won is not None


def retry(job, error_class="TransientError", delay_seconds=1, permanent=False):
    # One database budget is authoritative; broker retries never reset it.
    with connect() as conn:
        row = conn.execute("""
            UPDATE document_parse_jobs SET
              status=CASE WHEN %s OR attempt>=max_attempts OR
                  now()+(%s * interval '1 second')>=retry_deadline THEN 'FAILED' ELSE 'PENDING' END,
              next_attempt_at=now()+(%s * interval '1 second'),
              last_error_class=%s, attempt_token=NULL, lease_expires_at=NULL
            WHERE id=%s AND status='RUNNING' AND attempt_token=%s AND lease_expires_at>now()
            RETURNING id,status
            """, (permanent,delay_seconds,delay_seconds,error_class,job["id"],job["attempt_token"])).fetchone()
        if row and row["status"] == "PENDING":
            conn.execute("INSERT INTO job_outbox(id,job_id) VALUES (%s,%s)", (uuid4(),job["id"]))
        elif row:
            conn.execute("UPDATE document_parse_jobs SET finished_at=now() WHERE id=%s", (job["id"],))
        return row


def execute(job_id=None, fail=False):
    recover()
    job = claim(job_id)
    if job is None:
        return None
    try:
        with connect() as conn:
            content = conn.execute("SELECT content FROM document_inputs WHERE ref=%s", (job["input_ref"],)).fetchone()["content"]
        if fail:
            raise ConnectionError("local failure injection")
        # Bounded 10,000 characters input; this deterministic effect has no remote ambiguity.
        if not complete(job, len(content.split())):
            return "lost-ownership"
    except ConnectionError:
        retry(job)
        return "retry-scheduled"
    return str(job["id"])
