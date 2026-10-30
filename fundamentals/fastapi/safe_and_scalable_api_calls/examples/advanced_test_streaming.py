import asyncio
import httpx
import pytest
from advanced_streaming import WeightedGate, StreamOwner, FiniteSSE, demo_transport, DemoBytes
from advanced_stream_racing import first_stream, merged_stream
from advanced_resilience import hedge, PriorityWork
from bounded_calls import AdmissionTimeout


def test_cancel_hedge_before_delay_and_first_failure():
    async def run():
        stopped = asyncio.Event()
        async def slow():
            try:
                await asyncio.sleep(10)
            finally:
                stopped.set()
        task = asyncio.create_task(hedge(slow, slow, delay=.5))
        await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()
        async def bad():
            raise ValueError('no')
        async def good():
            return 42
        assert await hedge(bad, good) == 42
    asyncio.run(run())


def test_weighted_atomic_timeout_and_validation():
    async def run():
        gate = WeightedGate(3)
        async with gate.lease(2):
            with pytest.raises(TimeoutError):
                async with gate.lease(2, timeout=.01):
                    pass
            assert gate.used == 2 and gate.waiting == 0
        assert gate.used == 0
        with pytest.raises(ValueError):
            async with gate.lease(4):
                pass
    asyncio.run(run())


async def invoke(response, *, disconnect=False, send_delay=0):
    messages = []
    disconnected = asyncio.Event()
    async def receive():
        await disconnected.wait()
        return {'type': 'http.disconnect'}
    async def send(message):
        await asyncio.sleep(send_delay)
        messages.append(message)
        if disconnect and message['type'] == 'http.response.body':
            disconnected.set()
    await response({}, receive, send)
    return messages


def test_sse_total_idle_status_disconnect_and_slow_client():
    async def run():
        for path, total, idle, disconnect, send_delay, status in [
            ('/ok', 1, .1, False, 0, 200), ('/bad', 1, .1, False, 0, 503),
            ('/empty', 1, .1, False, 0, 503), ('/drip', .09, .03, False, 0, 200),
            ('/ok', 1, .005, False, 0, 503), ('/ok', 1, .1, True, 0, 200),
            ('/ok', 1, .1, False, .04, None)]:
            streams, stats, gate = [], {}, WeightedGate(1)
            async with httpx.AsyncClient(base_url='https://test', transport=demo_transport(streams)) as client:
                messages = await invoke(FiniteSSE(client, gate, path=path, total=total, idle=idle,
                    send_timeout=.02, stats=stats), disconnect=disconnect, send_delay=send_delay)
            assert all(s.closed for s in streams)
            assert gate.used == gate.waiting == 0
            if status:
                assert messages[0]['status'] == status
            assert sum(stats.values()) == 1
            if path == '/drip':
                assert b'stream_interrupted' in messages[-1]['body']
    asyncio.run(run())


def test_stream_admission_before_headers():
    async def run():
        gate, streams = WeightedGate(1), []
        async with httpx.AsyncClient(base_url='https://test', transport=demo_transport(streams)) as client:
            async with gate.lease():
                messages = await invoke(FiniteSSE(client, gate, admission=.005))
                assert messages[0]['status'] == 503 and streams == []
    asyncio.run(run())


def test_simultaneous_first_frames_close_loser_and_continue_iterator():
    async def run():
        streams = []
        async def transport(request):
            stream = DemoBytes(delay=0)
            streams.append(stream)
            return httpx.Response(200, headers={'content-type': 'text/event-stream'}, stream=stream)
        async with httpx.AsyncClient(base_url='https://test', transport=httpx.MockTransport(transport)) as client:
            owners = [StreamOwner(client, '/a'), StreamOwner(client, '/b')]
            async with first_stream(owners) as (winner, frame):
                assert frame.data == {'text': '0'}
                assert sum(o.closed for o in owners) == 1
                assert not winner.closed
                assert (await winner.next()).data == {'text': '1'}
                assert (await winner.next()).data == {'text': '2'}
                assert (await winner.next()).kind == 'done'
            assert all(o.closed for o in owners)
    asyncio.run(run())


