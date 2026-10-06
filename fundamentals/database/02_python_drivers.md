# Python Database Drivers — psycopg3 and asyncpg

<!-- length-justification: This is the canonical low-level PostgreSQL driver reference; the parallel sync and async examples stay together so protocol, parameterization, transaction, and bulk-I/O differences remain directly comparable. -->

> **Who this is for**: Python backend engineers choosing or directly using psycopg or asyncpg below
> an ORM.

> **Key insight**: The driver owns protocol, connection, and transaction mechanics beneath
> higher-level database APIs.

> **What is a driver?** A database driver is the low-level library that speaks the database wire protocol. SQLAlchemy and other ORMs sit on top of a driver — they don't communicate with PostgreSQL themselves, they delegate to psycopg3 or asyncpg.

```
Your code (FastAPI endpoint)
    ↓
ORM (SQLAlchemy)          ← optional layer
    ↓
Driver (psycopg3 / asyncpg)
    ↓
PostgreSQL (wire protocol)
```

You'll usually use a driver indirectly through SQLAlchemy. But understanding drivers directly helps you:
- Write raw SQL for performance-critical paths
- Understand what SQLAlchemy does under the hood
- Debug connection issues
- Use drivers in scripts or tools where an ORM is overkill

---

## 1. psycopg3 (psycopg)

psycopg3 is the third major version of the most widely used Python PostgreSQL driver. It supports both synchronous and async usage.

### Install

```bash
pip install "psycopg[binary]"       # binary wheel — bundles client libraries; choose packaging deliberately
pip install psycopg               # pure Python fallback
pip install "psycopg[binary,pool]"  # with the separate psycopg_pool package
```

### 1.1 Synchronous psycopg3

Use sync psycopg3 for scripts, CLIs, background jobs, or anywhere you're not in an async framework.

#### Connecting and Executing

```python
import os
import psycopg

# DATABASE_URL points to a disposable PostgreSQL database for this exercise.
with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    with conn.cursor() as cur:
        cur.execute("CREATE TEMP TABLE users (id int PRIMARY KEY, email text, name text)")
        cur.execute(
            "INSERT INTO users VALUES (%s, %s, %s)",
            (1, "alice@example.com", "Alice"),
        )
        cur.execute("SELECT id, email, name FROM users WHERE id = %s", (1,))
        row = cur.fetchone()
        print(row)  # (1, 'alice@example.com', 'Alice')
```

The temporary table disappears with the connection. The visible tuple proves connection,
parameter binding, transaction, and row decoding; a missing or bad
`DATABASE_URL` fails before any permanent schema is changed.

#### Parameters

psycopg3 uses `%s` as the placeholder for all types (not `%d`, `%f`, etc.):

```python
# ✅ Parameterized — safe
cur.execute("SELECT * FROM users WHERE email = %s AND is_active = %s", ("alice@example.com", True))

```

An unsafe interpolated query would turn attacker input such as `x' OR TRUE --` into the inert
text `SELECT * FROM users WHERE email = 'x' OR TRUE --'`. Do not make that shape executable;
the parameterized call above keeps the value separate from SQL syntax.

Named parameters:

```python
cur.execute(
    "SELECT * FROM users WHERE email = %(email)s",
    {"email": "alice@example.com"},
)
```

#### Fetching Results

```python
with conn.cursor() as cur:
    cur.execute("SELECT id, email, name FROM users LIMIT 10")

    # All rows as list of tuples
    rows = cur.fetchall()       # [(1, 'a@b.com', 'Alice'), ...]

    # The same result is exhausted after fetchall().
    row = cur.fetchone()        # None
    rows = cur.fetchmany(5)     # []

    # Reexecute before demonstrating incremental reads.
    cur.execute("SELECT id, email, name FROM users ORDER BY id LIMIT 10")
    row = cur.fetchone()        # first row, or None when result is empty
    rows = cur.fetchmany(5)     # up to 5 remaining rows
```

#### Bind values; compose allowed identifiers separately

A placeholder binds a value, not an SQL table/column name. `SELECT %s FROM users` selects a constant value for each row; it does not dynamically choose a column. For a caller-selected report field, validate the choice, then quote it with psycopg's identifier composer. This excerpt uses the `conn` and users fixture from earlier:

