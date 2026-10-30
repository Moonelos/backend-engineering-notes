from uuid import uuid4
import dramatiq
from dramatiq.brokers.stub import StubBroker
from dramatiq.worker import Worker
import store
from dramatiq_tasks import parse_job
from publisher import publish_one


def test_actual_actor_duplicate_delivery(monkeypatch):
    broker=StubBroker()
    monkeypatch.setattr(parse_job,'broker',broker)
    broker.declare_actor(parse_job)
    broker.emit_after('process_boot')
    worker=Worker(broker,worker_threads=2)
    job=store.submit(str(uuid4()),'three words here')
    worker.start()
    try:
        parse_job.send(str(job['id']))
        parse_job.send(str(job['id']))
        broker.join(parse_job.queue_name,timeout=5_000)
        worker.join()
        row=store.get_job(job['id'])
        assert (row['status'],row['words'],row['attempt'])==('SUCCEEDED',3,1)
    finally:
        worker.stop(timeout=5_000)
        broker.close()


def test_publish_then_rollback_keeps_intent():
    store.submit(str(uuid4()),'relay crash')
    sent=[]
    def send_then_crash(job_id):
        sent.append(job_id)
        raise RuntimeError('crash after broker accepted, before DB mark')
    try:
        publish_one(send_then_crash)
    except RuntimeError:
        pass
    else:
        raise AssertionError('expected injected failure')
    with store.connect() as conn:
        assert conn.execute('SELECT count(*) AS n FROM job_outbox WHERE job_id=%s AND published_at IS NULL',(sent[0],)).fetchone()['n']>=1
    assert publish_one(sent.append)
    assert sent[0]==sent[1]  # Repeated delivery is intentional, never lost intent.
