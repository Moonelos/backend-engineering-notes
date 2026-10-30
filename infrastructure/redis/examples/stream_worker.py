"""Redis 7+ bounded consumer; source/dlq/parking keys share one Redis Cluster hash tag.
The handler must persist business idempotency; acknowledgements do not supply it.
"""
import asyncio
import json
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis
from redis.exceptions import ResponseError

PARK = '''
local id = redis.call('HGET', KEYS[3], ARGV[1])
if not id then
  id = redis.call('XADD', KEYS[2], '*', 'source_id', ARGV[1],
                  'payload', ARGV[2], 'error_class', ARGV[3], 'deliveries', ARGV[4])
  redis.call('HSET', KEYS[3], ARGV[1], id)
end
redis.call('XACK', KEYS[1], ARGV[5], ARGV[1])
return id
'''


async def consume(r: Redis, stream: str, group: str, consumer: str,
                  handler: Callable[[str, dict], Awaitable[None]], *,
                  stop: asyncio.Event, idle_ms: int = 60000,
                  processing_seconds: float = 20, max_deliveries: int = 3) -> None:
    if not 0 < processing_seconds * 1000 < idle_ms or max_deliveries < 1:
        raise ValueError('handler deadline must be shorter than reclaim idle time')
    try:
        await r.xgroup_create(stream, group, id='0', mkstream=True)
    except ResponseError as error:
        if 'BUSYGROUP' not in str(error): raise
    dlq, parked = stream + ':dead-letter', stream + ':parked'

    async def handle(entry_id, data):
        try:
            async with asyncio.timeout(processing_seconds):
                await handler(entry_id, data)
        except asyncio.CancelledError:
            raise  # uncommitted delivery stays pending
        except Exception as error:
            details = await r.xpending_range(stream, group, entry_id, entry_id, 1)
            count = details[0]['times_delivered'] if details else 0
            if count >= max_deliveries:
                # Retain the full payload before settling the source delivery. Stable parking
                # identity and XACK occur in the same server script, including after retries.
                await r.eval(PARK, 3, stream, dlq, parked, entry_id,
                             json.dumps(data), type(error).__name__, count, group)
            # Otherwise leave pending; a later reclaim pass retries it without a restart.
        else:
            await r.xack(stream, group, entry_id)

    # Serial processing reserves one delivery at a time: batch queue residence
    # must not consume the reclaim idle allowance before its handler even starts.
    cursor = '0-0'
    while not stop.is_set():
        cursor, claimed, deleted = await r.xautoclaim(
            stream, group, consumer, min_idle_time=idle_ms, start_id=cursor, count=1)
        if deleted:
            # Missing payload is a retention breach, not successful business completion.
            raise RuntimeError(f'{len(deleted)} pending payloads were trimmed; reconcile source')
        for entry_id, data in claimed:
            if stop.is_set(): return
            await handle(entry_id, data)
        # Even an empty claimed batch can have a nonzero cursor. Preserve it for the next pass.
        fresh = await r.xreadgroup(group, consumer, {stream: '>'}, count=1, block=250)
        for _, entries in fresh:
            for entry_id, data in entries:
                if stop.is_set(): return
                await handle(entry_id, data)
