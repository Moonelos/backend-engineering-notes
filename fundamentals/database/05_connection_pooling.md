# Connection Pooling — Deep Dive

<!-- length-justification: This is the canonical database-pooling decision reference; SQLAlchemy pools, asyncpg pools, PgBouncer modes, sizing, monitoring, and failure symptoms remain together because each consumes the same PostgreSQL connection budget. -->

> **Who this is for**: Backend engineers who already use PostgreSQL connections and need to size, operate, and debug application and proxy pools.

> **Why pooling matters**: Opening a PostgreSQL connection requires network/authentication work and allocates a server backend; measure its cost in your deployment. Without a pool, every request would pay this cost and your database would run out of connections under load.

> **Key insight**: A pool reuses connections but does not create database capacity; every application and proxy layer must fit inside the same server-side connection budget.

---

## 1. What Is a Connection Pool?

A connection pool retains database connections created on demand. When your code needs a connection, it borrows one from the pool. When done, it returns it — the connection stays open for the next request.

```
Without pool:
  Request → open/authenticate connection → query → close connection → repeat

With pool:
  App start → zero connections; first concurrent SQL creates up to the configured capacity
  Request → borrow available connection or wait → query → return to pool → repeat
```

Reuse reduces repeated connection setup; query plans and transaction duration still determine useful throughput.

---

## 2. SQLAlchemy's Built-in Pool

SQLAlchemy manages its own connection pool. You configure it when creating the engine.

### Pool Types

| Pool Class | Behavior | Use case |
|-----------|----------|----------|
| `QueuePool` (default) | Fixed size + overflow | Web applications |
| `NullPool` | No pooling — new connection per request | Alembic migrations, serverless |
| `StaticPool` | One shared connection, never closed | SQLite in-memory for testing |
| `AssertionPool` | Raises if more than one connection at a time | Debugging |
| `AsyncAdaptedQueuePool` | Async version of QueuePool | Async SQLAlchemy (default) |

### Parameters

```python
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    DATABASE_URL,
    # Pool size
    pool_size=10,          # maximum retained idle capacity (created lazily)
    max_overflow=20,       # extra connections created under load
                           # total max = pool_size + max_overflow = 30
    # Timeouts
    pool_timeout=30,       # seconds to wait when pool is exhausted (raises TimeoutError)
    # Reliability
    pool_pre_ping=True,    # test connection liveness before checkout
    pool_recycle=3600,     # recycle connections after N seconds (prevents stale connections)
    # Debugging
    echo_pool=False,       # True logs pool events (checkouts, checkins, creates)
)
```

### What Each Setting Does

#### `pool_size`

The maximum retained idle capacity, populated by demand. A workload that only uses one connection at a time may never create five. It is not a preopened minimum.

```
pool_size=5 means:
  App startup → connect 0 connections (lazy)
  First 5 requests arrive → create 5 connections
  Requests complete → 5 connections stay open, idle
  New request arrives → reuse an idle connection instantly
```

#### `max_overflow`

Additional connections created when all `pool_size` connections are checked out.

```
pool_size=5, max_overflow=10:
  Connections 1-5: retained capacity (can be invalidated, recycled or disposed)
  Connections 6-15: overflow (created on demand, closed when returned)
  Connection 16+: async caller awaits capacity until pool_timeout, then TimeoutError
```

#### `pool_timeout`

How long to wait for a connection when the pool is exhausted. Under extreme load:

```python
# Low timeout — fail fast rather than queue
pool_timeout=5   # good for user-facing APIs (better to 503 than wait 30s)

# High timeout — queue requests
pool_timeout=60  # for batch jobs that can wait
```

#### `pool_pre_ping`

Before handing a connection to your code, SQLAlchemy sends `SELECT 1`. If the connection is dead (server restart, network drop, cloud proxy killed it), it creates a fresh one.

```
Without pre_ping:
  Connection goes stale after idle → next query fails with "connection lost"

With pre_ping:
  Stale connection detected → discarded → fresh connection used → query succeeds
```

Cost: a liveness round trip, whose latency depends on topology. It handles stale connections at checkout; it cannot recover an already checked-out transaction lost during SQL. Roll back/close after that failure and retry only a replayable whole transaction.

