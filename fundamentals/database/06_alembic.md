# Alembic — Database Migrations

<!-- length-justification: This canonical migration reference keeps schema/data transitions, branching, multi-database operation, and deployment safety together because each is reviewed as part of one immutable migration history. -->

> **Who this is for**: SQLAlchemy users designing reviewable database transitions from development
> through production rollout.

> **Key insight**: Migrations are reviewed, immutable transition programs rather than authoritative
> diffs from current models.

This deep dive develops one online schema rollout, then provides reference material for setup, autogenerate, data migrations, branching, multi-database, CI/CD integration, and production deployment strategies.

> Read `03` for mappings and transaction ownership; `04` adds the async application path. This file owns both sync and async Alembic setup and the production migration continuation.

---

## 1. Mental Model

```
Your SQLAlchemy Models (Python)         Your Database (PostgreSQL)
         │                                        │
         ▼                                        ▼
    target_metadata                         current schema
         │                                        │
         └────────── alembic autogenerate ────────┘
                            │
                            ▼
              Migration Script (versions/*.py)
                            │
                     alembic upgrade
                            │
                            ▼
              Database schema matches models
```

Alembic is **not** Django's auto-migration system. It generates a *draft* that you review and edit. Autogenerate is a convenience, not an authority.

---

## 2. Setup

### Install

```bash
pip install alembic "sqlalchemy[asyncio]" asyncpg "psycopg[binary]" pytest
```

### Initialize

```bash
# Async project (FastAPI + asyncpg)
alembic init -t async alembic

# Sync project
alembic init alembic
```

This creates:

```
project/
├── alembic/
│   ├── env.py              ← connects to DB, runs migrations
│   ├── script.py.mako      ← template for new migration files
│   └── versions/           ← migration scripts live here
├── alembic.ini             ← configuration file
```

### Configure `alembic.ini`

```ini
# alembic.ini
# Leave blank — set from app config in env.py to avoid hardcoded credentials
sqlalchemy.url =

# Useful: set the migration file naming template
# file_template = %%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s
```

The `file_template` setting controls migration filenames. The default is just the revision hash + slug. Adding a timestamp makes the `versions/` folder chronologically sorted:

```
versions/
├── 2025_03_15_1430-a1b2c3_add_users_table.py
├── 2025_03_17_0900-d4e5f6_add_posts_table.py
├── 2025_03_20_1100-g7h8i9_add_tags.py
```

### Configure `env.py` (Async)

```python
# alembic/env.py
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Import Base so Alembic sees all table metadata
from app.models import Base
from app.config import settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without connecting to the database."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection, target_metadata=target_metadata,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Configure the synchronous driver variant

For the synchronous application in 03, keep the same imports of `context`, `Base`, settings,
logging configuration, `target_metadata`, and `run_migrations_offline()` above. Replace the
async engine imports and online migration functions with this excerpt. Set
`settings.database_url` to `postgresql+psycopg://...`; an asyncpg URL is incompatible with this
synchronous engine. Both variants commit each revision separately, including an enum addition
before a later revision uses it.

```python
from sqlalchemy import create_engine, pool

def run_migrations_online() -> None:
    engine = create_engine(settings.database_url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                transaction_per_migration=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

This is an alternative `env.py` assembly, not code to run after the async version's final dispatch.
The [Alembic environment tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
explains the shared context; [SQLAlchemy's psycopg dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg)
selects the synchronous driver used here.

> **Critical:** Every model file must be imported somewhere that `Base` touches. The standard pattern is `app/models/__init__.py` that imports all models:
>
> ```python
> # app/models/__init__.py
> from .base import Base
> from .user import User
> from .post import Post
> from .tag import Tag
> ```
> If a model isn't imported here, Alembic won't see it and autogenerate will skip it.

---

## 3. Core Commands

```bash
# ── Generate ──────────────────────────────────────────────

# Autogenerate from model diff
alembic revision --autogenerate -m "add users table"

# Empty migration (for custom SQL, data migrations)
alembic revision -m "backfill user tiers"

# ── Apply ─────────────────────────────────────────────────

