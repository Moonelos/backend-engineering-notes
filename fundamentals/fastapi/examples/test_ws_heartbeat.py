import asyncio
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('ws_heartbeat', Path(__file__).with_name('ws_heartbeat.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_matching_pong_and_silent_peer():
    async def scenario():
        heartbeat = module.Heartbeat()
        queue, stop = asyncio.Queue(maxsize=1), asyncio.Event()
        task = asyncio.create_task(heartbeat.probe(queue, stop, .1))
        ping = await queue.get()
        heartbeat.observe({'type': 'pong', 'nonce': 'old-probe'})
        assert not heartbeat.acknowledged.is_set()
        heartbeat.observe({'type': 'pong', 'nonce': ping['nonce']})
        assert await task is True and not stop.is_set()
        task = asyncio.create_task(heartbeat.probe(queue, stop, .02))
        await queue.get()  # Peer reads the ping but never responds.
        assert await task is False and stop.is_set()
    asyncio.run(scenario())


def test_full_writer_queue_has_same_deadline():
    async def scenario():
        queue, stop = asyncio.Queue(maxsize=1), asyncio.Event()
        queue.put_nowait({'type': 'data'})
        assert not await module.Heartbeat().probe(queue, stop, .02)
        assert stop.is_set()
    asyncio.run(scenario())