```python
from psycopg import sql

field = "email"  # supplied by a caller
if field not in {"email", "name"}:
    raise ValueError("unsupported report field")
with conn.cursor() as cur:
    cur.execute(
        sql.SQL("SELECT {} FROM {} WHERE id = %s").format(
            sql.Identifier(field), sql.Identifier("users")
        ),
        (1,),
    )
    print(cur.fetchone())
```

The allowlist controls what the report may expose; quoting controls SQL syntax. A value such as `email; DROP TABLE users` fails the allowlist rather than becoming executable SQL. Continue to bind data values even when the identifier is composed. [SQL composition](https://www.psycopg.org/psycopg3/docs/api/sql.html).

#### Dictionary Rows (Row Factories)

By default you get tuples. Use a row factory for named access:

```python
from psycopg.rows import dict_row, namedtuple_row, class_row

# Dict rows
with psycopg.connect(connstr, row_factory=dict_row) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT id, email FROM users")
        row = cur.fetchone()
        print(row["email"])  # 'alice@example.com'

# Named tuple rows
with psycopg.connect(connstr, row_factory=namedtuple_row) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT id, email FROM users")
        row = cur.fetchone()
        print(row.email)  # 'alice@example.com'

# Per-cursor override
with conn.cursor(row_factory=dict_row) as cur:
    ...
```

#### Transactions

psycopg3 is **autocommit=False by default** — every operation is in a transaction.

```python
# Commit explicitly
with psycopg.connect(connstr) as conn:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO users (email, name) VALUES (%s, %s)", ("a@b.com", "Alice"))
        cur.execute("INSERT INTO users (email, name) VALUES (%s, %s)", ("x@y.com", "Bob"))
    conn.commit()
```

With context managers, `conn.commit()` is called automatically on clean exit, `conn.rollback()` on exception:

```python
with psycopg.connect(connstr) as conn:
    conn.execute("INSERT INTO users (email, name) VALUES (%s, %s)", ("a@b.com", "Alice"))
    # conn.__exit__ calls commit() on success, rollback() on exception
```

Explicit rollback and savepoints:

```python
with psycopg.connect(connstr) as conn:
    try:
        conn.execute("UPDATE accounts SET balance = balance - 100 WHERE id = 1")
        conn.execute("UPDATE accounts SET balance = balance + 100 WHERE id = 2")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

Autocommit mode (each statement is its own transaction):

```python
with psycopg.connect(connstr, autocommit=True) as conn:
    conn.execute("VACUUM")  # requires autocommit — cannot run inside a transaction
```

#### RETURNING Clause

```python
with conn.cursor() as cur:
    cur.execute(
        "INSERT INTO users (email, name) VALUES (%s, %s) RETURNING id, created_at",
        ("alice@example.com", "Alice"),
    )
    row = cur.fetchone()
    print(row)  # (42, datetime(2024, ...))
```

#### Bulk Insert with `executemany` and COPY

```python
# executemany — one statement, multiple parameter sets
users_data = [("a@b.com", "Alice"), ("x@y.com", "Bob"), ("q@r.com", "Carol")]

with conn.cursor() as cur:
    cur.executemany(
        "INSERT INTO users (email, name) VALUES (%s, %s)",
        users_data,
    )
conn.commit()
```

For maximum performance, use `COPY`:

```python
with conn.cursor() as cur:
    with cur.copy("COPY users (email, name) FROM STDIN") as copy:
        for email, name in users_data:
            copy.write_row((email, name))
conn.commit()
```

`COPY` reduces protocol round trips and per-statement overhead, so it is often materially faster than
`executemany` for large batches. Measure with your row width, constraints, indexes, transaction size,
network placement, server, and driver versions; no fixed multiplier transfers across workloads.

#### Keep import and export memory bounded

A regular client cursor may buffer the complete result even when the code calls fetchmany(). A **named server cursor** retains the result position on PostgreSQL and transfers batches. Keep its connection and transaction open until iteration finishes; committing or returning the connection early invalidates the ordinary non-holdable cursor. This excerpt uses an existing non-autocommit `conn` (as in the baseline), users table, and an output path in a disposable directory. An autocommit connection must instead wrap the cursor in an explicit transaction:

```python
import csv

with open("users_export.csv", "w", newline="") as output:
    writer = csv.writer(output)
    with conn.cursor(name="users_export") as cur:
        cur.execute("SELECT id, email, name FROM users ORDER BY id")
        while batch := cur.fetchmany(500):
            writer.writerows(batch)
# Caller commits or closes only after this cursor has closed.
```

Only the current batch is held by this loop, rather than building a list of all users. The transaction can retain a snapshot while the cursor is open, so set an export deadline, close it on cancellation, and monitor long-running transactions. A file consumer that accumulates every batch would defeat the bound.

For imports, a generator plus COPY avoids materializing all input rows. This excerpt imports that CSV into an independently created `users_import(id INTEGER, email TEXT, name TEXT)` table. Do not copy back into users without deliberately choosing conflict/identity semantics:

```python
import csv

def imported_rows(path):
    with open(path, newline="") as source:
        for row in csv.reader(source):
            yield int(row[0]), row[1], row[2]

with conn.transaction():
    with conn.cursor() as cur:
        with cur.copy("COPY users_import (id, email, name) FROM STDIN") as copy:
            for row in imported_rows("users_export.csv"):
                copy.write_row(row)
```

The source yields one row at a time, while psycopg streams COPY protocol buffers; memory does not grow with total row count. CSV structure and field lengths still need input limits, and converting the ID can fail. That exception leaves the transaction context and rolls back the import. The shown policy is one atomic import; for very large jobs, use a staging table plus bounded committed chunks and an explicit checkpoint/retry policy. Keep the source, COPY context, and connection alive together; an external file write is not rolled back by a database rollback. [Server cursors](https://www.psycopg.org/psycopg3/docs/advanced/cursors.html#server-side-cursors), [COPY streaming](https://www.psycopg.org/psycopg3/docs/basic/copy.html).

#### Connection Pool (sync)

```python
from psycopg_pool import ConnectionPool

pool = ConnectionPool(
    conninfo="postgresql://user:pass@localhost:5432/mydb",
    min_size=2,
    max_size=10,
)

# Use the pool
with pool.connection() as conn:
    result = conn.execute("SELECT COUNT(*) FROM users").fetchone()
    print(result[0])

# Close when done
pool.close()
```

---

### 1.2 Async psycopg3

Same API, but with `await`. Use in FastAPI, asyncio scripts, or anywhere you're in an async context.

```python
import psycopg

# Single async connection
async with await psycopg.AsyncConnection.connect(connstr) as conn:
    async with conn.cursor() as cur:
        await cur.execute("SELECT id, email FROM users WHERE id = %s", (1,))
        row = await cur.fetchone()
        print(row)
```

#### Async Pool with FastAPI

Integration excerpt: requires `DATABASE_URL`, the users schema from 01, and a FastAPI application module. Pool creation/shutdown belongs to application lifespan; request dependencies borrow and return connections. The full deployment and sizing continuation is in [05](05_connection_pooling.md).

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from psycopg_pool import AsyncConnectionPool

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = AsyncConnectionPool(
        conninfo="postgresql://user:pass@localhost:5432/mydb",
        min_size=2,
        max_size=10,
        open=False,  # don't block during __init__
    )
    await app.state.db_pool.open()
    yield
    await app.state.db_pool.close()

app = FastAPI(lifespan=lifespan)


def get_pool(request: Request) -> AsyncConnectionPool:
    return request.app.state.db_pool
```

#### CRUD with Async psycopg3

```python
from fastapi import Depends, HTTPException
from psycopg.rows import dict_row

@app.get("/users/{user_id}")
async def get_user(user_id: int, pool: AsyncConnectionPool = Depends(get_pool)):
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, email, name FROM users WHERE id = %s", (user_id,)
            )
            row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row


@app.post("/users")
async def create_user(data: UserCreate, pool: AsyncConnectionPool = Depends(get_pool)):
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "INSERT INTO users (email, name) VALUES (%s, %s) RETURNING id, email, name",
                (data.email, data.name),
            )
            row = await cur.fetchone()
    return row


@app.get("/users")
async def list_users(
    limit: int = 20,
    offset: int = 0,
    pool: AsyncConnectionPool = Depends(get_pool),
):
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT id, email, name FROM users ORDER BY id LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = await cur.fetchall()
    return rows
```

#### Async Transactions

```python
async with pool.connection() as conn:
    async with conn.transaction():
        await conn.execute(
            "UPDATE accounts SET balance = balance - %s WHERE id = %s",
            (amount, from_id),
        )
        await conn.execute(
            "UPDATE accounts SET balance = balance + %s WHERE id = %s",
            (amount, to_id),
        )
        # auto-commits on exit, rolls back on exception
```

#### Async COPY (Bulk Insert)

```python
async with pool.connection() as conn:
    async with conn.cursor() as cur:
        async with cur.copy("COPY users (email, name) FROM STDIN") as copy:
            for email, name in users_data:
                await copy.write_row((email, name))
```

---

## 2. asyncpg

asyncpg is a PostgreSQL driver with an asyncio-native API and binary type adaptation. Both asyncpg and psycopg can use binary adaptation and COPY; protocol support alone does not establish which is faster. Measure the same queries, row conversion, network path, pool concurrency, and COPY format on your workload.

### Install

```bash
pip install asyncpg
```

### 2.1 Connection and Pool

```python
import asyncpg

# Single connection (for scripts)
conn = await asyncpg.connect("postgresql://user:pass@localhost:5432/mydb")
await conn.close()

# Connection pool (for applications)
pool = await asyncpg.create_pool(
    dsn="postgresql://user:pass@localhost:5432/mydb",
    min_size=5,      # create initially; idle expiry can close connections later
    max_size=20,     # max connections
    command_timeout=30,
)
await pool.close()
```

### 2.2 Parameters

asyncpg uses `$1`, `$2`, ... (PostgreSQL's native parameter format):

```python
# ✅ Parameterized
row = await conn.fetchrow("SELECT * FROM users WHERE email = $1", "alice@example.com")

# ✅ Multiple parameters
row = await conn.fetchrow(
    "SELECT * FROM users WHERE email = $1 AND is_active = $2",
    "alice@example.com", True,
)

```

The same attack against an interpolated asyncpg query changes SQL structure. Keep `$1` binding as
the only runnable form so attacker-controlled text remains a value rather than becoming SQL.

### 2.3 Fetch Methods

| Method | Returns | Use case |
|--------|---------|----------|
| `fetch(query, *args)` | `list[Record]` | Multiple rows |
| `fetchrow(query, *args)` | `Record \| None` | Single row |
| `fetchval(query, *args, column=0)` | Single value | Scalar (`SELECT COUNT(*)`) |
| `execute(query, *args)` | Status string (`"INSERT 0 1"`) | INSERT/UPDATE/DELETE |
| `executemany(query, args_list)` | None | Batch operations |

```python
# Multiple rows
users = await pool.fetch("SELECT id, email FROM users ORDER BY id LIMIT 100")
for user in users:
    print(user["id"], user["email"])  # key access; stock Record has no row.email notation

# Single row
user = await pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
if user is None:
    raise HTTPException(status_code=404)
return dict(user)

# Scalar value
count = await pool.fetchval("SELECT COUNT(*) FROM users WHERE is_active = $1", True)

# Execute (no return data needed)
status = await pool.execute(
    "UPDATE users SET is_active = $1 WHERE id = $2", False, user_id
)
# status = "UPDATE 1"
```

### 2.4 asyncpg.Record

`asyncpg.Record` is tuple-like and dict-like:

```python
row = await pool.fetchrow("SELECT id, email, name FROM users WHERE id = $1", 1)

# Access by column name
print(row["email"])         # 'alice@example.com'

# Access by index
print(row[1])               # 'alice@example.com'

# Convert to dict
user_dict = dict(row)       # {"id": 1, "email": "...", "name": "..."}

# Check if None
if row is None: ...         # no row found
```

### 2.5 FastAPI Integration

Integration excerpt: supply `DATABASE_URL`, install FastAPI, and create the users schema before running this app. The examples illustrate driver ownership; production authentication, request schemas, and response error mapping are outside this database lesson.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
import asyncpg

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db_pool = await asyncpg.create_pool(
        dsn="postgresql://user:pass@localhost:5432/mydb",
        min_size=5,
        max_size=20,
    )
    yield
    await app.state.db_pool.close()

app = FastAPI(lifespan=lifespan)


def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.db_pool


@app.get("/users/{user_id}")
async def get_user(user_id: int, pool: asyncpg.Pool = Depends(get_pool)):
    row = await pool.fetchrow(
        "SELECT id, email, name FROM users WHERE id = $1", user_id
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)


@app.post("/users", status_code=201)
async def create_user(data: UserCreate, pool: asyncpg.Pool = Depends(get_pool)):
    try:
        row = await pool.fetchrow(
            "INSERT INTO users (email, name) VALUES ($1, $2) RETURNING id, email, name",
            data.email, data.name,
        )
        return dict(row)
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail="Email already registered")
```

### 2.6 Transactions

```python
# Simple transaction via acquire
async with pool.acquire() as conn:
    async with conn.transaction():
        await conn.execute(
            "UPDATE accounts SET balance = balance - $1 WHERE id = $2",
            amount, from_id,
        )
        await conn.execute(
            "UPDATE accounts SET balance = balance + $1 WHERE id = $2",
            amount, to_id,
        )
        # commits on exit, rolls back on exception

# Nested transaction (savepoint): integration excerpt; logs(msg), users and duplicate must exist.
async with pool.acquire() as conn:
    async with conn.transaction():
        # outer transaction
        await conn.execute("INSERT INTO logs (msg) VALUES ($1)", "start")

        try:
            async with conn.transaction():
                # The exception must leave this context so it rolls back to SAVEPOINT.
                await conn.execute("INSERT INTO users (email, name) VALUES ($1, $2)", duplicate, "Duplicate")
        except asyncpg.UniqueViolationError:
            pass  # rollback completed; outer transaction is usable again

        await conn.execute("INSERT INTO logs (msg) VALUES ($1)", "done")
```

### 2.7 Bulk Insert with asyncpg

asyncpg exposes PostgreSQL's binary `COPY` protocol directly:

```python
# copy_records_to_table — fastest possible bulk insert
records = [(f"user{i}@example.com", f"User {i}") for i in range(100_000)]

async with pool.acquire() as conn:
    await conn.copy_records_to_table(
        "users",
        records=records,
        columns=["email", "name"],
    )
```

Benchmark all three methods against the same disposable table and transaction boundary, recording
row count/width, constraints and indexes, client/server versions, network placement, and server
resources. Report rows per second and p95 run time across repeated trials. The stable expectation is
that binary `COPY` avoids many round trips; the actual wall-clock gap is environment-specific.

### 2.8 asyncpg-Specific Features

#### Prepared Statements

asyncpg automatically prepares statements on first use. You can also do it explicitly:

```python
# Explicit prepared statement — useful for queries run thousands of times
stmt = await conn.prepare("SELECT * FROM users WHERE id = $1")
for user_id in user_ids:
    row = await stmt.fetchrow(user_id)
```

#### Type Codecs

asyncpg understands PostgreSQL types natively. UUIDs come back as `uuid.UUID`, timestamps as `datetime`, etc.

```python
# Custom codec for a type you define
await conn.set_type_codec(
    "jsonb",
    encoder=json.dumps,
    decoder=json.loads,
    schema="pg_catalog",
)
```

#### Listeners (LISTEN/NOTIFY)

```python
# Subscribe to a PostgreSQL channel
await conn.add_listener("events_channel", callback)

# In another connection
await conn.execute("NOTIFY events_channel, 'user_created:42'")
```

### 2.9 Error Handling

Integration excerpt: inside an async FastAPI handler with `pool`, validated `email` and `name`. Each pool.execute acquisition owns this individual statement; for a multi-statement operation, catch errors outside its explicit transaction context.

asyncpg has typed exceptions for PostgreSQL error codes:

```python
import asyncpg
import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)