alembic upgrade head          # apply all pending
alembic upgrade +1            # apply next one
alembic upgrade a1b2c3        # apply up to specific revision

# ── Rollback ──────────────────────────────────────────────

alembic downgrade -1          # roll back one
alembic downgrade a1b2c3      # roll back to specific revision
alembic downgrade base        # roll back everything

# ── Inspect ───────────────────────────────────────────────

alembic current               # what revision is the DB at?
alembic history --verbose     # full migration chain
alembic heads                 # current head revision(s)
alembic branches              # show if there are multiple heads

# ── Preview ───────────────────────────────────────────────

alembic upgrade head --sql    # show SQL without running it
```

---

## 4. Autogenerate — What It Detects (and Doesn't)

| Detected | Not Detected |
|----------|-------------|
| Table create / drop | Table rename |
| Column add / drop | Column rename |
| Column type change | Enum value additions |
| Nullable change | CHECK expression changes; named add/drop requires opt-in plugin |
| Index add / drop | Custom SQL functions / triggers |
| Foreign key add / drop | Row-level security policies |
| Unique constraint changes | Sequence changes |
| Server default changes* | Partial indexes (sometimes) |

\* Server-default comparison is off by default; enable `compare_server_default=True` after testing
on the target schema. Type comparison has been enabled by default since Alembic 1.12.
In Alembic 1.19.2+ named CHECK add/drop detection is off by default. The optional
`alembic.ext.checkconstraint_byname` plugin compares names, never changed expressions. In `env.py`,
the opt-in excerpt is `autogenerate_plugins=["alembic.autogenerate.*", "alembic.ext.checkconstraint_byname"]`
alongside the other `context.configure` arguments. Every CHECK must be named; review the candidate
rather than treating a matching name as matching semantics.
[Official detection limits](https://alembic.sqlalchemy.org/en/latest/autogenerate.html), checked 2026-10-06.

**Always review autogenerated migrations.** They are a starting point, not a finished product.

### Handling Renames

Autogenerate sees a rename as "drop old + create new" — you'll lose data. Fix it manually:

```python
def upgrade() -> None:
    # Autogenerate would do: drop_column("name") + add_column("full_name")
    # Instead:
    op.alter_column("users", "name", new_column_name="full_name")


def downgrade() -> None:
    op.alter_column("users", "full_name", new_column_name="name")
