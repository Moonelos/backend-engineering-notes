"""Explicit owners for first useful stream and supervised bounded merge."""
import asyncio
from contextlib import asynccontextmanager
from advanced_streaming import Frame, finish


@asynccontextmanager
async def first_stream(owners, timeout=5):
    async def first(owner):
        await owner.open()
        frame = await owner.next()
        if frame is None or frame.kind != 'delta':
            raise ValueError('No useful first frame')
        return owner, frame
    tasks = [asyncio.create_task(first(owner)) for owner in owners]
    winner = None
    try:
        async with asyncio.timeout(timeout):
            pending = set(tasks)
            while pending and winner is None:
                done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                # Stable tie break; observe every task later, including completed losers.
                for task in tasks:
                    if task in done and not task.cancelled() and task.exception() is None:
                        winner = task.result()
                        break
            if winner is None:
                raise ValueError('No successful provider')
        for task in tasks:
            if not task.done():
                task.cancel()
        await finish(asyncio.gather(*tasks, return_exceptions=True))
        await finish(asyncio.gather(*(o.close() for o in owners if o is not winner[0])))
        yield winner  # SAME owner/iterator for all subsequent frames.
    finally:
        for task in tasks:
            task.cancel()
        await finish(asyncio.gather(*tasks, return_exceptions=True))
        await finish(asyncio.gather(*(owner.close() for owner in owners)))


@asynccontextmanager
async def merged_stream(owners_by_source, *, max_buffer=4):
    queue = asyncio.Queue(maxsize=max_buffer)
    async def produce(source, owner):
        try:
            await owner.open()
            while (frame := await owner.next()) is not None:
                await queue.put((source, frame))
                if frame.kind == 'done':
                    return
            await queue.put((source, Frame('error', {'code': 'missing_terminal'})))
        except Exception:
            await queue.put((source, Frame('error', {'code': 'provider_failed'})))
        finally:
            await finish(owner.close())
            # Cancellation must not block trying to enqueue a sentinel into a full queue.

    async def iterate():
        pending_sources = set(owners_by_source)
        while pending_sources:
            source, frame = await queue.get()
            queue.task_done()
            if frame.kind in {'done', 'error'}:
                pending_sources.remove(source)
            yield source, frame

    tasks = [asyncio.create_task(produce(s, o)) for s, o in owners_by_source.items()]
    try:
        yield iterate()
    finally:
        for task in tasks:
            task.cancel()
        await finish(asyncio.gather(*tasks, return_exceptions=True))
        await finish(asyncio.gather(*(o.close() for o in owners_by_source.values())))