def test_merge_source_errors_and_early_consumer_close():
    async def run():
        streams = []
        async with httpx.AsyncClient(base_url='https://test', transport=demo_transport(streams)) as client:
            async with merged_stream({'a': StreamOwner(client, '/ok'),
                    'b': StreamOwner(client, '/bad')}, max_buffer=1) as events:
                items = [item async for item in events]
                assert ('b', 'error') in [(s, f.kind) for s, f in items]
                assert ('a', 'done') in [(s, f.kind) for s, f in items]
            assert all(s.closed for s in streams)
            async with merged_stream({'a': StreamOwner(client, '/drip'),
                    'b': StreamOwner(client, '/drip')}, max_buffer=1) as events:
                await anext(events)
            assert all(s.closed for s in streams)
    asyncio.run(run())


def test_priority_cancelled_submitter_does_not_kill_worker():
    async def run():
        pool = PriorityWork(capacity=1)
        async def value():
            return 42
        task = asyncio.create_task(pool.submit(value))
        await asyncio.sleep(0)
        with pytest.raises(AdmissionTimeout):
            await pool.submit(value)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        worker = asyncio.create_task(pool.worker())
        await pool.queue.join()
        assert await pool.submit(value) == 42
        await pool.queue.join()
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
    asyncio.run(run())


def test_bulkhead_keeps_healthy_provider_available():
    from bounded_calls import BoundedCaller
    async def run():
        occupied=asyncio.Event()
        async def slow(request):
            occupied.set()
            await asyncio.sleep(10)
            return httpx.Response(200,json={'vendor':'a'})
        async def healthy(request):
            return httpx.Response(200,json={'vendor':'b'})
        async with httpx.AsyncClient(base_url='https://a',transport=httpx.MockTransport(slow)) as ca, \
                httpx.AsyncClient(base_url='https://b',transport=httpx.MockTransport(healthy)) as cb:
            a,b=BoundedCaller(ca,capacity=1,max_waiters=0),BoundedCaller(cb,capacity=1,max_waiters=0)
            task=asyncio.create_task(a.request_json('GET','/'))
            await occupied.wait()
            with pytest.raises(AdmissionTimeout): await a.request_json('GET','/')
            assert await b.request_json('GET','/')=={'vendor':'b'}
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
            assert a.gate.active==b.gate.active==0
    asyncio.run(run())


def test_empty_and_failed_race_candidates_do_not_win():
    async def run():
        streams=[]
        async with httpx.AsyncClient(base_url='https://test',transport=demo_transport(streams)) as client:
            owners=[StreamOwner(client,'/empty'),StreamOwner(client,'/bad'),StreamOwner(client,'/ok')]
            async with first_stream(owners) as (winner,first):
                assert winner is owners[2] and first.kind=='delta'
                assert all(o.closed for o in owners[:2])
            assert all(s.closed for s in streams)
            with pytest.raises(ValueError):
                async with first_stream([StreamOwner(client,'/empty'),StreamOwner(client,'/bad')]): pass
            assert all(s.closed for s in streams)
    asyncio.run(run())


def test_priority_queue_deadline_does_not_wrap_execution():
    async def run():
        pool=PriorityWork()
        async def work():
            await asyncio.sleep(.03)
            return 42
        worker=asyncio.create_task(pool.worker())
        assert await pool.submit(work,queue_timeout=.01)==42
        await pool.queue.join()
        worker.cancel()
        await asyncio.gather(worker,return_exceptions=True)
    asyncio.run(run())


def test_disconnect_at_final_body_still_records_outcome():
    async def run():
        streams, stats, disconnected = [], {}, asyncio.Event()
        async def receive():
            await disconnected.wait()
            return {'type':'http.disconnect'}
        async def send(message):
            if message['type']=='http.response.body' and not message.get('more_body',False):
                disconnected.set()
        async with httpx.AsyncClient(base_url='https://test',transport=demo_transport(streams)) as client:
            gate=WeightedGate(1)
            await FiniteSSE(client,gate,stats=stats)({},receive,send)
            assert stats=={'done':1} and gate.used==0
    asyncio.run(run())


def test_stream_total_bytes_bound_small_individual_frames():
    async def run():
        streams=[]
        async with httpx.AsyncClient(base_url='https://test',transport=demo_transport(streams)) as client:
            owner=StreamOwner(client,'/ok',max_bytes=30)
            try:
                await owner.open()
                assert (await owner.next()).kind=='delta'
                with pytest.raises(ValueError,match='byte budget'): await owner.next()
            finally:
                await owner.close()
            assert streams[0].closed
    asyncio.run(run())