```

---

## 5. Data Migrations

Schema migrations change structure. Data migrations change content. Alembic handles both.

### Backfill Pattern

```python
"""backfill user tiers

Revision ID: c3d4e5f6
Revises: b2c3d4e5
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6"
down_revision = "b2c3d4e5"


def upgrade() -> None:
    # Use raw SQL — ORM models may change later, but this migration is frozen in time
    op.execute("UPDATE users SET tier = 'free' WHERE tier IS NULL")


def downgrade() -> None:
    raise RuntimeError(
        "irreversible data migration: rows that were NULL were not recorded separately"
    )
```

This downgrade fails deliberately: changing every `free` row back to `NULL` would corrupt rows that
were already `free`. A reversible design must record the affected row IDs and old values in a
durable side table before the update; otherwise restore from backup or write a reviewed repair
migration instead of pretending reversal is safe.

> **Rule:** Never import ORM models in migration files. Models evolve; migrations are immutable snapshots. Use `op.execute()` with raw SQL or `sa.table()` / `sa.column()` for type-safe references:

```python
from alembic import op
import sqlalchemy as sa

# Lightweight table reference — no dependency on the ORM model
users = sa.table("users", sa.column("id", sa.Integer), sa.column("tier", sa.String))

def upgrade() -> None:
    op.execute(users.update().where(users.c.tier == None).values(tier="free"))
```

### One online rollout: adding `users.tier`

Assume existing users have `id` and `name`. The old application inserts only those columns.
The new application must assign a tier, but releases overlap: some old replicas can still write
while new replicas are starting. Database revision, application version and data completion are
three independent states. A successful `upgrade head` proves only the first.

| Stage | Writers | Schema / data | Revision and commit boundary |
|---|---|---|---|
| Before | Old inserts omit tier | No tier column | predecessor |
| Expand | Old and new accepted | Nullable tier; old rows are NULL | `tier_expand`, committed |
| Compatible deploy | New writes explicit tier; old still omit it | New reads NULL as free | unchanged |
| Backfill | Compatible writers; drain old replicas/jobs | Old rows filled in committed batches | checkpoint advances separately |
| Validate | Only tier-writing versions remain | No NULL; CHECK validated | validation commits separately |
| Enforce | New versions only | tier NOT NULL | `tier_enforce`, committed |
| Contract later | New versions only | Remove temporary read fallback/checkpoint | later release |

The expand revision excerpt is deliberately small: it changes structure without assigning the
meaning of every existing row. Its short transaction releases the DDL lock before the long backfill.

```python
# Revision tier_expand; imports/revision header follow the generated template.
def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '2s'")
    op.add_column("users", sa.Column("tier", sa.String(20), nullable=True))
```

Nullable ADD COLUMN normally needs an ACCESS EXCLUSIVE lock even without a table rewrite.
If another transaction has read users and remains open, expansion waits for that transaction.
Queued DDL can then delay later readers too. `lock_timeout` makes this attempt fail rather than
building an unbounded queue; rollback the failed revision, identify the blocker, and retry in a
controlled window. A fast catalog change is fast only after its lock has been acquired. Locks last
until transaction completion, so putting the UPDATE in the same revision would retain this lock
through the entire backfill. [ALTER TABLE locking](https://www.postgresql.org/docs/current/sql-altertable.html).

Compatible application behavior is an explanatory excerpt: create users with explicit `tier="free"`;
read old rows as `user.tier or "free"`. Avoid relying on that read fallback to repair stored data.
An old writer can still create another NULL after a complete backfill, so first drain old web
replicas, workers and scheduled jobs before the final sweep and enforcement.

For a large table, run a separate checkpointed job. This SQL is one batch excerpt inside a short
transaction. The job owns a durable single-row `migration_progress(name text PRIMARY KEY,
last_id bigint NOT NULL, upper_id bigint NOT NULL)` record. After old writers drain, initialize
it with a fixed high-water mark, for example `INSERT INTO migration_progress SELECT
'users_tier', 0, COALESCE(max(id), 0) FROM users;`. It serializes each batch using
that row lock. Run the UPDATE and checkpoint in the same transaction so either both survive or
neither does. IDs are increasing positive keys; the job handles historical rows up to a recorded
upper bound captured after old writers drain.

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '10s';
WITH progress AS (
    SELECT last_id, upper_id FROM migration_progress
    WHERE name = 'users_tier' FOR UPDATE
), batch AS (
    SELECT id FROM users WHERE id > (SELECT last_id FROM progress)
      AND id <= (SELECT upper_id FROM progress)
    ORDER BY id LIMIT 1000
), changed AS (
    UPDATE users SET tier = 'free'
    WHERE id IN (SELECT id FROM batch) AND tier IS NULL RETURNING id
)
UPDATE migration_progress
SET last_id = COALESCE((SELECT max(id) FROM batch), last_id)
WHERE name = 'users_tier';
COMMIT;
```

The cursor advances over non-NULL rows too: those rows already satisfy the change. A crash after
UPDATE but before COMMIT rolls back both modifications; restart repeats that batch. A crash after
COMMIT repeats no earlier batch. Never use the maximum updated ID as the only checkpoint: a batch
containing no NULLs would fail to advance. This job assumes no late insert can appear behind the
cursor and no surviving writer can clear a processed tier. After draining old writers, a final
`SELECT count(*) FROM users WHERE tier IS NULL` must be zero; investigate rather than blindly
skipping rows if this assumption fails. Observe rows/batch, batch time, replication/WAL pressure,
lock waits and checkpoint age; slow or pause batches when production latency rises.

With no old writers remaining, enforce through separate committed revisions or job steps. These
are SQL excerpts; each BEGIN/COMMIT represents a distinct transaction:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE users ADD CONSTRAINT users_tier_not_null
    CHECK (tier IS NOT NULL) NOT VALID;
COMMIT;

BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '5min';
ALTER TABLE users VALIDATE CONSTRAINT users_tier_not_null;
COMMIT;

BEGIN;
SET LOCAL lock_timeout = '2s';
ALTER TABLE users ALTER COLUMN tier SET NOT NULL;
ALTER TABLE users DROP CONSTRAINT users_tier_not_null;
COMMIT;
```

NOT VALID avoids scanning old rows when the CHECK is installed, but checks new/changed rows.
VALIDATE scans under SHARE UPDATE EXCLUSIVE, allowing ordinary reads/writes while excluding some
maintenance/DDL. PostgreSQL 12+ can use a validated CHECK proving non-nullness to skip the SET NOT
NULL scan; that final metadata operation still needs ACCESS EXCLUSIVE. Separate transactions
prevent validation from inheriting the earlier strong DDL lock. If validation fails, the constraint
continues guarding new rows: diagnose the offending NULLs, repair and rerun validation. The app
read fallback is removed only in a later release after every database and reader has completed
cutover. [Validation guarantees](https://www.postgresql.org/docs/current/sql-altertable.html).

**Prediction:** the backfill finished, but one old worker is still running. Is enforcement safe?
No: its next INSERT omits tier, becoming NULL and failing CHECK/NOT NULL. Zero NULLs is evidence
about existing rows, not future writers. Drain it or deploy a compatible writer first. A temporary
server default could preserve omitted-column inserts, but explicit NULL still bypasses a default;
that alternative needs its own compatibility test.

An application rollback during expand is usually possible because the old columns remain. After
enforcement, rollback to the old writer is unsafe. Repair forward or redeploy a compatible release.
Dropping tier in a downgrade destroys newly stored choices; migration history cannot reconstruct
them. [Recovery and restore rehearsal](08_backup_and_recovery.md) owns recovery of lost data.


---

## 6. Handling Enums

PostgreSQL enums are a common pain point — Alembic can't add values to existing enums automatically.

### Adding a Value to an Existing Enum

```python
"""add 'enterprise' to user_tier enum

