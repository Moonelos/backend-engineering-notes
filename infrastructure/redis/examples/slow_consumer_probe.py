"""Two-consumer regression: a serial reader must not reserve an idle-expiring batch."""
import asyncio
import sys
import uuid
from redis.asyncio import Redis
from stream_worker import consume

async def main(url):
    r=Redis.from_url(url,decode_responses=True)
    stream='notes:{'+uuid.uuid4().hex+'}:slow';group='workers';stop=asyncio.Event();started=asyncio.Event();done=[]
    async def effect(entry_id,data):
        started.set();await asyncio.sleep(.04);done.append(entry_id)
        if len(done)==6:stop.set()
    task=None
    try:
        for n in range(6):await r.xadd(stream,{'event_id':str(n)})
        task=asyncio.create_task(consume(r,stream,group,'healthy-a',effect,stop=stop,idle_ms=60,processing_seconds=.05))
        await asyncio.wait_for(started.wait(),2)
        await asyncio.sleep(.075)
        _,claimed,_=await r.xautoclaim(stream,group,'observer-b',min_idle_time=60,start_id='0-0',count=10)
        assert not claimed, f'healthy serial worker reserved idle-expiring queued entries: {claimed}'
        await asyncio.wait_for(task,3)
        assert len(set(done))==6 and (await r.xpending(stream,group))['pending']==0
        print('PASS: second consumer reclaimed 0 healthy queued deliveries; 6 unique effects; pending=0')
    finally:
        stop.set()
        if task and not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
        await r.delete(stream,stream+':dead-letter',stream+':parked');await r.aclose()
if __name__=='__main__':asyncio.run(main(sys.argv[1] if len(sys.argv)>1 else 'redis://127.0.0.1:16379'))