try:
    await pool.execute("INSERT INTO users (email, name) VALUES ($1, $2)", email, name)
except asyncpg.UniqueViolationError:
    raise HTTPException(409, "Email already exists")
except asyncpg.ForeignKeyViolationError:
    raise HTTPException(400, "Referenced record does not exist")
except asyncpg.NotNullViolationError:
    raise HTTPException(400, "Required field missing")
except asyncpg.PostgresError as e:
    # Catch any other PostgreSQL error
    logger.error("Database error sqlstate=%s", e.sqlstate)
    raise HTTPException(500, "Database error")
```

---

## 3. psycopg3 vs asyncpg — Comparison

| Feature | psycopg3 | asyncpg |
|---------|----------|---------|
| Sync support | Yes (native) | No |
| Async support | Yes | Yes (native, optimized) |
| Performance (async) | Measure matched workloads | Measure matched workloads |
| Parameter style | `%s` (standard DB-API) | `$1`, `$2`, ... (PostgreSQL native) |
| Row type | tuple / dict / namedtuple (configurable) | `asyncpg.Record` (tuple+dict-like) |
| COPY support | Text and binary COPY | Binary COPY via copy_records_to_table |
| SQLAlchemy backend | `psycopg` (recommended for new projects) | `asyncpg` |
| Typed exceptions | SQLSTATE classes and `sqlstate` | SQLSTATE classes and `sqlstate` |
| Connection pool | `psycopg_pool` (separate package) | Built-in |
| Python version | Check selected release metadata | Check selected release metadata |
| Type codecs | Good | Extensive, binary-level |

### Which to Choose?

**Use psycopg3 when:**
- You need both sync and async in the same project
- You're using SQLAlchemy with psycopg3 backend (modern, actively maintained)
- You want DB-API 2.0 compatibility (standard Python DB interface)
- You're coming from psycopg2 and want a familiar API

**Use asyncpg when:**
- Pure async application (FastAPI, asyncio)
- Your matched workload benchmark favors its API and adaptation costs
- You want the simplest possible async code without adapting from sync
- You're doing heavy bulk operations and want binary COPY

**In practice**: psycopg supports both sync and async plus DB-API compatibility; asyncpg supplies an asyncio-native PostgreSQL API. Either works behind SQLAlchemy. Select by required APIs, packaging, deployment constraints, and measured performance, rather than assuming a universal winner. [Psycopg COPY](https://www.psycopg.org/psycopg3/docs/basic/copy.html).

---

## 4. Raw Drivers vs ORM — When to Use Each

| Situation | Use |
|-----------|-----|
| Rapid CRUD app development | SQLAlchemy ORM |
| Complex domain model with many relationships | SQLAlchemy ORM |
| Team prefers Python over SQL | SQLAlchemy ORM |
| Reporting / analytics queries | Raw SQL via driver |
| Bulk insert | Driver COPY after measuring transaction size and conversion cost |
| Scripting / one-off migrations | psycopg3 or asyncpg directly |
| Performance-sensitive read endpoints | Profile ORM, Core, and raw driver on the same workload |
| You need maximum control over SQL | Raw driver |

> You don't have to choose one. In a SQLAlchemy app, unwrap the driver connection only inside the
> owning SQLAlchemy connection/transaction scope:
>
> ```python
> async with engine.begin() as async_connection:
>     adapter = await async_connection.get_raw_connection()
>     asyncpg_connection = adapter.driver_connection
>     # Driver-only calls belong here; SQLAlchemy still owns commit/rollback and close.
> ```

### Diagnose psycopg errors after transaction recovery

Psycopg 3 uses `sqlstate`, rather than psycopg2's `pgcode`. Catch a typed error outside the transaction context so rollback has completed before subsequent SQL. This excerpt requires an existing connection and the users schema:

```python
from psycopg import errors

try:
    with conn.transaction():
        conn.execute("INSERT INTO users (email, name) VALUES (%s, %s)",
                     ("alice@example.com", "Duplicate"))
except errors.UniqueViolation as exc:
    print(exc.sqlstate)  # 23505
    # Map the known constraint to a domain conflict; avoid logging submitted data.
```

A statement failure leaves an explicit PostgreSQL transaction unusable until rollback. Catching inside the transaction without a savepoint would suppress the signal the context needs for rollback. [Psycopg error diagnostics](https://www.psycopg.org/psycopg3/docs/api/errors.html).