Alembic autogenerate won't detect this.
"""
from alembic import op

def upgrade() -> None:
    # PostgreSQL allows this in a transaction, but the new value cannot be
    # referenced until that transaction commits.
    op.execute("ALTER TYPE user_tier ADD VALUE IF NOT EXISTS 'enterprise'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values
    # You'd need to recreate the type — usually not worth it
    pass
```

> **Gotcha:** Current PostgreSQL permits `ALTER TYPE ... ADD VALUE` inside a transaction, but the
> new enum value cannot be used until commit. Use a subsequent migration with `transaction_per_migration=True` (as in this env.py),
> or separate committed `alembic upgrade <add_value_revision>` and `alembic upgrade head` invocations.
> Separate files alone do not commit when an upgrade runs in one encompassing transaction. Use autocommit only for an older supported PostgreSQL version or a
> migration workflow that you have verified requires it.

For a legacy environment that demonstrably requires autocommit, configure it deliberately. In `env.py`:

```python
context.configure(
    connection=connection,
    target_metadata=target_metadata,
    transaction_per_migration=True,  # one txn per migration, so an AUTOCOMMIT migration is possible
)
```

Then inside the migration:

```python
from alembic import op

def upgrade() -> None:
    # Run outside any transaction — requires AUTOCOMMIT isolation level.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_tier ADD VALUE IF NOT EXISTS 'enterprise'")
```

### Creating a New Enum Column

```python
def upgrade() -> None:
    # Create the type explicitly
    user_tier = sa.Enum("free", "pro", "enterprise", name="user_tier")
    user_tier.create(op.get_bind(), checkfirst=True)

    op.add_column("users", sa.Column("tier", user_tier, nullable=True))
```

---

## 7. Branching and Merging

When multiple developers create migrations in parallel, you get **multiple heads**.

### Detecting the Problem

```bash
$ alembic heads
a1b2c3 (head)   # developer A's migration
d4e5f6 (head)   # developer B's migration

$ alembic upgrade head
ERROR: Multiple head revisions are present; please specify a specific target
```

### Fixing: Merge Migration

```bash
alembic merge -m "merge heads" a1b2c3 d4e5f6
```

This creates a merge migration:

```python
"""merge heads

