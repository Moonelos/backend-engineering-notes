"""Run while a separate worker and publisher are alive; bounded by 15 seconds."""
import time
from uuid import uuid4
import store

key=str(uuid4())
job=store.submit(key,'one two three')
assert store.submit(key,'one two three')['id']==job['id']
deadline=time.monotonic()+15
while time.monotonic()<deadline:
    result=store.get_job(job['id'])
    if result['status']=='SUCCEEDED':
        assert result['words']==3
        print('one durable job, words=3, status=SUCCEEDED')
        break
    time.sleep(0.1)
else:
    raise AssertionError('job not completed: inspect publisher, worker and DB state')
