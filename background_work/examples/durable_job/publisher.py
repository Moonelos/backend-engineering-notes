"""Outbox relay plus bounded recovery scan; choose exactly one broker adapter."""
import argparse
import time
from uuid import uuid4
import store


def publish_one(send):
    with store.connect() as conn:
        row = conn.execute("""
            SELECT o.id,o.job_id FROM job_outbox o JOIN document_parse_jobs j ON j.id=o.job_id
            WHERE o.published_at IS NULL AND j.status='PENDING' AND j.next_attempt_at<=now()
            ORDER BY o.created_at FOR UPDATE OF o SKIP LOCKED LIMIT 1
            """).fetchone()
        if row is None:
            return False
        send(str(row['job_id']))
        # A crash after send repeats delivery; only confirmed sends are marked.
        conn.execute('UPDATE job_outbox SET published_at=now() WHERE id=%s',(row['id'],))
        return True


def repair_missing_hints():
    store.recover()
    with store.connect() as conn:
        rows = conn.execute("""
            SELECT j.id FROM document_parse_jobs j
            WHERE j.status='PENDING' AND j.next_attempt_at<=now()
              AND NOT EXISTS(SELECT 1 FROM job_outbox o WHERE o.job_id=j.id
                AND (o.published_at IS NULL OR o.published_at>now()-interval '5 seconds'))
            ORDER BY j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 100
            """).fetchall()
        for row in rows:
            conn.execute('INSERT INTO job_outbox(id,job_id) VALUES (%s,%s)',(uuid4(),row['id']))


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('runtime',choices=['dramatiq','celery'])
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    if args.runtime=='dramatiq':
        from dramatiq_tasks import parse_job
        send=parse_job.send
    else:
        from celery_tasks import parse_job
        send=lambda job_id: parse_job.apply_async(args=[job_id],retry=False)
    while True:
        repair_missing_hints()
        sent=publish_one(send)
        if args.once: break
        if not sent: time.sleep(0.2)
