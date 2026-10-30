"""Owned hedges, bounded ephemeral priority work, and generation-checked Redis probes."""
import asyncio
import itertools
import uuid
from advanced_streaming import finish
from bounded_calls import AdmissionTimeout


async def hedge(primary, secondary, *, delay=.05, total=1):
    """Factories must themselves perform admission and allow safe duplicate execution."""
    tasks = [asyncio.create_task(primary(), name='hedge-primary')]
    errors = []
    try:
        async with asyncio.timeout(total):
            done, _ = await asyncio.wait(tasks, timeout=delay)
            if done:
                try:
                    return tasks[0].result()
                except Exception as exc:
                    errors.append(exc)
            tasks.append(asyncio.create_task(secondary(), name='hedge-secondary'))
            pending = {t for t in tasks if t not in done}
            while pending:
                ready, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in tasks:
                    if task in ready:
                        try:
                            return task.result()
                        except Exception as exc:
                            errors.append(exc)
            raise ExceptionGroup('All hedge candidates failed', errors)
    finally:
        for task in tasks:
            task.cancel()
        await finish(asyncio.gather(*tasks, return_exceptions=True))


class PriorityWork:
    """Ephemeral queue; caller cancellation abandons result, not durable business work."""
    def __init__(self, capacity=20):
        self.queue = asyncio.PriorityQueue(maxsize=capacity)
        self.sequence = itertools.count()

    async def submit(self, factory, *, priority=10, queue_timeout=.1):
        future = asyncio.get_running_loop().create_future()
        try:
            # Only immediate insertion is supported; no unbounded population of put waiters.
            self.queue.put_nowait((priority, next(self.sequence),
                asyncio.get_running_loop().time() + queue_timeout, factory, future))
        except asyncio.QueueFull as exc:
            raise AdmissionTimeout('Priority queue full') from exc
        try:
            return await future
        finally:
            if not future.done():
                future.cancel()

    async def worker(self):
        while True:
            _, _, deadline, factory, future = await self.queue.get()
            try:
                if future.cancelled():
                    continue
                if asyncio.get_running_loop().time() >= deadline:
                    raise AdmissionTimeout('Priority queue deadline')
                # The queue deadline has ended; factory owns the execution deadline.
                result = await factory()
                if not future.done():
                    future.set_result(result)
            except asyncio.CancelledError:
                if not future.done():
                    future.cancel()
                raise
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
            finally:
                self.queue.task_done()

    def abandon_pending(self):
        while not self.queue.empty():
            *_, future = self.queue.get_nowait()
            future.cancel()
            self.queue.task_done()


BREAKER = r'''
local key=KEYS[1]
local t=redis.call('TIME'); local now=tonumber(t[1])*1000+tonumber(t[2])/1000
local action=ARGV[1]
local state=redis.call('HGET',key,'state') or 'closed'
local gen=tonumber(redis.call('HGET',key,'gen') or '0')
if action=='allow' then
  if state=='closed' then return {1,gen,''} end
  if tonumber(redis.call('HGET',key,'until') or '0')>now then return {0,gen,''} end
  gen=gen+1
  redis.call('HSET',key,'state','half','gen',gen,'token',ARGV[2],'until',now+tonumber(ARGV[3]))
  return {1,gen,ARGV[2]}
end
if gen~=tonumber(ARGV[2]) then return 0 end
if state=='half' and (redis.call('HGET',key,'token')~=ARGV[3] or
    tonumber(redis.call('HGET',key,'until'))<=now) then return 0 end
if state=='open' then return 0 end
local outcome=ARGV[4]
if outcome=='neutral' then
  if state=='half' then redis.call('HSET',key,'until',now) end
  return 1
end
if outcome=='success' then
  redis.call('HSET',key,'state','closed','failures',0,'gen',gen+1,'token','','until',0)
  return 1
end
local failures=redis.call('HINCRBY',key,'failures',1)
if state=='half' or failures>=tonumber(ARGV[5]) then
  redis.call('HSET',key,'state','open','gen',gen+1,'token','','until',now+tonumber(ARGV[6]))
end
return 1
'''


class SharedBreaker:
    def __init__(self, redis, key, *, threshold=3, cooldown_ms=1000, probe_ms=500):
        self.script = redis.register_script(BREAKER)
        self.key, self.threshold, self.cooldown, self.probe = key, threshold, cooldown_ms, probe_ms

    async def allow(self):
        allowed, generation, token = await self.script(keys=[self.key],
            args=['allow', uuid.uuid4().hex, self.probe])
        if not allowed:
            raise AdmissionTimeout('Circuit open')
        return int(generation), token

    async def record(self, ticket, outcome):
        if outcome not in {'success', 'failure', 'neutral'}:
            raise ValueError('Invalid breaker outcome')
        gen, token = ticket
        return bool(await self.script(keys=[self.key],
            args=['record', gen, token, outcome, self.threshold, self.cooldown]))
