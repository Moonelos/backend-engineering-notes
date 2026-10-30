"""Python 3.14+ lifecycle lab. Only temporary marker files; no network or durable business effects."""
import asyncio
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
import multiprocessing as mp
import os
from pathlib import Path
import tempfile
import time


def compute(items: list[int], seconds: float = 0, marker: str = '') -> tuple[int, list[int]]:
    if marker:
        Path(marker + '.started').write_text(str(os.getpid()))
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        sum(i * i for i in range(1000))
    if marker:
        Path(marker + '.done').write_text('completed')
    return os.getpid(), [x * x for x in items]


def initialize(fail: bool) -> None:
    if fail:
        raise RuntimeError('deliberate initialization failure')


class Busy(Exception):
    pass


class BoundedCPU:
    """Event-loop-owned fail-fast admission; permits follow actual futures, not awaiters."""
    def __init__(self, *, limit: int = 2, fail_initializer: bool = False):
        self.pool = ProcessPoolExecutor(max_workers=2, mp_context=mp.get_context('spawn'),
                                        initializer=initialize, initargs=(fail_initializer,))
        self.limit = limit
        self.pending = set()
        self.accepting = True

    def submit(self, *args):
        if not self.accepting or len(self.pending) >= self.limit:
            raise Busy('CPU capacity unavailable')
        future = asyncio.wrap_future(self.pool.submit(compute, *args))
        self.pending.add(future)
        def completed(done):
            self.pending.discard(done)
            if not done.cancelled():
                done.exception()  # Observe failures even if the caller abandoned its wait.
        future.add_done_callback(completed)
        # Never expose the accounting future: cancelling this caller's view must
        # not release capacity while its process is still computing.
        view = asyncio.shield(future)
        def observe_view(done):
            if not done.cancelled():
                done.exception()  # An abandoned view must not hide an unobserved error.
        view.add_done_callback(observe_view)
        return view

    async def call(self, *args, timeout: float):
        future = self.submit(*args)
        # submit returns a shielded view; even direct-await cancellation is safe.
        return await asyncio.wait_for(future, timeout)

    async def close(self, budget: float = 3) -> bool:
        self.accepting = False
        _, pending = await asyncio.wait(tuple(self.pending), timeout=budget) if self.pending else (set(), set())
        if pending:
            # Pool-wide escalation, deliberately safe only for this pure-compute fixture.
            self.pool.kill_workers()  # Python 3.14+. Production effects need a recovery policy.
            await asyncio.gather(*pending, return_exceptions=True)
            return False
        await asyncio.to_thread(self.pool.shutdown, wait=True, cancel_futures=True)
        return True


async def main():
    if not hasattr(ProcessPoolExecutor, 'kill_workers'):
        raise SystemExit('This lifecycle lab requires Python 3.14+; the chapter baseline example supports 3.11+.')
    with tempfile.TemporaryDirectory(prefix='notes-cpu-') as directory:
        owner = BoundedCPU(limit=4)
        try:
            # Four inputs/two workers, then the same inputs in two batches.
            single = await asyncio.gather(*(owner.call([n], .03, timeout=3) for n in range(1, 5)))
            batch = await asyncio.gather(owner.call([1, 2], timeout=3), owner.call([3, 4], timeout=3))
            assert [x for _, values in single for x in values] == [1, 4, 9, 16]
            assert [x for _, values in batch for x in values] == [1, 4, 9, 16]
            print('items=4; dispatches=4 then 2; worker PIDs=', sorted({pid for pid, _ in single}))
            owner.limit = 2
            marker = str(Path(directory) / 'job')
            first = owner.submit([5], .4, marker)
            second = owner.submit([6], .4)
            try:
                await asyncio.wait_for(asyncio.shield(first), .03)
                raise AssertionError('wait should time out')
            except TimeoutError:
                assert len(owner.pending) == 2
                assert not Path(marker + '.done').exists()
            try:
                owner.submit([7])
                raise AssertionError('replacement must be rejected')
            except Busy:
                print('caller timed out; 2 permits remain charged; replacement rejected')
            await asyncio.gather(first, second)
            assert Path(marker + '.done').read_text() == 'completed'
            print('later marker observed; actual completions release permits')
            # Exercise the public submit API without asking callers to add shield.
            marker = str(Path(directory) / 'cancelled-waiter')
            first = owner.submit([9], .4, marker)
            second = owner.submit([10], .4)
            async def await_first():
                return await first
            waiter = asyncio.create_task(await_first())
            for _ in range(200):
                if Path(marker + '.started').exists():
                    break
                await asyncio.sleep(.005)
            assert Path(marker + '.started').exists()
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
            assert len(owner.pending) == 2
            assert not Path(marker + '.done').exists()
            try:
                owner.submit([11])
                raise AssertionError('cancelled waiter must not free running capacity')
            except Busy:
                pass
            await asyncio.gather(*tuple(owner.pending))
            await second
            assert Path(marker + '.done').exists()
            print('direct-await cancellation retained permits until actual process completion')
        finally:
            assert await owner.close()
        broken = BoundedCPU(fail_initializer=True)
        try:
            try:
                await broken.call([1], timeout=3)
                raise AssertionError('initializer should fail')
            except BrokenProcessPool:
                print('initializer failed: discard pool, repair cause, recreate once')
        finally:
            await broken.close()
        replacement = BoundedCPU()
        try:
            assert (await replacement.call([7], timeout=3))[1] == [49]
        finally:
            assert await replacement.close()
        overdue = BoundedCPU()
        future = overdue.submit([8], 5)
        assert not await overdue.close(.03)
        assert future.done()
        print('PASS: bounded admission, late completion, one recovery and pool-wide shutdown escalation')


if __name__ == '__main__':
    asyncio.run(main())
