import os
import dramatiq
from dramatiq.brokers.redis import RedisBroker
import store

broker = RedisBroker(url=os.environ.get('REDIS_URL','redis://127.0.0.1:56379/0'),
                     socket_connect_timeout=2, socket_timeout=2)
dramatiq.set_broker(broker)


@dramatiq.actor(queue_name='parse.dramatiq',max_retries=0,time_limit=30_000)
def parse_job(job_id: str):
    # The DB owns retry time/budget. Duplicate deliveries can fail to claim.
    # The 90-second DB lease exceeds this bounded, deterministic lab operation.
    store.execute(job_id)
