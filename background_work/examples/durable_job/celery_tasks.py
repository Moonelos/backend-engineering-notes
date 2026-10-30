import os
from celery import Celery
import store

app = Celery('parse_lab',broker=os.environ.get('REDIS_URL','redis://127.0.0.1:56379/0'))
app.conf.update(
    task_serializer='json',accept_content=['json'],task_ignore_result=True,
    task_acks_late=True,task_reject_on_worker_lost=True,worker_prefetch_multiplier=1,
    broker_connection_timeout=2,
    broker_transport_options={'visibility_timeout':120,'socket_timeout':2,'socket_connect_timeout':2},
    result_backend_transport_options={'visibility_timeout':120},visibility_timeout=120,
)


@app.task(name='parse_lab.parse_job',queue='parse.celery',max_retries=0,time_limit=30)
def parse_job(job_id: str):
    # No Celery retry resets the authoritative database attempt budget.
    store.execute(job_id)