#### `pool_recycle`

Connections older than this age are replaced on their **next checkout**. No timer kills an
active query. Choose an age below a known connection-age policy when that policy warrants it;
`pool_recycle=-1` disables age recycling. It does not cure idle-in-transaction leaks or cancel
long queries: statement/lock/idle-transaction timeouts address different boundaries.
[Pool reliability](https://docs.sqlalchemy.org/en/20/core/pooling.html).

---

## 3. Pool Sizing Math

Getting pool size wrong causes two failure modes:
- **Too small**: requests queue up waiting for connections → high latency
- **Too large**: exhausts database `max_connections` → connections refused

### First establish the fleet ceiling

Each engine has a pool **per process**. Four pods with two worker processes have eight pools,
and rolling deployment can temporarily add more. Include all engines, background workers,
admin/monitoring clients and reserved server slots before assigning the application budget.

```text
PostgreSQL max_connections = 100
Reserved/admin/other clients = 20
Maximum live pods (including rollout) = 5
Worker processes per pod = 2
Application budget = 80 / (5 × 2) = 8 per process
pool_size=6, max_overflow=2 → maximum fleet demand=10 × 8=80
```

This is a ceiling, not evidence that eight simultaneous queries improve throughput. If replicas
increase to eight pods, the same configuration allows 128 app connections and exceeds the budget.
Reduce per-process maximum to five or change the server/proxy budget before that rollout.
`SHOW max_connections;` supplies the server limit; inspect reserved-slot policy separately.

### Then measure how many checkouts the workload needs

Suppose a process completes 100 database units per second and their mean checkout hold time is
40 ms. Mean occupied connections are approximately arrival rate × hold time = 100 × 0.040 = 4
(Little's law for a stable workload). Hold time includes all SQL, lock waits and application gaps
between first SQL and commit; it is not just query execution time. A tail of 400 ms transactions
can still create queues even with this mean of four.

Start a load test with six retained connections and two overflow, within the fleet ceiling above.
Increase arrival rate to the expected peak and include the slower transaction mix. Record request
p95/p99, checkout wait p95/p99, hold time, timeout count, PostgreSQL CPU/I/O/lock waits and successful
throughput. For this example accept p95 request latency <200 ms, checkout p95 <20 ms and fewer than
0.1% pool timeouts; these are stated service objectives, not universal defaults. Test the maximum
live fleet, not one worker multiplied from a quiet benchmark.

If hold time is 40 ms and wait grows while DB CPU remains low, investigate leaks, transaction gaps
and capacity. If adding connections increases CPU saturation and query latency without throughput,
the database is already constrained: reduce query cost/admitted concurrency instead. Choose the
smallest configuration meeting the objectives, repeat the burst/recovery phase, and preserve
headroom for rollout. Raising overflow adds server pressure and hides queues temporarily.

### Measure acquisition separately from checkout hold time

This excerpt instruments a particular QueuePool-family engine. The timer around `connect()`
includes queue wait, connection setup and pre-ping; the event interval measures checked-out time.
Use a histogram exporter in place of `print` and avoid logging SQL or credentials. SQLAlchemy async
sessions autobegin on first SQL, so trace that acquisition boundary separately when using sessions.

```python
from time import monotonic
from sqlalchemy import event, text

@event.listens_for(engine.sync_engine, "checkout")
def mark_checkout(dbapi_connection, record, proxy):
    record.info["checked_out_at"] = monotonic()

@event.listens_for(engine.sync_engine, "checkin")
def mark_checkin(dbapi_connection, record):
    started = record.info.pop("checked_out_at", None)
    if started is not None:
        print("hold_seconds", monotonic() - started)

async def measured_query():
    started = monotonic()
    async with engine.connect() as connection:
        print("acquire_seconds", monotonic() - started)
        await connection.execute(text("SELECT 1"))
```

### A reproducible one-connection queue and recovery

With the dependencies from [04](04_async_sqlalchemy.md), save the following as `pool_queue.py`
and run `python pool_queue.py`. A temporary SQLite file isolates pool scheduling from PostgreSQL
query tuning; it proves timeout and return behavior, not a production sizing result.

```python
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError
from sqlalchemy.ext.asyncio import create_async_engine

async def main():
    with TemporaryDirectory() as directory:
        database = Path(directory) / "queue.db"
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{database}",
            pool_size=1, max_overflow=0, pool_timeout=0.05,
        )
        try:
            async with engine.connect() as first:
                await first.execute(text("SELECT 1"))
                try:
                    async with engine.connect():
                        raise AssertionError("second checkout unexpectedly succeeded")
                except TimeoutError:
                    print("second checkout timed out")
            async with engine.connect() as recovered:
                print("recovered", await recovered.scalar(text("SELECT 1")))
        finally:
            await engine.dispose()

asyncio.run(main())
# second checkout timed out
# recovered 1
```

The timeout rejects the waiting borrower; it does not cancel the first transaction. Returning the
first checkout restores capacity, so the next request succeeds. More asyncio tasks can wait
concurrently without adding connections. Bound admitted work and choose pool_timeout inside the
request deadline, leaving time for error handling; immediate repeated retries amplify overload.

### Kubernetes Considerations

In Kubernetes, `max_overflow` matters more because the number of pods can vary:

```python
import os

POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))

engine = create_async_engine(
    DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_pre_ping=True,
)
```

Configure via environment variables so you can tune without code changes.

---

## 4. PgBouncer — External Connection Pooler

SQLAlchemy's pool manages connections **within a single process**. Under heavy load with many app instances, you can exhaust PostgreSQL's `max_connections` even with small per-instance pools.

**PgBouncer** sits between your app and PostgreSQL, multiplexing connections:

```
App Instance 1 (pool: 10 conns)  ─┐
App Instance 2 (pool: 10 conns)  ─┤→ PgBouncer (10 server conns) → PostgreSQL
App Instance 3 (pool: 10 conns)  ─┘
App Instance 4 (pool: 10 conns)

Without PgBouncer: 40 PostgreSQL connections
With PgBouncer:    10 PostgreSQL connections
```

### PgBouncer Modes

| Mode | How it works | Connection overhead | Use case |
|------|-------------|-------------------|----------|
| **Transaction** (recommended) | Server connection assigned per transaction | Lowest — reuses aggressively | Most web apps |
| **Session** | Server connection held for client's lifetime | Moderate | Apps using session-scoped features (advisory locks, SET SESSION) |
| **Statement** | Server connection per statement | Lowest overhead | Read-only apps only — no multi-statement transactions |

**Transaction mode** is almost always the right choice. It means 100+ app connections can share 10-20 PostgreSQL connections, as long as they're not all in a transaction simultaneously.

### PgBouncer Configuration (pgbouncer.ini)

```ini
[databases]
mydb = host=postgres-server port=5432 dbname=mydb

[pgbouncer]
listen_port = 6432
listen_addr = 0.0.0.0
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt

pool_mode = transaction
default_pool_size = 20       # server connections per database/user pair
max_client_conn = 1000       # max simultaneous client connections
min_pool_size = 5            # minimum server connections to keep
reserve_pool_size = 5        # extra connections for bursts
reserve_pool_timeout = 5     # seconds before using reserve pool
server_idle_timeout = 600    # close idle server connections after 10 min
client_idle_timeout = 0      # never close idle client connections
```

### Connecting Through PgBouncer

```python
from sqlalchemy.pool import NullPool

# Point your connection string at PgBouncer instead of PostgreSQL directly
DATABASE_URL = "postgresql+asyncpg://user:pass@pgbouncer-host:6432/mydb"

# With PgBouncer transaction mode, make two measured choices:
#   1. Don't double-pool: let PgBouncer be the pool (NullPool, or a small async client pool).
#   2. Match prepared-statement behavior to PgBouncer's max_prepared_statements setting.
engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,                       # no internal pool — PgBouncer pools instead
    connect_args={"statement_cache_size": 0}, # does not eliminate dialect prepare calls; verify the topology
)

# Note: NullPool and pool_size/max_overflow are mutually exclusive — NullPool rejects
# size args, so remove them. If you prefer a tiny pool instead of NullPool, drop poolclass and use:
#     pool_size=2, max_overflow=5, pool_pre_ping=True
# and verify pool wait/client-connection cost before choosing either topology.
```

**Why use `NullPool` or a tiny pool with PgBouncer?**

In transaction mode, PgBouncer releases the **server** connection after each transaction even while
SQLAlchemy retains the client-side connection to PgBouncer. Choose `NullPool` or a small client pool
to control client-connection cost, queueing, and prepared-statement cleanup—not because an idle
client connection pins a server connection. Measure both layers under the real topology.

### PgBouncer Limitations

In transaction mode, behavior depends on whether state is transaction-local or session-local:

| Feature | Problem |
|---------|---------|
| `SET LOCAL` | Works inside the current transaction |
| `SET SESSION` | Unsafe because a later transaction may use another server session |
| Transaction advisory locks (`pg_advisory_xact_lock`) | Work inside one transaction |
| Session advisory locks (`pg_advisory_lock`) | Unsafe because ownership is session-scoped |
| `NOTIFY` | Works as a statement; delivery is committed with the transaction |
| `LISTEN` | Unsafe because registration is session-scoped |
| Temporary tables (`CREATE TEMP TABLE`) | Session-scoped |
| Protocol-level named prepared statements | Supported only when PgBouncer prepared-statement tracking is enabled and sized |
| SQL `PREPARE` / `DEALLOCATE` | Session-scoped and not rewritten by PgBouncer |
| Cursors outside transactions | Session-scoped |

For prepared statements with asyncpg through PgBouncer:

```python
# Cache-control excerpt, not a guarantee of compatibility with an older proxy: SQLAlchemy
# still calls asyncpg prepare even when its prepared-statement cache is disabled.
engine = create_async_engine(
    DATABASE_URL + "?prepared_statement_cache_size=0",  # asyncpg dialect DBAPI option
    connect_args={"statement_cache_size": 0},     # asyncpg-level
)
```

[PgBouncer](https://www.pgbouncer.org/features.html) can track protocol-level named prepared statements when
`max_prepared_statements` is nonzero. If that feature is enabled, test caching and statement naming with the SQLAlchemy asyncpg dialect.
The dialect documents dynamic names and server cleanup requirements; disabling caches alone does
not remove prepare calls or guarantee compatibility with an unconfigured proxy. Verify with repeated transactions
through PgBouncer; success is stable execution without `DuplicatePreparedStatementError` or
`InvalidSQLStatementNameError` after connections are reassigned.

For psycopg3, select its dialect explicitly; `prepare_threshold` is not an asyncpg argument:

```python
PSYCOPG_URL = "postgresql+psycopg://user:pass@pgbouncer-host:6432/mydb"
engine = create_async_engine(
    PSYCOPG_URL,
    connect_args={"prepare_threshold": None},  # disable auto-prepare
)
```

---

## 5. asyncpg's Built-in Pool

asyncpg has its own pool, independent of SQLAlchemy. Use this when you're using asyncpg directly (without SQLAlchemy).

```python
import asyncpg

# Excerpt: define setup_connection below before constructing this pool.
pool = await asyncpg.create_pool(
    dsn="postgresql://user:pass@localhost:5432/mydb",
    min_size=5,                          # initial connections; expiry can reduce idle count
    max_size=20,                         # never more than this
    max_inactive_connection_lifetime=300, # close idle connections after 5 min
    command_timeout=30,                  # default timeout for all queries
    max_queries=50000,                   # recycle connection after N queries
    setup=setup_connection,              # called on each acquisition
)
```

### Per-Connection Setup Hook

`init` runs once when a connection is created; `setup` runs on each acquisition. [asyncpg pool lifecycle](https://magicstack.github.io/asyncpg/current/api/index.html#connection-pools). Release resets
session settings, so reapply them in setup. Register codecs in init:

```python
import json

async def setup_connection(conn):
    # Set default timezone
    await conn.execute("SET TIME ZONE 'UTC'")
    # Set statement timeout
    await conn.execute("SET statement_timeout = '30s'")

async def init_connection(conn):
    # Codec registration belongs to connection creation.
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )

pool = await asyncpg.create_pool(dsn=DSN, init=init_connection, setup=setup_connection)
```

---

## 6. Monitoring the Pool

### SQLAlchemy Pool Events

```python
from sqlalchemy import event
from sqlalchemy.pool import Pool
import logging

logger = logging.getLogger("sqlalchemy.pool")

@event.listens_for(Pool, "checkout")
def on_checkout(dbapi_conn, connection_record, connection_proxy):
    logger.debug("Connection checked out from pool")

@event.listens_for(Pool, "checkin")
def on_checkin(dbapi_conn, connection_record):
    logger.debug("Connection returned to pool")

@event.listens_for(Pool, "connect")
def on_connect(dbapi_conn, connection_record):
    logger.info("New database connection created")

@event.listens_for(Pool, "invalidate")
def on_invalidate(dbapi_conn, connection_record, exception):
    logger.warning("Database connection invalidated", exc_info=exception)
```

### Pool Status

The status methods below apply to QueuePool and AsyncAdaptedQueuePool; NullPool has no
retained-size/checked-out API. Pool event callbacks on an async engine use its `sync_engine`.

```python
# Get pool statistics
pool = engine.pool
print(f"Pool size: {pool.size()}")
print(f"Checked out: {pool.checkedout()}")
print(f"Overflow: {pool.overflow()}")
print(f"Checked in: {pool.checkedin()}")
```

Expose these as metrics (Prometheus, Datadog):

```python
from prometheus_client import Gauge

db_pool_size = Gauge("db_pool_size", "Pool size")
db_pool_checked_out = Gauge("db_pool_checked_out", "Checked out connections")
db_pool_overflow = Gauge("db_pool_overflow", "Overflow connections")

async def update_pool_metrics():
    pool = engine.pool
    db_pool_size.set(pool.size())
    db_pool_checked_out.set(pool.checkedout())
    db_pool_overflow.set(pool.overflow())
```

### PostgreSQL-Side Monitoring

```sql
-- Active connections per application
SELECT application_name, state, count(*)
FROM pg_stat_activity
GROUP BY application_name, state
ORDER BY count DESC;

-- Long-running queries (potential connection hogs)
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE state != 'idle' AND query_start < now() - interval '30 seconds'
ORDER BY duration DESC;

-- Connections approaching max
SELECT count(*) AS active,
       max_conn,
       count(*) * 100 / max_conn AS pct_used
FROM pg_stat_activity,
     (SELECT setting::int AS max_conn FROM pg_settings WHERE name = 'max_connections') x
GROUP BY max_conn;

```

Termination rolls back the target's open transaction and disconnects its client. First use the
read-only query above to identify an exact application PID and verify its database, user,
`backend_type`, state, query, and duration. Never target the current session, an administrator, or a
replication/background worker. Then run the bounded destructive step with that verified literal:

```sql
SELECT pg_terminate_backend(12345) AS terminated
WHERE 12345 <> pg_backend_pid()
  AND EXISTS (
    SELECT 1 FROM pg_stat_activity
    WHERE pid = 12345
      AND backend_type = 'client backend'
      AND usename = 'myapp'
      AND datname = 'myapp'
  );
-- terminated = true means PostgreSQL sent termination; zero rows means the guard refused it.
```

---

## 7. Connection Pool Failure Modes

### Pool Exhaustion

**Symptom**: `TimeoutError: QueuePool limit of size N overflow N reached, connection timed out`

**Causes**:
- Long-running queries holding connections
- Missing `await session.close()` / not using context managers
- Sudden traffic spike
- Pool size too small for the workload

**Fixes**:
```python
# 1. Always use context managers — they guarantee return to pool
async with async_session() as session:
    ...  # session returned even on exception

# 2. Set statement timeout to prevent runaway queries
engine = create_async_engine(
    DATABASE_URL,
    connect_args={"server_settings": {"statement_timeout": "30000"}},
)

# 3. Increase pool size if the workload genuinely needs more connections
# 4. Set query timeouts to prevent connection hogging
```

When the server cancels a statement at this boundary, asyncpg surfaces SQLSTATE `57014`
(`query_canceled`); that is the signal that the server setting, rather than a pool wait, fired.

### Stale Connections (without pre_ping)

**Symptom**: `OperationalError: SSL connection has been closed unexpectedly` or `server closed the connection unexpectedly`

**Cause**: Cloud databases (RDS, Cloud SQL) and proxies silently close idle connections after a timeout.

**Fix**: enable checkout pre-ping when stale idle connections are a risk. A disconnect during an active transaction still needs rollback and whole-operation recovery.

### Connection Leak

**Symptom**: Pool exhausts even with low traffic. Connection count slowly grows. Restart fixes it temporarily.

**Cause**: Code path that acquires a session but never releases it:

```python
# ❌ Connection leak
session = async_session()
result = await session.execute(select(User))
# exception here — session never closed!

# ✅ No leak — context manager guarantees cleanup
async with async_session() as session:
    result = await session.execute(select(User))
    # session closed on exit even if exception
```

**Detection**:

```sql
-- Find connections that have been idle in a transaction for > 5 minutes
SELECT pid, state, now() - xact_start AS tx_duration, query
FROM pg_stat_activity
WHERE state = 'idle in transaction'
AND xact_start < now() - interval '5 minutes';
```

### Thundering Herd on Startup

**Symptom**: App startup causes a spike of connection attempts that overwhelm the database.

**Fix**: SQLAlchemy creates connections lazily by default (first use, not startup). For asyncpg's own pool:

```python
pool = await asyncpg.create_pool(
    dsn=DSN,
    min_size=0,   # start with 0 connections, create on first request
    max_size=20,
)
```

---

## 8. Statement and Query Timeouts

Always set timeouts to prevent slow queries from holding connections and blocking the pool.

### PostgreSQL Statement Timeout

These excerpts use `postgresql+asyncpg://`. asyncpg accepts `server_settings`, not libpq
`options`; the latter belongs to a separately configured `postgresql+psycopg://` engine.
A server statement cancellation yields SQLSTATE `57014`; rollback before reusing its transaction.

```python
# Set per-connection at creation time
engine = create_async_engine(
    DATABASE_URL,
    connect_args={"server_settings": {"statement_timeout": "30000"}},  # asyncpg: ms
)

# Set per-query via SQL
async with session.begin():
    await session.execute(text("SET LOCAL statement_timeout = '5s'"))
    # expensive query here — will raise if it takes > 5s
```

### Lock Timeout

Prevent queries from waiting indefinitely for a lock:

```python
engine = create_async_engine(
    DATABASE_URL,
    connect_args={"server_settings": {"lock_timeout": "5000"}},  # asyncpg: ms
)
```

### Idle in Transaction Timeout

Prevent transactions from staying open indefinitely (a common connection leak source):

```python
engine = create_async_engine(
    DATABASE_URL,
    connect_args={"server_settings": {"idle_in_transaction_session_timeout": "60000"}},
)
```

### asyncpg Command Timeout

```python
pool = await asyncpg.create_pool(
    dsn=DSN,
    command_timeout=30,  # default timeout for all queries (seconds)
)

# Per-query timeout
row = await pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id, timeout=5.0)
```

---

## 9. Production Checklist

```
Pool Configuration:
  ✅ pool_pre_ping evaluated for stale checkouts; in-flight failures still need rollback
  ✅ All process pools × maximum live fleet fit the available server/client budgets
  ✅ pool_recycle selected for a known connection-age policy; replaces only at checkout
  ✅ pool_timeout set (prefer fast failure over long queues)
  ✅ statement_timeout set — prevents runaway queries

Code Patterns:
  ✅ Always use context managers for sessions (async with async_session() as s)
  ✅ One session per concurrent task, including tasks inside one request
  ✅ Engine created once at module level, never per-request
  ✅ engine.dispose() called on shutdown (lifespan context manager)

Monitoring:
  ✅ Pool metrics exposed (size, checked_out, overflow)
  ✅ Alerts on pool exhaustion (checked_out approaching max)
  ✅ Alerts on long-running queries (pg_stat_activity)
  ✅ Alerts on idle-in-transaction connections

PgBouncer (if used):
  ✅ Transaction mode (unless you use session-scoped features)
  ✅ Prepared statements verified against the proxy version, tracking setting and dialect
  ✅ App client pool and proxy server pool measured separately; budgets cover all DB/user pools
```