Revision ID: m1n2o3
Revises: a1b2c3, d4e5f6
"""

revision = "m1n2o3"
down_revision = ("a1b2c3", "d4e5f6")  # tuple = merge point


def upgrade() -> None:
    pass  # no-op unless you need conflict resolution


def downgrade() -> None:
    pass
```

### Prevention: Team Workflow

```
1. Pull main before creating a migration
2. Create migration
3. Pull main again — if a new migration appeared, merge heads
4. Push
```

Or enforce a linear migration chain in CI:

```bash
# CI check: fail if there are multiple heads
heads=$(alembic heads | wc -l)
if [ "$heads" -gt 1 ]; then
    echo "ERROR: Multiple Alembic heads detected. Run: alembic merge -m 'merge heads'"
    exit 1
fi
```

---

## 8. Stamping

`alembic stamp` sets the database's recorded revision **without running any migrations**. Useful for:

- Bringing an existing database under Alembic control
- Recovering from a broken migration state

```bash
# Mark the database as being at revision a1b2c3 (without running anything)
alembic stamp a1b2c3

# Mark as fully up to date
alembic stamp head

# Mark as having no migrations applied
alembic stamp base
```

### Adopting Alembic on an Existing Database

Autogenerate against an already matching database produces an empty revision. Stamping that
empty revision would hide the fact that a fresh database cannot rebuild the application schema.
Generate the full initial revision against an **empty disposable database**, review it, then replay
it into a second empty database. Compare tables, constraints, indexes and server-side objects
against the existing database, accounting for objects outside autogenerate's coverage. Only stamp
an exact baseline that demonstrably matches. If they differ, reconcile through a reviewed repair
rather than claiming equivalence. Use the same baseline for future fresh installations.

Command sequence excerpt; these URLs refer to dedicated disposable databases configured through
Settings `DATABASE_URL`, never the production URL during generation/replay:

```bash
DATABASE_URL="$EMPTY_GENERATION_URL" alembic revision --autogenerate -m "initial schema"
DATABASE_URL="$EMPTY_REPLAY_URL" alembic upgrade head
DATABASE_URL="$EMPTY_REPLAY_URL" alembic check
# Only after catalog and data invariants match the reviewed baseline:
DATABASE_URL="$VERIFIED_EXISTING_URL" alembic stamp <exact_baseline_revision>
```


---

## 9. Multi-Database Migrations

When your app talks to multiple databases (e.g., main + analytics).

### Setup with Named Sections

```ini
# alembic.ini
[alembic]
script_location = alembic/main

[analytics]
script_location = alembic/analytics
```

```bash
# Initialize each
alembic init alembic/main
alembic init alembic/analytics
```

### Separate env.py per Database

Each section gets its own `env.py` that connects to its respective database.

```bash
# Run migrations for a specific database
alembic -n analytics upgrade head
alembic -n alembic upgrade head   # default section
```

---

## 10. Testing Migrations

### Test: reversible schema upgrade → downgrade → upgrade

```python
import os
import subprocess
import uuid

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import make_url


@pytest.fixture
def temporary_database_url():
    admin_conninfo = os.environ["ALEMBIC_TEST_ADMIN_CONNINFO"]
    migration_url = make_url(os.environ["ALEMBIC_TEST_MIGRATION_URL"])
    database_name = f"alembic_test_{uuid.uuid4().hex}"

    with psycopg.connect(
        admin_conninfo, autocommit=True
    ) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
        )

    test_url = migration_url.set(database=database_name).render_as_string(hide_password=False)
    try:
        yield test_url
    finally:
        assert database_name.startswith("alembic_test_")
        with psycopg.connect(
            admin_conninfo, autocommit=True
        ) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    sql.Identifier(database_name)
                )
            )


def test_migrations_roundtrip(temporary_database_url):
    """The fixture creates a unique database and drops it after this test."""
    database_name = temporary_database_url.rsplit("/", 1)[-1]
    assert database_name.startswith("alembic_test_")
    env = {**os.environ, "DATABASE_URL": temporary_database_url}

    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
    subprocess.run(["alembic", "downgrade", "base"], check=True, env=env)
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
```

`ALEMBIC_TEST_ADMIN_CONNINFO` (libpq `postgresql://` or keyword conninfo) must point to a dedicated test cluster role allowed to create databases.
`ALEMBIC_TEST_MIGRATION_URL` points to that same test cluster using `postgresql+asyncpg://`
for the async env.py. These distinct schemes are intentional: psycopg cannot consume a SQLAlchemy
dialect URL. Settings must read `DATABASE_URL` (for example, a pydantic-settings field
`database_url: str`); the fixture changes that environment variable for each subprocess.
The UUID-named database is the isolation mechanism; the prefix assertions guard both destructive
operations. Success is three zero exit codes followed by removal of that exact temporary database.

Run this roundtrip only on reversible histories. For an irreversible backfill, test predecessor →
head with seeded rows and assert preserved IDs/names plus expected tiers, then test a reviewed
forward repair or disposable restore. Downgrade failure is intentional, not a CI defect.

### Assert forward data preservation, not only revision numbers

This integration test excerpt uses the fixture above and a test project's revisions
`users_initial` (id/name only) and `tier_enforce` (the completed tier rollout, including its
backfill job in the test harness). Supply those actual revision identifiers in your project.
It tests migration behavior on preexisting rows rather than invoking a destructive downgrade.
It requires the same dedicated cluster and psycopg library as the fixture.

```python
from sqlalchemy.engine import make_url

def test_existing_users_survive_tier_rollout(temporary_database_url):
    env = {**os.environ, "DATABASE_URL": temporary_database_url}
    subprocess.run(["alembic", "upgrade", "users_initial"], check=True, env=env)
    conninfo = make_url(temporary_database_url).set(
        drivername="postgresql"
    ).render_as_string(hide_password=False)
    with psycopg.connect(conninfo) as connection:
        connection.execute(
            "INSERT INTO users (id, name) VALUES (%s, %s)", (1, "Alice")
        )
    # The project harness must run its separate checkpointed backfill before enforcement.
    subprocess.run(["alembic", "upgrade", "tier_enforce"], check=True, env=env)
    with psycopg.connect(conninfo) as connection:
        assert connection.execute(
            "SELECT id, name, tier FROM users ORDER BY id"
        ).fetchall() == [(1, "Alice", "free")]
```

If the production rollout deliberately keeps the backfill outside Alembic, the integration
harness must call that job between expand and enforce; collapsing those steps is a test-only
arrangement, not the production release procedure. Include a second already populated `pro` row
when testing later backfill reruns, proving the NULL predicate preserves assigned tiers.

### Test: No Pending Migrations

Catch cases where someone changed a model but forgot to generate a migration.

```python
import subprocess

def test_no_pending_migrations(temporary_database_url):
    """Fail if models are out of sync with migrations."""
    env = {**os.environ, "DATABASE_URL": temporary_database_url}
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
    result = subprocess.run(
        ["alembic", "check"], capture_output=True, text=True, check=True, env=env
    )
    assert "No new upgrade operations detected" in result.stdout
```

### Alembic `check` Command (Alembic 1.9+)

```bash
# Fails with exit code 1 if models and migrations are out of sync
alembic check
```

Add this to CI:

```yaml
# .github/workflows/ci.yml
- name: Check for missing migrations
  run: alembic check
```

---

## 11. CI/CD Integration

### GitHub Actions deployment recipe (not executed here)

This fixture assumes a reversible schema history; replace downgrade steps with seeded forward
preservation/repair tests for data migrations. `alembic check` requires the database already at head.

```yaml
name: Database CI

on: [push, pull_request]

jobs:
  migrations:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: testdb
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    env:
      DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/testdb

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - run: pip install -r requirements.txt

      - name: Check for multiple heads
        run: |
          heads=$(alembic heads | wc -l)
          [ "$heads" -le 1 ] || (echo "Multiple heads!" && exit 1)

      - name: Upgrade fresh service database to head
        run: alembic upgrade head

      - name: Check no pending migrations
        run: alembic check

      - name: Downgrade to base
        run: alembic downgrade base

      - name: Upgrade again (roundtrip test)
        run: alembic upgrade head
```

---

## 12. Production Deployment

### Single-instance local migration in Docker Entrypoint

This local convenience assumes exactly one application instance. For replicated deployment, run
the coordinated release job below before starting replicas; concurrent entrypoints race revisions.

```dockerfile
# Dockerfile
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
```

```bash
#!/bin/bash
# entrypoint.sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Migration as a separately coordinated Kubernetes Job (deployment recipe, not executed)

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: myapp-migrate-release-20260904
spec:
  backoffLimit: 3
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: migrate
          image: myapp:latest
          command: ["alembic", "upgrade", "head"]
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: db-credentials
                  key: url
```

Run and wait for this one-shot Job in the release pipeline before rolling out application pods. A
Deployment init container runs once **per pod**, so replicas can migrate concurrently. Job retries
mean every migration must tolerate re-entry after an ambiguous failure; for multiple release
controllers, also serialize with a database advisory-lock protocol.

### Production release review

| Step | Command / Action |
|------|------------------|
| Preview the SQL | `alembic upgrade head --sql > preview.sql` |
| Take a DB snapshot | Verified recovery artifact and restore plan; see [recovery](08_backup_and_recovery.md) |
| Run in a staging environment first | Apply to staging, run tests, then production |
| Check for long locks | Avoid `ALTER TABLE ... ADD COLUMN ... NOT NULL` on large tables without the three-step pattern |
| Monitor migration time | Time the migration; alert if it exceeds expected duration |
| Have a rollback plan | Compatible app rollback, forward repair, or tested isolated restore; never assume downgrade recovers data |

### Avoiding Locks on Large Tables

ACCESS EXCLUSIVE blocks ordinary reads and writes while held. Other lock modes allow some
operations; the size of the table affects scan/rewrite duration, not whether a lock exists.

Distinguish lock acquisition, lock duration and rewrite cost:

| Operation | Cost and lock boundary |
|---|---|
| Nullable ADD COLUMN, DROP COLUMN | Usually metadata-only; still ACCESS EXCLUSIVE |
| Nonvolatile DEFAULT, PostgreSQL 11+ | Often avoids rewrite; strong DDL lock still required |
| Volatile DEFAULT | Computes per row; can rewrite table |
| SET NOT NULL | Scan unless existing validated CHECK proves it; strong lock still required |
| ALTER TYPE | Can rewrite; binary-compatible changes can avoid rewrite |
| CREATE INDEX | Allows reads, blocks writes during build |
| CREATE INDEX CONCURRENTLY | Allows ordinary writes; extra scans/waits, cannot run in transaction block |

Bound acquisition with `SET LOCAL lock_timeout` in transactional migrations. Inspect blockers
using `pg_stat_activity`, `pg_blocking_pids(pid)` and transaction ages; a short SQL statement can
wait behind an hours-old transaction. Cancel/retry the migration through its coordinator rather
than killing an unknown production session. For concurrent index work, use a dedicated autocommit
step and session-level timeout settings with explicit reset/disposal. See the tier rollout for
why validation and enforcement use separate transactions.

```python
# Excerpt: allow ordinary writes during index creation; waits and other locks still exist
def upgrade() -> None:
    # Alembic temporarily enters autocommit without corrupting its transaction state.
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_orders_created_at",
            "orders",
            ["created_at"],
            postgresql_concurrently=True,
        )
```

If concurrent creation fails, PostgreSQL may leave an invalid index. Check
`pg_index.indisvalid`; drop that exact invalid index with `DROP INDEX CONCURRENTLY` in an autocommit
block, fix the cause, and retry.

> **PostgreSQL 12+:** apply each of the following steps in its own committed revision/transaction, after draining incompatible writers, as developed in §5. Running them in one transaction retains the first ACCESS EXCLUSIVE lock throughout validation:
>
> ```python
> # 1. NOT VALID: no initial scan; strong DDL lock, new/changed rows checked
> op.execute("ALTER TABLE users ADD CONSTRAINT users_tier_not_null CHECK (tier IS NOT NULL) NOT VALID")
> # 2. Validate it — scans existing rows but takes only a SHARE UPDATE EXCLUSIVE lock (reads/writes continue)
> op.execute("ALTER TABLE users VALIDATE CONSTRAINT users_tier_not_null")
> # 3. SET NOT NULL — PG 12+ uses the validated CHECK to skip its own full scan; then drop the now-redundant CHECK
> op.alter_column("users", "tier", nullable=False)
> op.execute("ALTER TABLE users DROP CONSTRAINT users_tier_not_null")
> ```
>
> Pre-12, `SET NOT NULL` always rescans the whole table under an `ACCESS EXCLUSIVE` lock — there is no non-blocking path.

---

## 13. Common Operations Reference

### Add a Column

```python
op.add_column("users", sa.Column("bio", sa.Text(), nullable=True))
```

### Drop a Column

```python
op.drop_column("users", "bio")
```

### Rename a Column

```python
op.alter_column("users", "name", new_column_name="full_name")
```

### Change Column Type

```python
op.alter_column(
    "users", "age",
    type_=sa.SmallInteger(),
    existing_type=sa.Integer(),
)
```

### Add an Index

```python
op.create_index("ix_users_email", "users", ["email"], unique=True)
```

### Add a Foreign Key

```python
op.create_foreign_key(
    "fk_posts_author_id",
    "posts", "users",
    ["author_id"], ["id"],
    ondelete="CASCADE",
)
```

### Create a Table

```python
op.create_table(
    "tags",
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(50), nullable=False, unique=True),
    sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
)
```

### Drop a Table

```python
op.drop_table("tags")
```

### Execute Raw SQL

```python
op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
op.execute("UPDATE users SET status = 'active' WHERE status IS NULL")
```

### Bulk Insert (in data migration)

```python
from alembic import op
import sqlalchemy as sa
from datetime import UTC, datetime

roles_table = sa.table(
    "roles",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("created_at", sa.DateTime(timezone=True)),
)

def upgrade() -> None:
    op.bulk_insert(roles_table, [
        {"id": 1, "name": "admin", "created_at": datetime.now(UTC)},
        {"id": 2, "name": "editor", "created_at": datetime.now(UTC)},
        {"id": 3, "name": "viewer", "created_at": datetime.now(UTC)},
    ])
```

---

## 14. Troubleshooting

### "Target database is not up to date"

```bash
$ alembic revision --autogenerate -m "new migration"
ERROR: Target database is not up to date.
```

**Fix:** Apply pending migrations first, then generate.

```bash
alembic upgrade head
alembic revision --autogenerate -m "new migration"
```

### "Can't locate revision"

```bash
$ alembic upgrade head
ERROR: Can't locate revision identified by 'a1b2c3'
```

**Cause:** A migration file was deleted but the `alembic_version` table still references it.

**Recovery is a schema-forensics task, not a generic stamp command.** Take a backup, inspect
`alembic current` and the live catalog, and compare the live schema with the candidate revision's
upgrade operations. If they differ, write a repair migration. Stamp only when that comparison proves
the schema already matches one exact revision.

```bash
# Check what the DB thinks it's at
alembic current

# After backup and an exact schema/revision comparison:
alembic stamp <verified_matching_revision>
alembic current
alembic check
```

### "Multiple heads"

```bash
$ alembic upgrade head
ERROR: Multiple head revisions are present
```

**Fix:**

```bash
alembic merge -m "merge heads"
alembic upgrade head
```

### Migration generated but nothing changed

Autogenerate might create empty migrations if:
- Your models import `Base` from the wrong location
- `env.py` doesn't import all model modules
- You have tables created outside of SQLAlchemy (Alembic compares against `target_metadata` only)

Check `env.py`:
```python
# This must import ALL model modules
from app.models import Base  # make sure __init__.py imports everything
target_metadata = Base.metadata
```

### Autogenerate creates duplicate table operations

When models are imported multiple times through different paths, metadata can get duplicated.

**Fix:** Import `Base` from exactly one location. Every model inherits from the same `Base`.
