"""Run with asyncpg installed and local Docker. Owns a disposable PostgreSQL container."""
import asyncio
import json
from pathlib import Path
import re
import subprocess
import uuid

import asyncpg


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.DEVNULL).strip()


async def main():
    name = "notes-claim-" + uuid.uuid4().hex[:12]
    docker("run", "-d", "--name", name, "-e", "POSTGRES_PASSWORD=local-fixture-only",
           "-p", "127.0.0.1::5432", "postgres:17-alpine")
    connections = []
    try:
        async with asyncio.timeout(60):
            while True:
                try:
                    docker("exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres")
                    break
                except subprocess.CalledProcessError:
                    await asyncio.sleep(0.1)
        port = int(docker("port", name, "5432/tcp").rsplit(":", 1)[1])
        for _ in range(2):
            connections.append(await asyncpg.connect(host="127.0.0.1", port=port,
                                user="postgres", password="local-fixture-only", database="postgres"))
        a, b = connections
        await a.execute("""CREATE TABLE task_effects (
            task_id TEXT PRIMARY KEY, state TEXT NOT NULL, generation BIGINT NOT NULL,
            lease_expires_at TIMESTAMPTZ NOT NULL);
            CREATE TABLE effects (task_id TEXT PRIMARY KEY, payload JSONB NOT NULL);""")
        note = Path(__file__).resolve().parents[1] / "02_worker_patterns.md"
        source = next(code for code in re.findall(r"```python\n(.*?)\n```", note.read_text(), re.S)
                      if "async def process_if_claimed" in code)
        async def effect(db, task_id, payload):
            await db.execute("INSERT INTO effects VALUES ($1, $2)", task_id, json.dumps(payload))
        namespace = {"apply_business_effect": effect}
        exec(compile(source, str(note), "exec"), namespace)
        process = namespace["process_if_claimed"]

        class PausedClaim:
            def __init__(self, connection):
                self.connection = connection
                self.first = True
            def __getattr__(self, name):
                return getattr(self.connection, name)
            async def fetchval(self, query, *args):
                result = await self.connection.fetchval(query, *args)
                if self.first:
                    self.first = False
                    await b.execute("UPDATE task_effects SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE task_id=$1", args[0])
                    assert await process(b, args[0], {"owner": "B"}) is True
                return result
        assert await process(PausedClaim(a), "abc", {"owner": "A"}) is False
        assert json.loads(await a.fetchval("SELECT payload FROM effects WHERE task_id='abc'")) == {"owner": "B"}
        assert await a.fetchval("SELECT generation FROM task_effects WHERE task_id='abc'") == 2
        assert await process(a, "abc", {"owner": "retry"}) is False
        print("PASS generation 1 resumes after generation 2; only B's effect commits")

        class FailBeforeCompletion:
            def __getattr__(self, name):
                return getattr(a, name)
            async def fetchval(self, query, *args):
                if query.startswith("UPDATE task_effects SET state='complete'"):
                    raise RuntimeError("injected crash before completion marker")
                return await a.fetchval(query, *args)
        try:
            await process(FailBeforeCompletion(), "rollback", {"owner": "A"})
        except RuntimeError:
            pass
        else:
            raise AssertionError("fault not injected")
        assert await a.fetchval("SELECT count(*) FROM effects WHERE task_id='rollback'") == 0
        print("PASS failure before completion rolls the local effect back")
    finally:
        for connection in connections:
            await connection.close()
        subprocess.run(["docker", "rm", "-f", name], check=True, capture_output=True)


if __name__ == "__main__":
    asyncio.run(main())
