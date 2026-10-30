# Database

> Learn PostgreSQL access in Python backends, from relational rows and transactions through drivers, ORMs, migrations, capacity, recovery and access controls.

Assumed knowledge: basic Python and ordinary command-line use. SQL is taught in 01; async and FastAPI branches require the linked prerequisite lessons. Examples use PostgreSQL 15+ semantics, SQLAlchemy 2.x style, Psycopg 3 and asyncpg. Cluster installation, sharding, HA orchestration and provider-specific failover are outside this collection; production operation still requires tested recovery and access boundaries.

[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15+-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0+-D71F00.svg)](https://www.sqlalchemy.org)
[![asyncpg](https://img.shields.io/badge/asyncpg-0.29+-2E6FA3.svg)](https://github.com/MagicStack/asyncpg)
[![Alembic](https://img.shields.io/badge/Alembic-1.x-6BA81E.svg)](https://alembic.sqlalchemy.org)

---

## Contents

| File | Topic | What you'll learn |
|------|-------|-------------------|
| [01_databases_and_schemas.md](01_databases_and_schemas.md) | Foundations | PostgreSQL vs SQLite, schemas, data types, constraints, indexes, transactions, ACID, SQL basics |
| [02_python_drivers.md](02_python_drivers.md) | Drivers | psycopg3 (sync + async), asyncpg — raw database access, bulk insert, COPY protocol |
| [03_sqlalchemy_orm.md](03_sqlalchemy_orm.md) | ORM | SQLAlchemy 2.0 models, relationships, sync session patterns, basic Alembic setup |
| [04_async_sqlalchemy.md](04_async_sqlalchemy.md) | Async SQLAlchemy | Async engine/session, FastAPI integration, CRUD, transactions, eager loading, common mistakes |
| [05_connection_pooling.md](05_connection_pooling.md) | Connection Pooling | Pool sizing math, SQLAlchemy pool config, PgBouncer, asyncpg pool, failure modes |
| [06_alembic.md](06_alembic.md) | Alembic Deep-Dive | Data migrations, enum handling, branching/merging, stamping, multi-DB, CI/CD, production deployment, lock-safe patterns |
| [07_sqlmodel_decision_guide.md](07_sqlmodel_decision_guide.md) | SQLModel Decision Guide | Combined SQLAlchemy/Pydantic models, table vs data roles, and when direct SQLAlchemy is clearer |
| [08_backup_and_recovery.md](08_backup_and_recovery.md) | Recovery | RPO/RTO, logical and physical backups, PITR, disposable restore rehearsal |
| [09_postgresql_operations.md](09_postgresql_operations.md) | Operations | MVCC version retention, autovacuum, long transactions, statistics and replica freshness |
| [10_database_access_security.md](10_database_access_security.md) | Access Security | Runtime versus migration authority, grants, future objects and verified driver TLS |
| [11_query_performance.md](11_query_performance.md) | Query performance | Plans, indexes, pagination, ORM query counts and benchmark hygiene |
| [12_data_modeling_and_constraints.md](12_data_modeling_and_constraints.md) | Modeling | Constraints, state transitions, history, soft deletes and JSONB |
| [13_multi_tenancy.md](13_multi_tenancy.md) | Tenancy | Isolation models, row policies, noisy neighbors and tenant lifecycle operations |

---

## Learning Path

**New to databases** → Start with `01` (foundations) then `03` (ORM concepts). Milestone: the
synchronous baseline prints `1 alice@example.com`; stop there when you only need one mapped unit of
work. Continue to drivers, async access, pooling, or migrations when that requirement appears.

**Know SQL, new to Python DB libs** → Start with `02` (drivers) or `03` (SQLAlchemy). The driver
branch succeeds when its temporary-table query returns `(1, 'alice@example.com', 'Alice')`; the ORM
branch succeeds when the mapped object prints. Stop after the chosen branch unless you need the
other abstraction.

**Choosing SQLModel** → Read `07` after `03` to compare reduced schema glue with direct SQLAlchemy control.

**Building a FastAPI app** → Read `03` for models, then `04` for async patterns, then `06` for migrations.

**Performance / production concerns** → Read `05` for measured capacity and overload diagnosis, then `09` for maintenance and replica freshness. Before shipping, follow `06` → `08` → `10` for compatible changes, recovery rehearsal and access controls. Stop when you can explain a pool ceiling, diagnose a retained snapshot, restore a disposable database and verify runtime privileges and TLS.

**Migration workflows** → Read `03` for mapping and transaction prerequisites, then `06` for setup, reviewed history, data changes, CI/CD and production rollout.

**Something breaking** → Jump to "Common Mistakes" in `04`, "Failure Modes" in `05`, or "Troubleshooting" in `06`.

---

## New production branches

After 01–06, read 11 to diagnose query cost, 12 to enforce business invariants, and 13 when multiple tenants share the service. Keep 08–10 as prerequisites for tenant recovery and runtime privilege decisions.

## Key Decisions at a Glance

| Question | Answer |
|----------|--------|
| PostgreSQL or SQLite? | PostgreSQL for shared/concurrent services and PostgreSQL semantics; SQLite for bounded single-host, low-write, or test workloads |
| Which async driver? | Choose asyncpg or Psycopg 3 for the needed APIs; benchmark equivalent workloads. Psycopg supports sync and async without an `async` extra. |
| ORM or raw SQL? | SQLAlchemy ORM for app code; raw driver for bulk ops and hot paths |
| Sync or async SQLAlchemy? | Match the I/O stack. FastAPI supports sync endpoints/dependencies and async endpoints; blocking driver calls require a sync execution boundary. |
| Async relationship loading? | Repository default: eager loading or `lazy="raise"` to expose hidden I/O; use `AsyncAttrs.awaitable_attrs` or explicit `refresh()` only when deliberate per-attribute I/O is clearer. |
| `expire_on_commit`? | This collection uses `False` for async response access; load/refresh deliberately when fresh state is required. |
| Connection pool size? | Budget all live processes and pools plus deployment overlap, then measure checkout demand and waits; see `05`. |
| PgBouncer? | Use it when you have many app instances and need to limit server connections |

---

## Prerequisites

- [Concurrency & Async](../concurrency/README.md) — understand event loops before async SQLAlchemy
- [FastAPI Dependency Injection](../fastapi/02_dependency_injection.md) — `Depends(get_db)` pattern

## What's changing — checked 2026-10-30

The chapter examples retain their stated version baselines. Treat upgrades as separate verified configurations:

- **SQLAlchemy 2.1:** Python 3.11+; install `SQLAlchemy[asyncio]` when using async paths because greenlet is no longer installed by default. A bare `postgresql://` URL now selects Psycopg 3; use explicit `postgresql+psycopg://` or `postgresql+asyncpg://` to make driver selection reviewable. Session execution autoflush is now unconditional when enabled, so even a textual SELECT can flush pending invalid writes earlier than a 2.0 application expects. Re-run transaction/rollback tests before deployment. [Migration guide](https://docs.sqlalchemy.org/en/21/changelog/migration_21.html).
- **PostgreSQL 18:** `uuidv7()` provides time-ordered identifiers; they are not an authorization secret. Generated columns default to VIRTUAL, so explicitly retain STORED when persistence is required. New clusters enable checksums by default; compare source/target checksum settings before `pg_upgrade`. MD5 deprecation and SCRAM migration belong in [access security](10_database_access_security.md). OAuth requires an explicit server/client authentication design. [Release notes](https://www.postgresql.org/docs/18/release-18.html).

The [2.1 upgrade probe](examples/sqlalchemy_21_probe.py) proves driver selection and the earlier flush boundary in an isolated SQLite database; it does not establish PostgreSQL performance or provider upgrade compatibility. Install `SQLAlchemy[asyncio]==2.1.6`, then run `python fundamentals/database/examples/sqlalchemy_21_probe.py`. Keep the existing 2.0 async baseline pinned until its driver, transaction and migration suite passes under the target release.
