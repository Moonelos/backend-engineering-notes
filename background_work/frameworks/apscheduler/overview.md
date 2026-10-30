# APScheduler — Job Scheduling

> **Who this is for**: Python engineers who need cron, interval, or one-time triggers and must decide whether execution can remain local.

Before reading this, understand why **[scheduling and execution are separate](../../foundations/01_overview.md#5-choose-durability-independently-from-concurrency)**.

## What this framework is

A Python service needs to create work at a cron, interval, or one-time deadline without adopting a full task platform. APScheduler 3.x supplies those triggers, decides **when** a callable becomes eligible, and can execute it locally.

| Role | APScheduler 3.x coverage |
|---|---|
| Scheduler | Yes |
| Local executor | Yes, thread/process/async integration depending on scheduler |
| Distributed task queue | No |
| Broker abstraction | No |
| Persistent business-workflow engine | No |

---

## What this framework is not

APScheduler is not a complete distributed durable queue or a business-workflow engine. A persistent job store preserves schedules, but APScheduler 3.x does not coordinate several scheduler processes through leader election.

> **Key insight**: A durable schedule proves that a firing time was stored; it does not prove the triggered business effect executed once or completed.

---

## Installation — persistent stores need extras

```bash
pip install apscheduler

# Only if you use a persistent job store:
pip install 'apscheduler[redis]'        # RedisJobStore
pip install 'apscheduler[sqlalchemy]'   # SQLAlchemyJobStore
pip install psycopg2-binary             # plus a driver, for a postgresql:// URL
```

Neither `redis` nor `sqlalchemy` is a base dependency, so the job-store snippets later in this note fail on a bare `pip install apscheduler` with `ModuleNotFoundError: No module named 'redis'` (or `'sqlalchemy'`) at import — and a `postgresql://` URL additionally needs a DBAPI driver or SQLAlchemy raises `ModuleNotFoundError: No module named 'psycopg2'`. Verified against the [3.11.3 metadata](https://pypi.org/pypi/apscheduler/3.11.3/json), checked 2026-08-03.

The unversioned package currently installs the stable 3.x line. APScheduler 4.x remains a pre-release rewrite with different APIs; the [official version history](https://apscheduler.readthedocs.io/en/master/versionhistory.html) says not to use the 4.0 pre-release in production.

---

## Run one bounded firing and then explain it

Start the PostgreSQL example in [minimal durable task](../../foundations/03_minimal_durable_task.md#run-one-job-before-studying-the-schema). From `background_work/examples/durable_job`, with `DATABASE_URL` still set:

```bash
.venv/bin/python -m pip install -r requirements-brokers.txt
.venv/bin/python scheduled_once.py
```

The [complete script](../../examples/durable_job/scheduled_once.py) schedules one known UTC instant, waits at most five seconds, commits the same operation key on replay and shuts the scheduler down. It then runs the local worker and prints `one scheduled firing, one durable job, SUCCEEDED`. The scheduler only creates the durable row; the worker supplies completion. The following recipes change triggers, stores and process placement around that working boundary.

---

## The scheduler type is decided by how your app runs

| Scheduler | Use case | How it runs |
|-----------|----------|-------------|
| `AsyncIOScheduler` | Async apps (FastAPI, aiohttp) | On the running event loop |
| `BackgroundScheduler` | Sync apps (Flask, scripts) | In a background thread |
| `BlockingScheduler` | Standalone scripts | Blocks the main thread |

For FastAPI, always use **`AsyncIOScheduler`**.

---

## Pin the timezone, or the same code fires at different times

Every cron example below uses a bare wall-clock hour (`hour=3`). APScheduler resolves those against `tzlocal.get_localzone()` — **the host's local zone** — so identical code fires at 03:00 Europe/Athens on a developer laptop and 03:00 UTC in a container. Pin it explicitly:

```python
scheduler = AsyncIOScheduler(timezone="UTC")          # whole scheduler
scheduler.add_job(cleanup, "cron", hour=3, timezone="UTC")   # or per trigger
```

⚠️ In a DST-observing zone, a daily firing time inside the spring-forward gap is **skipped entirely** (the wall-clock hour does not exist that day), and one inside the fall-back repeat can **fire twice** (the hour occurs twice). Scheduling in UTC removes both cases; if a job genuinely must run at a local wall-clock time, expect and handle those two days. Verified against 3.11.3 (`self.timezone = astimezone(config.pop("timezone", None)) or get_localzone()`, with `tzlocal>=3.0` as a hard dependency), checked 2026-08-03.

---

## Three trigger types cover every schedule

### `interval` — Fixed Intervals

Run every N seconds/minutes/hours.

```python
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="UTC")

# Every 5 minutes
@scheduler.scheduled_job('interval', minutes=5)
async def refresh_cache():
    await cache.refresh_all()

# Every 30 seconds, but not until 10 seconds after startup
@scheduler.scheduled_job(
    'interval',
    seconds=30,
    start_date=datetime.now(timezone.utc) + timedelta(seconds=10),
)
async def health_ping():
    await ping_external_services()
```

Options: `weeks`, `days`, `hours`, `minutes`, `seconds`, `start_date`, `end_date` — in practice you will only reach for **`minutes`** and **`seconds`**; the rest exist for completeness and `start_date`/`end_date` bound a window.

### `cron` — Cron-like Scheduling

Rich cron expressions.

```python
# Every day at 2:30 AM
@scheduler.scheduled_job('cron', hour=2, minute=30)
async def nightly_cleanup():
    await delete_expired_sessions()
    await vacuum_database()

# Every Monday at 9:00 AM
@scheduler.scheduled_job('cron', day_of_week='mon', hour=9, minute=0)
async def weekly_report():
    await generate_and_send_report()

# Every 15 minutes during business hours
@scheduler.scheduled_job('cron', hour='9-17', minute='*/15')
async def sync_inventory():
    await sync_from_erp()

# First day of every month at midnight
@scheduler.scheduled_job('cron', day=1, hour=0, minute=0)
async def monthly_billing():
    await run_billing_cycle()
```

Cron fields: `year`, `month`, `day`, `week`, `day_of_week`, `hour`, `minute`, `second`. Nearly every real schedule is built from three of them — **`hour`**, **`minute`**, and **`day_of_week`** — as in the four examples above. Omitted fields more significant than the least-significant field you set use `*`; less-significant fields use their minimum, except `week` and `day_of_week`, which use `*`. Thus `hour=3, minute=0` implies `second=0` and fires at 03:00:00 each day. [APScheduler 3.x cron defaults](https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html), checked 2026-10-30.

### `date` — One-time Execution

Run once at a specific time.

```python
from datetime import datetime, timedelta

# Run once, 1 hour from now
scheduler.add_job(
    send_reminder,
    trigger='date',
    run_date=datetime.now() + timedelta(hours=1),
    args=["user_123", "Complete your profile!"],
)
```

---

## `AsyncIOScheduler.start()` needs a running event loop

⚠️ `AsyncIOScheduler.start()` calls `asyncio.get_running_loop()`, so calling it at module level raises `RuntimeError: no running event loop`. Both styles below must run inside an already-running loop — either `asyncio.run(main())` as shown, or a framework's lifespan (see [FastAPI Integration](#fastapi-start-in-lifespan-never-at-import) below).

### Decorator Style

```python
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="UTC")

@scheduler.scheduled_job('interval', minutes=5, id='cache-refresh')
async def refresh_cache():
    await redis_client.refresh_hot_keys()

@scheduler.scheduled_job('cron', hour=3, minute=0, id='nightly-cleanup')
async def nightly_cleanup():
    deleted = await db.execute("DELETE FROM sessions WHERE expires_at < NOW()")
    logger.info(f"Cleaned up {deleted.rowcount} expired sessions")

async def main():
    scheduler.start()            # inside the loop, not at import time
    await asyncio.Event().wait()  # keep the process alive

if __name__ == "__main__":
    asyncio.run(main())
```

Registering jobs with `@scheduler.scheduled_job` at module level is fine — only `start()` needs the loop.

### Programmatic Style

```python
import asyncio

scheduler = AsyncIOScheduler(timezone="UTC")

async def my_job(name: str):
    print(f"Running job: {name}")

async def main():
    scheduler.add_job(my_job, 'interval', seconds=30, args=["heartbeat"], id="heartbeat")
    scheduler.add_job(my_job, 'cron', hour=2, args=["nightly"], id="nightly")
    scheduler.start()

    # Modify a running job
    scheduler.reschedule_job("heartbeat", trigger='interval', seconds=60)

    # Pause / resume
    scheduler.pause_job("heartbeat")
    scheduler.resume_job("heartbeat")

    # Remove
    scheduler.remove_job("heartbeat")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
```

Verified against 3.11.3 (`AsyncIOScheduler.start()` → `self._eventloop = asyncio.get_running_loop()`), checked 2026-08-03.

---

## How you know scheduling is working

Nothing in APScheduler prints anything by default at the level you need, so the first step is turning its logger on:

```python
import logging
logging.getLogger("apscheduler").setLevel(logging.INFO)
```

Then these are the four observables that matter. All are verified against 3.11.3:

| What happened | What you see |
|---|---|
| A job was registered | `INFO Added job "<name>" to job store "default"` |
| A firing was lost to grace time | `WARNING Run time of job "<job>" was missed by <delta>` (from `apscheduler.executors.default`) |
| An overlapping run was rejected | `WARNING Execution of job "<job>" skipped: maximum number of running instances reached (1)` |
| A job raised | `ERROR Job "<job>" raised an exception` with the traceback |

⚠️ Neither `logger.info("Scheduler started")` in your own lifespan nor the `/scheduler/jobs` endpoint below proves that anything *fires*. They confirm the scheduler object exists and holds job definitions. A scheduler with a correct job list that never fires — because the process has no running loop, or because every firing is being skipped as a misfire — looks identical from both. Watch for the `Added job` line first, then the absence of any `missed by` or `skipped` warnings at the time the job should have run.

To turn a swallowed failure into an alert, register a listener — this is the only built-in hook for it:

```python
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, EVENT_JOB_MAX_INSTANCES

def on_job_problem(event):
    if event.code == EVENT_JOB_ERROR:
        logger.error(
            "scheduled job failed",
            extra={"job_id": event.job_id, "error_class": type(event.exception).__name__},
        )
    else:
        logger.warning("scheduled job missed or skipped", extra={"job_id": event.job_id})
    alert(f"scheduled job {event.job_id} did not complete")

scheduler.add_listener(
    on_job_problem,
    EVENT_JOB_ERROR | EVENT_JOB_MISSED | EVENT_JOB_MAX_INSTANCES,
)
```

`EVENT_JOB_MAX_INSTANCES` carries a `JobSubmissionEvent`, which has no `exception` field; only the execution-error branch reads it. Job logs/alerts use identifiers and error classes, not arbitrary arguments or exception text. Without a listener, later firings still continue after a failed job; logging alone is not an owned recovery action.

---

## FastAPI: start in lifespan, never at import

### Using Lifespan (Recommended)

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Explicit, not the host's local time — see "Pin the timezone" above. The
# `cron` job below is meaningless without it: 04:00 in whichever zone the
# container happens to have is not a schedule.
scheduler = AsyncIOScheduler(timezone="UTC")

async def cleanup_expired_tokens():
    async with get_db_session() as session:
        result = await session.execute(
            text("DELETE FROM tokens WHERE expires_at < NOW()")
        )
        logger.info(f"Cleaned up {result.rowcount} expired tokens")

async def refresh_materialized_views():
    async with get_db_session() as session:
        await session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY user_stats"))
        logger.info("Refreshed materialized views")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: configure and start scheduler
    scheduler.add_job(
        cleanup_expired_tokens,
        trigger='interval',
        minutes=10,
        id='token-cleanup',
    )
    scheduler.add_job(
        refresh_materialized_views,
        trigger='cron',
        hour=4,
        minute=0,
        id='refresh-views',
    )
    scheduler.start()
    logger.info("Scheduler started")

    yield

    # Shutdown: clean up
    scheduler.shutdown(wait=True)
    logger.info("Scheduler shut down")   # NOT a completion signal — see below

app = FastAPI(lifespan=lifespan)
```

Do **not** use the deprecated `@app.on_event("startup")` pattern.

⚠️ `shutdown(wait=True)` does not drain in-flight jobs the way the argument implies. `AsyncIOScheduler` wraps `_shutdown` in `@run_in_event_loop`, which dispatches it through `call_soon_threadsafe` — so `shutdown()` returns immediately and the log line after it is not evidence that anything finished. A job still executing at that point can be cut off when the loop closes. If a scheduled job must complete across a deploy, do not run it in-process: have the firing create a durable job for a worker (Solution 3 below). Verified against 3.11.3, checked 2026-08-03.

### Scheduler control endpoints are admin-only, and the app must enforce it

⚠️ **These endpoints are privileged operations, not debug helpers.** `pause` on a billing job stops revenue collection. `remove` deletes a schedule with no record that it existed. `run-now` lets a caller fire a cleanup — a bulk `DELETE` — as many times per second as they can send requests. An unauthenticated `POST /scheduler/jobs/{id}/run-now` is a denial-of-service and data-destruction primitive handed to anyone who can reach the app, and none of it appears in the scheduler logs as anything other than normal firings.

Mount them on a router that **enforces** authorization, so a new endpoint added to the file inherits the check instead of needing to remember it:

```python
from fastapi import APIRouter, Depends, HTTPException, status

def require_admin(user = Depends(get_current_user)):
    # Authentication answers "who is this"; this line answers "may they do it".
    # Without the second check any logged-in user can pause your billing job.
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user


# dependencies= on the router applies to every route in it, including ones
# added later. Per-route Depends is what gets forgotten.
admin = APIRouter(
    prefix="/admin/scheduler",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
    include_in_schema=False,     # keep the control surface out of the public spec
)


@admin.get("/jobs")
async def list_jobs():
    return [
        {
            "id": job.id,
            "name": job.name,
            "trigger": str(job.trigger),
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
        }
        for job in scheduler.get_jobs()
    ]


@admin.post("/jobs/{job_id}/pause")
async def pause_job(job_id: str, user = Depends(require_admin)):
    scheduler.pause_job(job_id)
    # Log the actor, not just the action: "job paused" with no operator is
    # useless three weeks later when nobody knows why billing stopped.
    logger.warning("scheduler_job_paused", extra={"job_id": job_id, "actor": user.id})
    return {"status": "paused"}


@admin.post("/jobs/{job_id}/resume")
async def resume_job(job_id: str, user = Depends(require_admin)):
    scheduler.resume_job(job_id)
    logger.warning("scheduler_job_resumed", extra={"job_id": job_id, "actor": user.id})
    return {"status": "resumed"}


@admin.post("/jobs/{job_id}/run-now")
async def trigger_job(job_id: str, user = Depends(require_admin)):
    job = scheduler.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    # Timezone-aware: a naive datetime here is interpreted in the scheduler's
    # timezone, so on a UTC scheduler on a UTC+2 host the job fires two hours late.
    job.modify(next_run_time=datetime.now(timezone.utc))
    logger.warning("scheduler_job_triggered", extra={"job_id": job_id, "actor": user.id})
    return {"status": "triggered"}


app.include_router(admin)
```

⚠️ **Network-level protection is not a substitute, but it is the control that actually holds.** Put these behind a separate internal listener or an ingress rule as well; an application-level `is_admin` check is one refactor away from being bypassed, and `include_in_schema=False` hides the routes from `/docs` without protecting them at all.

⚠️ **`run-now` on a replica only affects that replica's scheduler.** With the scheduler running in every instance, the caller has no idea which one they reached, and a memory job store means `pause` is silently undone by the next deploy. If you need operator control over schedules, use a persistent job store and a single scheduler process — see [Solution 1](#solution-1-single-instance-deployment-simplest).

---

## A sync job costs a thread; a blocking async job costs the loop

APScheduler's `AsyncIOScheduler` supports both sync and async job functions.

```python
# Async job — runs directly on the event loop
async def async_cleanup():
    await db.delete_expired()

# Sync job — runs in a thread, which protects the event loop but not CPU throughput
def sync_heavy_computation():
    # CPU-bound Python still needs a process executor or a separate CPU worker.
    result = crunch_numbers()
    save_result(result)

scheduler.add_job(async_cleanup, 'interval', minutes=5)
scheduler.add_job(sync_heavy_computation, 'cron', hour=3)
```

⚠️ A sync job that takes a long time occupies a thread from the executor. An async job that performs blocking work freezes the event loop. Use async callables with async clients for I/O, and a process executor or separate CPU worker for CPU-bound Python.

---

## Job stores decide what survives a restart

By default, jobs are stored **in memory** — they are lost on restart.

### Memory Store (Default)

```python
scheduler = AsyncIOScheduler(timezone="UTC")
# Jobs live in memory. If the process restarts, all jobs are re-added from code.
# Fine for jobs defined in lifespan, since they're re-added on startup anyway.
```

### SQLAlchemy Store

```python
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

scheduler = AsyncIOScheduler(
    jobstores={
        'default': SQLAlchemyJobStore(url='postgresql://user:pass@localhost/mydb')
    }
)
```

⚠️ That `postgresql://` URL is **synchronous**, and 3.x job stores have no async interface. `AsyncIOScheduler.wakeup()` runs `_process_jobs()` — and therefore `get_due_jobs()` — on the event loop, so every scheduler tick performs blocking database I/O directly on the loop that is serving your HTTP requests. This contradicts the Sync vs Async warning above, and there is no `postgresql+asyncpg://` escape hatch in 3.x. The practical answer: keep a persistent job store on a low-traffic dedicated scheduler process rather than inside a request-serving app. Verified against 3.11.3 (`@run_in_event_loop def wakeup`), checked 2026-08-03.

### Redis Store

```python
from apscheduler.jobstores.redis import RedisJobStore

scheduler = AsyncIOScheduler(
    jobstores={
        'default': RedisJobStore(host='localhost', port=6379, db=2)
    }
)
```

### When to Use Persistent Stores

- **Memory (default):** Your jobs are defined in code and re-added on startup. This is the most common case.
- **SQLAlchemy / Redis:** You dynamically add jobs at runtime (e.g., user-scheduled reports) and need them to survive restarts. Also useful for `date` triggers (one-time jobs) that must not be lost.

### A persistent store constrains what a job may be

Moving off the memory store is where most people get their first surprise, because persistence means *serialization*:

- **The target callable must be globally reachable by module path.** No lambdas, no closures, no functions defined inside another function, no bound methods. `scheduler.add_job(lambda: ...)` works in memory and raises on a persistent store.
- **Every value in `args`/`kwargs` must be serializable.** Pass a `user_id` string, not an ORM object, an open session, or an HTTP client.

This directly constrains the [Dynamic Job Management](#jobs-can-be-added-and-removed-at-runtime) pattern below — which is precisely the case persistent stores exist for — so design those jobs as module-level functions taking primitives from the start. Source: [3.x user guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html) ("The target callable must be globally accessible" / "Any arguments to the callable must be serializable"), checked 2026-08-03.

---

## A late firing is skipped unless you widen the grace time

If a scheduled job is delayed (process was down, event loop was busy), APScheduler decides what to do based on `misfire_grace_time`:

```python
scheduler.add_job(
    nightly_cleanup,
    trigger='cron',
    hour=3,
    misfire_grace_time=3600,  # seconds — run if less than 1 hour late
)
```

- If the job is late by **less than** `misfire_grace_time` → it runs immediately
- If the job is late by **more than** `misfire_grace_time` → it is **skipped**
- Default is `1` second (very aggressive — will skip most misfired jobs)

> **Tip:** Set `misfire_grace_time` to a reasonable value for each job. For a nightly cleanup that runs at 3 AM, `3600` (1 hour) is sensible. For a real-time sync, `30` seconds may be appropriate.

### Grace time decides *whether*; `coalesce` decides *how many*

⚠️ `coalesce` defaults to **`True`**, which means that when several firings are missed during downtime, only the **last** one runs — the scheduler truncates the pending run list to `run_times[-1:]`. So setting `misfire_grace_time=3600` on an hourly job and then restarting after four hours of downtime does **not** produce four catch-up runs. It produces exactly one.

```python
scheduler.add_job(
    hourly_sync,
    trigger='interval',
    hours=1,
    misfire_grace_time=3600,   # eligible if less than an hour late
    coalesce=False,            # run EVERY missed firing, not just the newest
)
```

Which one you want depends on the job. A cache refresh only needs the newest run (`coalesce=True` is right). An hourly billing rollup that must process every window needs `coalesce=False` — or, better, a design where each firing creates a durable per-window job so the catch-up is explicit rather than a scheduler side effect. Verified against 3.11.3 (`"coalesce": asbool(job_defaults.get("coalesce", True))` and `run_times[-1:] if run_times and job.coalesce else run_times`), checked 2026-08-03.

---

## Every replica runs its own scheduler — this is the main footgun

This is the **biggest footgun** with APScheduler. If you deploy multiple instances of your FastAPI app, each instance runs its own scheduler.

```
Pod A → scheduler → runs cleanup at 3:00 AM
Pod B → scheduler → runs cleanup at 3:00 AM  ← DUPLICATE!
Pod C → scheduler → runs cleanup at 3:00 AM  ← DUPLICATE!
```

There is **no leader election**, **no distributed locking**, **no shared state** in APScheduler 3.x. Each scheduler is completely independent.

### Solution 1: Single-Instance Deployment (Simplest)

Run the scheduler in **exactly one process** — a dedicated scheduler pod/container.

```yaml
# docker-compose.yml
services:
  api:
    command: uvicorn myapp.main:app --host 0.0.0.0
    deploy:
      replicas: 3  # no scheduler here
    environment:
      ENABLE_SCHEDULER: "false"

  scheduler:
    command: python -m myapp.scheduler
    deploy:
      replicas: 1  # exactly one instance
    environment:
      ENABLE_SCHEDULER: "true"
```

```python
# myapp/scheduler.py
import asyncio
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from myapp.tasks import nightly_cleanup_task   # Dramatiq actor

# Explicit timezone. `hour=3` on a host whose TZ changes with the base image is
# a schedule that silently moves.
scheduler = AsyncIOScheduler(timezone="UTC")


def hand_off_cleanup():
    """Record the firing durably, then let a worker execute it."""
    slot = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    firing_key = f"nightly-cleanup:{slot.isoformat()}"
    with db.begin() as tx:
        if not tx.execute(text("""
            INSERT INTO scheduled_firings (firing_key) VALUES (:k)
            ON CONFLICT (firing_key) DO NOTHING
        """), {"k": firing_key}).rowcount:
            return
        tx.execute(insert(outbox).values(firing_key=firing_key))


async def main():
    # misfire_grace_time must stay smaller than the slot granularity, or a
    # recovered firing keys to a different slot and runs a second time.
    scheduler.add_job(
        hand_off_cleanup, "cron", hour=3,
        id="nightly-cleanup", misfire_grace_time=300,
    )
    scheduler.start()

    # Keep the process alive
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
```

Even with `replicas: 1`, the firing record matters: a rolling restart can briefly run two scheduler containers, and `replicas: 1` does not mean "never two". The unique `firing_key` is what makes that overlap harmless. The actor side is in [Solution 3](#solution-3-apscheduler-as-trigger-dramatiq-as-executor).

Or conditionally in the same FastAPI process:

```python
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("ENABLE_SCHEDULER") == "true":
        scheduler.start()
    yield
    if os.environ.get("ENABLE_SCHEDULER") == "true":
        scheduler.shutdown(wait=False)
```

⚠️ **Env-var gating alone does not solve the problem it looks like it solves.** The number of schedulers is `replicas × ASGI workers`, not `replicas`. A service running `uvicorn --workers 4` (or `gunicorn -w 4 -k uvicorn.workers.UvicornWorker`) with `ENABLE_SCHEDULER=true` starts **four** schedulers in one pod and produces exactly the duplicate firings this whole section exists to prevent — because each `--workers` entry is a separate process running its own copy of the app, including its own lifespan.

So this variant is only safe when the gated deployment runs **one replica *and* `--workers 1`**. And `gunicorn --preload` does not fix it: preloading shares the import, but each worker process still runs the app's lifespan independently. If you cannot guarantee both, use the dedicated scheduler process above or Solution 2/3 below. Sources: [FastAPI server workers](https://fastapi.tiangolo.com/deployment/server-workers/), [apscheduler#1088](https://github.com/agronholm/apscheduler/discussions/1088), checked 2026-08-03.

### Solution 2: Distributed Locking with Redis

If you must run the scheduler in every instance, use a distributed lock:

```python
import redis.asyncio as redis

redis_client = redis.Redis.from_url("redis://localhost:6379/0")

async def cleanup_with_lock():
    """Only one instance will execute the job body."""
    lock = redis_client.lock("scheduler:cleanup-lock", timeout=300)
    acquired = await lock.acquire(blocking=False)
    if not acquired:
        logger.info("Another instance is running cleanup, skipping")
        return
    try:
        await do_cleanup()
    finally:
        await lock.release()

scheduler.add_job(cleanup_with_lock, 'cron', hour=3)
```

This works but has two edge cases, and only one of them is obvious.

If the lock-holder **crashes**, the lock is held until `timeout` expires — that firing is simply lost. Make the timeout longer than the job's maximum execution time.

⚠️ The non-obvious one: if the job body **outruns** `timeout=300`, the lock expires while the job is still running. A second instance can then acquire it and run concurrently — the exact duplicate execution the lock was added to prevent — and when the first instance reaches `finally: await lock.release()` it raises `redis.exceptions.LockNotOwnedError: Cannot release a lock that's no longer owned`, which masks the job's own result and outcome. Two mitigations, and you want at least one:

**Option 1 — renew the lock from a task that can cancel the work.** A heartbeat callback the job body is trusted to call is not a mitigation: if the body is a single long `await`, it never calls it, and if the extension *fails* a callback has no way to stop the work. Run the renewal concurrently and make a failed extension cancel the job:

```python
import asyncio
import contextlib

LOCK_TTL = 300          # seconds
RENEW_EVERY = 100       # comfortably < LOCK_TTL / 2, so one missed tick is survivable


async def _renew(lock) -> None:
    from redis.exceptions import RedisError
    while True:
        await asyncio.sleep(RENEW_EVERY)
        try:
            async with asyncio.timeout(10):
                await lock.extend(LOCK_TTL, replace_ttl=True)
        except (RedisError, TimeoutError) as exc:
            # A network error makes ownership uncertain too, not only expiry.
            raise RuntimeError("cleanup ownership could not be renewed") from exc


async def cleanup_with_lock() -> None:
    from redis.exceptions import RedisError
    lock = redis_client.lock("scheduler:cleanup-lock", timeout=LOCK_TTL)
    if not await lock.acquire(blocking=False):
        return
    try:
        async with asyncio.TaskGroup() as group:
            work = group.create_task(do_cleanup())
            renew = group.create_task(_renew(lock))
            await work
            renew.cancel()
        # Renewal failure cancels work; outer cancellation cancels both tasks.
    finally:
        try:
            async with asyncio.timeout(10):
                await lock.release()
        except (RedisError, TimeoutError):
            # Preserve the work/renewal exception rather than masking it.
            logger.warning("cleanup lock release unconfirmed")
```

**How you know it worked:** across a rolling restart of N replicas, exactly one `cleanup started` line per scheduled slot, and no `lock lost` lines. The tell that `LOCK_TTL` is too short is `lock lost; cancelling this run` appearing every night at roughly the same elapsed time.

⚠️ **A lock is mutual exclusion, not a firing record, and it is not fencing.** Even with renewal, redis-py's lock is a TTL key: a process that stalls (GC pause, `SIGSTOP`, network partition) can resume believing it holds a lock that expired and was re-acquired, and Redis will not tell it otherwise. Nothing anywhere records that the 03:00 firing happened, so a firing lost to a crash is lost silently and a firing executed twice is invisible. If the job has a real external effect — billing, deletion, email — the lock is not enough on its own: it needs a durable unique firing record and an idempotent effect, which is Solution 3.

Source: [redis-py `lock.py`](https://github.com/redis/redis-py/blob/master/redis/lock.py) (`do_release` raises `LockNotOwnedError`, `extend(..., replace_ttl=)`), checked 2026-08-03.

### Solution 3: APScheduler as Trigger, Dramatiq as Executor

The cleanest approach for heavy workloads: use APScheduler **only** as a scheduler that hands work to Dramatiq, so the job body never runs in the web process.

⚠️ **Dramatiq does not deduplicate anything.** Its own docs require that actors be idempotent, because at-least-once delivery means an actor can run more than once for a single `.send()`. So the naive version below is *worse* than Solution 2 — with the scheduler running in every replica, three replicas fire at 03:00 and send three messages, and three workers each run a full cleanup:

```python
# WRONG — three replicas, three messages, three cleanups. Nothing dedupes.
@scheduler.scheduled_job("cron", hour=3)
def trigger_nightly_cleanup():
    nightly_cleanup_task.send()   # no firing identity: every send looks new
```

There is nothing in that message to deduplicate on. Persist `(schedule_id, scheduled_for)` before publication, then let the normal durable-job worker own attempts. A permanent `claimed_at` flag is not a worker claim: a crash after setting it would suppress every redelivery forever.

Use the [complete scheduler fixture](../../examples/durable_job/test_scheduler.py) from [scheduling and periodic work](../../execution/03_scheduling_and_periodic_work.md). It atomically creates firing, job and outbox, races two replicas, and replays a stale cursor after a crash. The `scheduled_for` argument is the calendar occurrence stored by the scheduler; it is never recomputed from callback wall time. Delayed callbacks and restart catch-up must still name the original slot.

Follow one firing through two execution attempts. The second claim changes the token, while the firing and job IDs remain stable.

```mermaid
sequenceDiagram
    participant S as Scheduler
    participant D as PostgreSQL
    participant R as Relay
    participant W as Worker
    S->>D: Commit 03:00 firing, job-42, outbox
    R->>D: Read unpublished job-42
    R->>W: Deliver job-42
    W->>D: Claim token A, lease 90s
    Note over W: Worker exits before completion
    R->>D: Recover expired lease, create hint
    R->>W: Deliver same job-42
    W->>D: Claim token B, complete if owned
```

The relay can repeat a publish after its own crash. The worker reloads the job and uses [claim, retry and completion predicates](../../examples/durable_job/store.py), so a duplicate cannot bypass ownership. If worker A resumes late, token A changes zero rows. A remote effect also needs its stable operation key; token fencing protects the local row, not a provider that never sees it.

For a full Dramatiq delivery run, use the [assembled FastAPI integration](../dramatiq/fastapi_integration.md#run-the-canonical-service-first). Its publisher repairs expired attempts and replaces lost delivery hints, while the DB budget terminalizes exhausted jobs. One scheduler callback creates an obligation; the broker, worker and reconciler discharge it.

**How you know it worked:** one firing and job per scheduled instant; a crash after claim eventually produces a new attempt and a terminal row. Alert on oldest owed job, expired leases and unpublished outbox age. A single `cleanup started` log line is neither a completion test nor a proof of exactly-once effects.

---

## APScheduler 4.x redesigns multi-node coordination but remains pre-release

APScheduler 4.x is a **complete rewrite** with a different API and architecture. Key changes:

- **Data stores** include SQLAlchemy-backed relational databases, MongoDB and an in-memory store; choose persistent storage for recoverable schedules.
- **Event brokers** coordinate scheduler instances; Redis is an event-broker option, not a built-in 4.x data store. See the [current API reference](https://apscheduler.readthedocs.io/en/master/api.html#data-stores), checked 2026-10-30.
- **Async-first** design
- **No more job stores confusion** — one unified store

```python
# APScheduler 4.x API (subject to change)
from apscheduler import AsyncScheduler
from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
from apscheduler.eventbrokers.redis import RedisEventBroker
from apscheduler.triggers.cron import CronTrigger

async with AsyncScheduler(
    data_store=SQLAlchemyDataStore("postgresql+asyncpg://..."),
    event_broker=RedisEventBroker("redis://localhost:6379/0"),
) as scheduler:
    await scheduler.add_schedule(
        cleanup_task, CronTrigger(hour=3), id="nightly-cleanup"
    )
    await scheduler.run_until_stopped()
```

APScheduler 4.x redesigns data stores to support multiple schedulers/workers and introduces event brokers for coordination. The [official migration guide](https://apscheduler.readthedocs.io/en/master/migration.html) says external event brokers are required for multi-node or multi-process deployments. This is a new distributed architecture, not a guarantee that arbitrary job side effects run exactly once. The official version history still marks 4.0 as a pre-release unsuitable for production; use the stable 3.x line with one logical scheduler until that changes.

---

## Non-overlap is already the default

If a job is still running when its next firing comes due, **the new invocation is skipped** — no configuration required. `max_instances` defaults to `1` in the shipped 3.x line.

```python
scheduler.add_job(
    slow_sync,
    trigger='interval',
    minutes=5,
    max_instances=1,           # the default, written out explicitly
    replace_existing=True,
    id='slow-sync',
)
```

The `max_instances=1` above is therefore a no-op made visible, which is worth keeping for the reader of your code but changes nothing at runtime. You know it engaged from the log line:

```
WARNING Execution of job "slow_sync" skipped: maximum number of running instances reached (1)
```

A reader who actually *wants* concurrent runs of the same job has to opt in by raising the limit:

```python
scheduler.add_job(fan_out, 'interval', minutes=5, max_instances=5)
```

Verified against 3.11.3 (`"max_instances": asint(job_defaults.get("max_instances", 1))`), checked 2026-08-03.

---

## Jobs can be added and removed at runtime

```python
from apscheduler.jobstores.base import JobLookupError

# Add a job for a user-scheduled report
def schedule_user_report(user_id: str, cron_hour: int, cron_minute: int):
    scheduler.add_job(
        generate_user_report,
        trigger='cron',
        hour=cron_hour,
        minute=cron_minute,
        id=f"user-report-{user_id}",
        args=[user_id],
        replace_existing=True,     # update if already exists
        jobstore='default',
    )

# Remove when user cancels
def cancel_user_report(user_id: str):
    try:
        scheduler.remove_job(f"user-report-{user_id}")
    except JobLookupError:
        pass  # already removed
```

---

## The six mistakes that cause real incidents

The first three rows cause most production incidents: duplicate schedulers, heavy local execution, and failures with no alert/retry policy.

| Mistake | Fix |
|---------|-----|
| Running scheduler in every pod | Use single-instance or distributed lock |
| Heavy work in scheduled job | Offload to Dramatiq worker |
| No error policy in jobs | APScheduler logs the exception and later firings continue; add alerting and create a durable retryable job when failure matters |
| Forgetting `scheduler.shutdown()` | Always shut down in lifespan `yield` cleanup |
| Using `BackgroundScheduler` with FastAPI | Use `AsyncIOScheduler` — it runs on the event loop |
| Default `misfire_grace_time=1` | Set a reasonable value or jobs get skipped silently |

---

## APScheduler answers “when”; a queue answers “where” and “how safely”

Start by deciding whether execution may stay in one scheduler process. If not, use the scheduler only to create an idempotent durable task.

| Scenario | Use |
|----------|-----|
| Simple periodic task, single instance | APScheduler |
| Periodic task, multiple instances | APScheduler + distributed lock, or APScheduler as trigger + Dramatiq |
| Heavy periodic task (minutes to hours) | APScheduler as trigger + Dramatiq |
| Task needs retries or result tracking | Dramatiq (APScheduler has neither) |
| Cron scheduling + lightweight work | APScheduler |
| No broker infrastructure available | APScheduler |
| User-configured schedules | APScheduler with persistent job store |

---

## Mental Model

> **APScheduler = cron for your Python process.** It answers "when" but not "where" or "how safely." If you need distributed-safe execution, use it only as a trigger that enqueues Dramatiq tasks.

```
APScheduler says:  "It's 3:00 AM, time to run cleanup"
                        │
                        ├── Simple case: run cleanup() right here in this process
                        │
                        └── Distributed case: commit firing + job + outbox → relay → worker
```

---

## When to use APScheduler

Use APScheduler 3.x when one controlled process can own timing, local execution is acceptable, or each firing creates an idempotent durable job.

When a separate worker runtime is needed, APScheduler can publish to Dramatiq, Celery, a managed queue, or a database job table. The destination is an architectural choice, not an APScheduler requirement.

---

## When not to use APScheduler

Do not use APScheduler as the only durability layer for critical distributed work, human workflows, or jobs that must survive an executing process crash.

⚠️ Running a scheduler inside every API pod creates one firing per pod. A shared 3.x job store does not add leader election; run one scheduler process or use an external leader/locking design with idempotent jobs.

---

## Recap and check yourself

- APScheduler calculates eligibility; durable firing/job rows preserve the resulting obligation.
- Replica-local max_instances limits do not coordinate process ownership.
- A lease needs supervised renewal and token-bound effects; permanent claimed flags lose work after a crash.

**Two replicas fire at 03:00 and the first worker dies after claim. Does max_instances=1 recover the job?**

<details><summary>Answer</summary>

No. It limits one scheduler process only. Unique firing intent, expiring attempt ownership and an idempotent effect recover the obligation.

</details>

**Redis renewal raises a network error rather than LockNotOwnedError. May cleanup continue?**

<details><summary>Answer</summary>

No. Ownership is uncertain. The renewal task fails and TaskGroup cancels cleanup; external effects still need fencing/idempotency because cooperative cancellation cannot undo them.

</details>

**Try it:** In the durable-job crash test, remove the completion token predicate and predict the assertion that detects the defect.

<details><summary>Hint and worked solution</summary>

Run the old completion after the new claim, not before it. `assert not store.complete(old, 999)` must fail; the mutation has lost fencing. Restore the predicate and require the new result to remain authoritative.

</details>


**Next**: [Airflow](../airflow/overview.md)
