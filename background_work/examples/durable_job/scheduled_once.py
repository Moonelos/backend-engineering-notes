from datetime import datetime, timedelta, timezone
from threading import Event
from apscheduler.schedulers.background import BackgroundScheduler
import store

scheduled_for=datetime.now(timezone.utc)+timedelta(milliseconds=300)
key='cleanup:'+scheduled_for.isoformat()
finished=Event()


def create_firing():
    # Capture the logical occurrence before scheduling, not callback wall time.
    store.submit(key,'one scheduled cleanup')
    finished.set()


scheduler=BackgroundScheduler(timezone='UTC')
scheduler.add_job(create_firing,'date',run_date=scheduled_for,id='cleanup-once')
scheduler.start()
try:
    assert finished.wait(timeout=5), 'scheduler did not fire'
finally:
    scheduler.shutdown(wait=True)
job=store.submit(key,'one scheduled cleanup')  # restart/replay uses the same key
assert store.execute(job['id']) == str(job['id'])
assert store.get_job(job['id'])['status']=='SUCCEEDED'
print('one scheduled firing, one durable job, SUCCEEDED')
