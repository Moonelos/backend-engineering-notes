"""Run against disposable Redis on 127.0.0.1:16379; owned random keys only."""
import asyncio
import json
import sqlite3
import tempfile
import uuid
from pathlib import Path

from redis.asyncio import Redis
from redis.exceptions import ConnectionError
from stream_worker import PARK, consume


async def main():
    r = Redis(host='127.0.0.1', port=16379, decode_responses=True)
    stream, group = 'orders:{' + uuid.uuid4().hex + '}', 'billing'
    stop = asyncio.Event()
    task = None
    try:
        async with asyncio.timeout(15):
            while True:
                try:
                    await r.ping()
                    break
                except ConnectionError:
                    await asyncio.sleep(.1)
        with tempfile.TemporaryDirectory() as directory:
            db = sqlite3.connect(Path(directory) / 'effects.sqlite')
            db.execute('CREATE TABLE effects(event_id TEXT PRIMARY KEY, value TEXT NOT NULL)')
            await r.xgroup_create(stream, group, '0', mkstream=True)
            await r.xadd(stream, {'event_id': 'abandoned', 'value': 'ready'})
            await r.xreadgroup(group, 'old-worker', {stream: '>'}, count=1)
            await r.xadd(stream, {'event_id': 'transient', 'value': 'ready'})
            poison = {'event_id': 'poison', 'value': 'invalid'}
            poison_id = await r.xadd(stream, poison)
            attempts = {}

            async def effect(entry_id, fields):
                event_id = fields['event_id']
                attempts[event_id] = attempts.get(event_id, 0) + 1
                if event_id == 'poison' or (event_id == 'transient' and attempts[event_id] == 1):
                    raise ValueError('fixture failure')
                with db:
                    db.execute('INSERT OR IGNORE INTO effects VALUES (?, ?)',
                               (event_id, fields['value']))

            task = asyncio.create_task(consume(r, stream, group, 'new-worker', effect, stop=stop,
                        idle_ms=100, processing_seconds=.02, max_deliveries=3))
            async with asyncio.timeout(15):
                while True:
                    if task.done(): await task
                    rows = db.execute('SELECT event_id FROM effects ORDER BY event_id').fetchall()
                    parked = await r.xrange(stream + ':dead-letter')
                    if len(rows) == 2 and len(parked) == 1 and (await r.xpending(stream, group))['pending'] == 0:
                        break
                    await asyncio.sleep(.05)
            stop.set()
            await task
            assert rows == [('abandoned',), ('transient',)], rows
            assert attempts['transient'] == 2 and attempts['poison'] == 3, attempts
            assert json.loads(parked[0][1]['payload']) == poison
            duplicate = await r.eval(PARK, 3, stream, stream+':dead-letter', stream+':parked',
                                     poison_id, json.dumps(poison), 'ValueError', 3, group)
            assert duplicate == parked[0][0] and await r.xlen(stream+':dead-letter') == 1
            await r.xtrim(stream, maxlen=0, approximate=False)
            assert json.loads((await r.xrange(stream+':dead-letter'))[0][1]['payload']) == poison
            print('PASS: abandoned claimed; transient retried; 2 effects; poison parked once with payload; pending=0')
            db.close()
    finally:
        if task is not None and not task.done():
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
        await r.delete(stream, stream+':dead-letter', stream+':parked')
        await r.aclose()


if __name__ == '__main__':
    asyncio.run(main())
