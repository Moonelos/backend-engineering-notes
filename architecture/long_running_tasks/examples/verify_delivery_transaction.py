"""Execute current lesson SQL/Python fences against an owned disposable PostgreSQL 17.

Run with asyncpg installed and local Docker; no existing database is touched.
"""
import asyncio
import json
from pathlib import Path
import re
import subprocess
import uuid
import asyncpg


def docker(*args):
    return subprocess.check_output(['docker', *args], text=True, stderr=subprocess.DEVNULL).strip()


async def main():
    note = Path(__file__).resolve().parents[1] / '03_client_delivery_patterns.md'
    source = note.read_text()
    schema = next(s for s in re.findall(r'```sql\n(.*?)\n```', source, re.S)
                  if 'CREATE TABLE delivery_jobs' in s)
    code = next(s for s in re.findall(r'```python\n(.*?)\n```', source, re.S)
                if 'async def create_job_intent' in s)
    namespace = {}
    exec(compile(code, str(note), 'exec'), namespace)
    create, complete = namespace['create_job_intent'], namespace['on_worker_complete']
    name = 'notes-delivery-' + uuid.uuid4().hex[:12]
    docker('run', '-d', '--name', name, '-e', 'POSTGRES_PASSWORD=local-fixture-only',
           '-p', '127.0.0.1::5432', 'postgres:17-alpine')
    db = None
    try:
        port = int(docker('port', name, '5432/tcp').rsplit(':', 1)[1])
        async with asyncio.timeout(60):
            while True:
                try:
                    db = await asyncpg.connect(host='127.0.0.1', port=port, user='postgres',
                                               password='local-fixture-only', database='postgres')
                    break
                except (OSError, asyncpg.CannotConnectNowError):
                    await asyncio.sleep(.1)
        await db.execute(schema)

        class FailInsert:
            def __init__(self, table):
                self.table = table
            def __getattr__(self, attr):
                return getattr(db, attr)
            async def execute(self, sql, *args):
                if sql.startswith('INSERT INTO ' + self.table):
                    raise RuntimeError('injected process failure before intent insert')
                return await db.execute(sql, *args)

        try:
            await create(FailInsert('job_dispatch_outbox'), 'tenant7', {}, 'registration7')
        except RuntimeError:
            pass
        else:
            raise AssertionError('submission fault missing')
        assert await db.fetchval('SELECT count(*) FROM delivery_jobs') == 0
        job_id = await create(db, 'tenant7', {'input': 1}, 'registration7')
        assert await db.fetchval('SELECT state FROM job_dispatch_outbox WHERE job_id=$1', job_id) == 'pending'
        print('PASS submission crash rolls back job; committed job always has durable dispatch intent')
        await db.execute("UPDATE delivery_jobs SET state='running', generation=2, "
                         "lease_expires_at=clock_timestamp()+interval '60 seconds' WHERE id=$1", job_id)
        assert not await complete(db, job_id, 1, {'owner': 'stale'})
        assert await db.fetchval('SELECT count(*) FROM callback_deliveries') == 0
        await db.execute("UPDATE delivery_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=$1", job_id)
        assert not await complete(db, job_id, 2, {'owner': 'expired'})
        await db.execute("UPDATE delivery_jobs SET lease_expires_at=clock_timestamp()+interval '60 seconds' WHERE id=$1", job_id)
        try:
            await complete(FailInsert('callback_deliveries'), job_id, 2, {'owner': 'current'})
        except RuntimeError:
            pass
        else:
            raise AssertionError('completion fault missing')
        row = await db.fetchrow('SELECT state,result FROM delivery_jobs WHERE id=$1', job_id)
        assert row['state'] == 'running' and row['result'] is None
        assert await complete(db, job_id, 2, {'owner': 'current'})
        assert not await complete(db, job_id, 2, {'owner': 'duplicate'})
        await db.close()
        db = await asyncpg.connect(host='127.0.0.1', port=port, user='postgres',
                                   password='local-fixture-only', database='postgres')
        delivery = await db.fetchrow('SELECT * FROM callback_deliveries WHERE job_id=$1', job_id)
        assert delivery['state'] == 'pending' and delivery['id'] == f'{job_id}-2'
        assert json.loads(delivery['body']) == {
            'job_id': job_id, 'state': 'succeeded', 'generation': 2,
            'result': {'owner': 'current'},
        }
        assert await db.fetchval('SELECT count(*) FROM callback_deliveries') == 1
        print('PASS stale/expired owners rejected; callback insertion failure rolls result back')
        print('PASS committed generation-2 envelope and one pending delivery survive reconnect')
    finally:
        if db is not None:
            await db.close()
        subprocess.run(['docker', 'rm', '-f', name], check=True, capture_output=True)


if __name__ == '__main__':
    asyncio.run(main())
