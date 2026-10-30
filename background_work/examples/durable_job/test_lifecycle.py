"""Run only against the dedicated jobs lab database; no cloud services involved."""
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import store
from main import app


def test_http_replay_and_result():
    key = str(uuid4())
    with TestClient(app) as client:
        first = client.post('/document-parses', headers={'Idempotency-Key':key}, json={'text':'one two three'})
        second = client.post('/document-parses', headers={'Idempotency-Key':key}, json={'text':'one two three'})
        conflict = client.post('/document-parses', headers={'Idempotency-Key':key}, json={'text':'different'})
        assert first.status_code == second.status_code == 202
        assert first.json()['id'] == second.json()['id']
        assert conflict.status_code == 409
        location = first.headers['Location']
        assert client.get(location).json()['status'] == 'PENDING'
        store.execute(first.json()['id'])
        result = client.get(location).json()
        assert (result['status'],result['words'],result['attempt']) == ('SUCCEEDED',3,1)


def test_competing_claims_and_stale_completion():
    job = store.submit(str(uuid4()), 'worker recovery')
    barrier = threading.Barrier(2)
    def attempt(_):
        barrier.wait(timeout=5)
        return store.claim(job['id'])
    with ThreadPoolExecutor(2) as pool:
        claimed = [row for row in pool.map(attempt,range(2)) if row]
    assert len(claimed) == 1
    old = claimed[0]
    with store.connect() as conn:
        conn.execute("UPDATE document_parse_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s",(job['id'],))
    store.recover()
    new = store.claim(job['id'])
    assert new['attempt_token'] != old['attempt_token']
    assert not store.complete(old,999)
    assert store.complete(new,2)
    assert store.get_job(job['id'])['words'] == 2


def test_attempt_and_wall_clock_budget():
    job = store.submit(str(uuid4()), 'bounded retries')
    for n in range(3):
        claimed = store.claim(job['id'])
        assert claimed['attempt'] == n+1
        store.retry(claimed,delay_seconds=0)
    assert store.get_job(job['id'])['status'] == 'FAILED'
    assert store.claim(job['id']) is None
    aged = store.submit(str(uuid4()), 'too old')
    with store.connect() as conn:
        conn.execute("UPDATE document_parse_jobs SET retry_deadline=now()-interval '1 second' WHERE id=%s",(aged['id'],))
    assert store.claim(aged['id']) is None
    store.recover()
    assert store.get_job(aged['id'])['status'] == 'FAILED'


def test_real_process_loss():
    # Use a targeted child process, so other tests' pending jobs cannot be claimed.
    job = store.submit(str(uuid4()), 'survives process exit')
    code = 'import os,store; print(store.claim(%r),flush=True); os._exit(17)' % str(job['id'])
    child = subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).parent,capture_output=True,text=True)
    assert child.returncode == 17
    assert store.get_job(job['id'])['status'] == 'RUNNING'
    with store.connect() as conn:
        conn.execute("UPDATE document_parse_jobs SET lease_expires_at=now()-interval '1 second' WHERE id=%s",(job['id'],))
    store.recover()
    assert store.execute(job['id']) == str(job['id'])
    assert store.get_job(job['id'])['attempt'] == 2


def test_recovery_batch_is_bounded():
    running = [store.submit(str(uuid4()), 'bounded recovery') for _ in range(3)]
    for job in running:
        store.claim(job['id'])
    aged = [store.submit(str(uuid4()), 'bounded exhaustion') for _ in range(3)]
    with store.connect() as conn:
        conn.execute("UPDATE document_parse_jobs SET lease_expires_at=now()-interval '1 hour' WHERE id=ANY(%s)",
                     ([j['id'] for j in running],))
        conn.execute("UPDATE document_parse_jobs SET retry_deadline=now()-interval '1 hour' WHERE id=ANY(%s)",
                     ([j['id'] for j in aged],))
    assert store.recover(batch_size=2)==2
    assert sum(store.get_job(j['id'])['status']=='RUNNING' for j in running)==1
    assert sum(store.get_job(j['id'])['status']=='FAILED' for j in aged)==2
    store.recover(batch_size=2)
    assert all(store.get_job(j['id'])['status']=='PENDING' for j in running)
    assert all(store.get_job(j['id'])['status']=='FAILED' for j in aged)
