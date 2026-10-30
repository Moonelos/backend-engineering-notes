# Docker and Deployment for FastAPI

<!-- length-justification: The opening lab owns the complete image/lifecycle result. Later sections retain implementation alternatives as reference; release and Kubernetes behavior have separate canonical owners. -->

> **Who this is for**: FastAPI engineers building a reproducible container and carrying its health,
> shutdown, identity, and capacity contract into deployment.

A production-focused guide to containerizing and deploying FastAPI applications — from Dockerfile to graceful shutdown.

> **Key insight**: A deployable image is only the artifact; production correctness comes from the
> runtime contract around identity, signals, health, resources, and rollout.

---

## Run one image through its full lifetime

Prerequisites: Python 3.11+ for the verification driver and a local Docker daemon. The supplied app
uses Python 3.12, pinned FastAPI/Uvicorn inputs and a fully resolved hash-checked requirements file.
It has no database, credentials or external service. From the repository root:

```bash
docker build -t notes-lifecycle:lab operations/deployment/examples/container_lifecycle
python3 operations/deployment/examples/container_lifecycle/verify.py notes-lifecycle:lab
```

The [app](examples/container_lifecycle/app.py), [Dockerfile](examples/container_lifecycle/Dockerfile),
[dependency lock](examples/container_lifecycle/requirements.txt) and [driver](examples/container_lifecycle/verify.py)
are the complete example. The driver binds an ephemeral port on loopback, checks the same image
through each phase and removes its uniquely named container even on failure. Expected assertions:

```text
PASS non-root uid=10001; ready=503 while health=200
PASS unhealthy stays running; restart count=0
PASS in-flight response=200; cleanup complete; exit=0; stop under 12s
```

The printed image ID identifies the artifact tested. The Python base tag is mutable: record its
resolved digest and pin that digest in a release build; hashes in `requirements.txt` protect Python
artifacts, not the operating-system base. Rebuild and rerun after any base or dependency upgrade.
The test injects failures through files inside its own container, not through public debug routes.

This lifecycle has several owners; inspect where observation becomes action:

```mermaid
sequenceDiagram
    participant D as Docker
    participant U as Uvicorn
    participant A as FastAPI lifespan
    participant C as Local client
    D->>U: Start tested image as uid 10001
    U->>A: Startup
    C->>A: GET ready and health
    A-->>C: ready 503, health 200 after dependency simulation
    Note over D,A: Docker health failure marks unhealthy, process remains running
    C->>U: GET slow, bounded to 3 seconds
    D->>U: SIGTERM, outer grace 12 seconds
    U-->>C: Finish response before 6-second server drain budget
    U->>A: Shutdown and resource cleanup
    U-->>D: Exit 0
```

Docker's `HEALTHCHECK` changes health status. Its ordinary restart policy responds to process exit,
not to `unhealthy`. Kubernetes can separately restart after a failed liveness probe or withdraw
traffic after failed readiness; those are controller decisions. A database outage should usually
withdraw dependent traffic, not create a fleet-wide restart storm.
[Docker health](https://docs.docker.com/reference/dockerfile/#healthcheck) and
[restart policies](https://docs.docker.com/engine/containers/start-containers-automatically/), checked 2026-10-30.

During the slow request, the driver waits for the server's “started” log before sending SIGTERM.
That establishes the interleaving; sleeping a guessed duration would not prove draining. The server
owns intake/drain; lifespan owns cleanup; Docker owns the final kill deadline. A real resource
cleanup budget must fit between server drain and container grace, and must handle partial startup.
The lab's cleanup is local logging; the resource-owning pattern appears in section 8.

**Stop here** when you can reproduce and explain these observations. The following sections are
reference variants for real resources, process counts, package managers and Compose. Promote the
same tested digest through [releases](02_ci_cd_and_releases.md), then apply the
[Kubernetes runtime](03_kubernetes_runtime.md) only when needed.

## 1. The Mental Model

Deploying a FastAPI app is not "put code in a container." It is a series of decisions about **isolation, reproducibility, and failure handling**.

The deployment stack:

```
Your Code
  ↓
ASGI Server (Uvicorn)
  ↓
Process Manager (Gunicorn, optional)
  ↓
Container (Docker)
  ↓
Orchestrator (Compose / Kubernetes)
  ↓
Infrastructure
```

Each layer has a specific job. Skipping or misconfiguring any layer creates production problems that are hard to debug.

---

## 2. Dockerfile for FastAPI

### The Production Dockerfile

```dockerfile
# ---- Stage 1: Build ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies (gcc, etc.) only in build stage
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 2: Runtime ----
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy only installed packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -s /sbin/nologin appuser

# Copy application code last (best cache utilization)
COPY ./app ./app

# Switch to non-root user
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Why Multi-Stage Builds

| Concern | Single stage | Multi-stage |
|---------|-------------|-------------|
| Image size | Includes whatever build tools remain in final layers | Can omit build tools; measure the actual compressed/pulled image |
| Attack surface | Build tools in production | Minimal runtime |
| Build cache | Supports cacheable layers when inputs are ordered well | Separates builder and runtime cache boundaries |
| Secrets exposure | Never COPY secrets; use BuildKit secret mounts | Same rule: stage separation alone does not secure caches/history |

### Why `python:3.12-slim` Over `python:3.12`

```
python:3.12       → ~1.0 GB (full Debian, docs, man pages)
python:3.12-slim  → ~150 MB (minimal Debian)
python:3.12-alpine → ~50 MB (musl libc — smaller but trickier)
```

> **Default to `slim`.** Alpine uses `musl` instead of `glibc`. The long-standing pain — no binary wheels, long compile-from-source installs — has mostly been resolved: PEP 656 added the `musllinux` wheel tag, and as of 2024–2025 numpy, pandas, psycopg2-binary, scipy, matplotlib, and most of the scientific stack ship `musllinux_1_2` wheels on PyPI. The cases where Alpine still hurts are: (a) packages that have not yet published musllinux wheels — check with `pip install --only-binary=:all: <pkg>`; (b) subtle runtime differences (DNS resolver behavior, thread-local stacks) that can surface as hard-to-diagnose bugs. If you want the smaller image and your dependency tree installs cleanly from wheels, Alpine is fine. Otherwise stick with `slim` — the 100MB savings is rarely worth the compatibility debugging.

### Why Non-Root User

Running as `root` inside a container means:

- Container escape vulnerabilities grant root on the host
- Any file-write bug can modify system files
- Violates the principle of least privilege

```dockerfile
# Create user with no shell, no home directory
RUN groupadd -r appuser && useradd -r -g appuser -s /sbin/nologin appuser
USER appuser
```

This is a **security requirement**, not a best practice.

---

## 3. Uvicorn Production Configuration

### The Flags That Matter

```bash
uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --loop uvloop \
    --http httptools \
    --log-level warning \
    --limit-concurrency 100 \
    --backlog 2048 \
    --timeout-keep-alive 5
```

### What Each Flag Does

| Flag | Purpose | Default | Production Value |
|------|---------|---------|-----------------|
| `--host 0.0.0.0` | Bind to all interfaces (required in Docker) | `127.0.0.1` | `0.0.0.0` |
| `--port 8000` | Listen port | `8000` | `8000` |
| `--workers N` | Number of OS processes | `1` | ~`1 per CPU core` (async workers — see note below) |
| `--loop uvloop` | Faster event loop implementation | `auto` | `uvloop` |
| `--http httptools` | Faster HTTP parser | `auto` | `httptools` |
| `--log-level warning` | Suppress per-request access logs | `info` | `warning` or `info` |
| `--limit-concurrency N` | Max in-flight requests per worker | `None` (unlimited) | Set based on load testing |
| `--backlog N` | TCP connection queue size | `2048` | `2048` |
| `--timeout-keep-alive N` | Idle connection timeout (seconds) | `5` | `5` |

### Understanding `--workers`

Uvicorn's `--workers` flag spawns multiple **processes**, each with its own event loop.

```
uvicorn --workers 4

Parent process (supervisor)
  ├── Worker 1 (event loop + app)
  ├── Worker 2 (event loop + app)
  ├── Worker 3 (event loop + app)
  └── Worker 4 (event loop + app)
```

Each worker is a fully independent copy of your application. They share nothing in memory.

> **Worker count for async workers is not `2 * CPU + 1`.** That formula is Gunicorn's heuristic for *synchronous* workers, where one process handles one request at a time. An async Uvicorn worker handles many concurrent requests on a single event loop, so you don't need extra processes to hide I/O latency. Start at roughly **one worker per CPU core** and tune from load tests. (For purely I/O-bound workloads a single worker per core is often plenty; more workers mainly help saturate multiple cores for CPU-bound work.)

### Understanding `--limit-concurrency`

This is your **per-worker admission control**.

```
--limit-concurrency 100

Request 1-100   → accepted, processed by event loop
Request 101     → HTTP 503 immediately
```

Without this, a burst of 10,000 requests all enter the event loop simultaneously, memory spikes, and the pod crashes.

> **Always set `--limit-concurrency` in production.** The correct value depends on your workload — start with 100 and adjust based on load testing.

### Install Performance Dependencies

```
pip install uvloop httptools
```

These are C-based replacements for Python's default asyncio loop and HTTP parser. Typical improvement: **2-3x throughput** for no code changes.

---

## 4. Gunicorn + Uvicorn

### When to Use Gunicorn

Uvicorn can run multiple workers on its own. Gunicorn adds:

- **Mature process management** — worker recycling, graceful restarts
- **Worker health monitoring** — restarts workers that hang or crash
- **Configurable worker lifecycle** — `max-requests` to prevent memory leaks
- **Graceful reloads** — `SIGHUP` for zero-downtime config changes

### The Decision

| Scenario | Recommendation |
|----------|---------------|
| Kubernetes (one process per pod) | Uvicorn alone |
| Single VM, multiple workers | Gunicorn + UvicornWorker |
| Docker Compose, no orchestrator | Gunicorn + UvicornWorker |
| Development | Uvicorn with `--reload` |

> **In Kubernetes, run one Uvicorn worker per container.** Let Kubernetes handle process management, scaling, and health checks. Running Gunicorn inside Kubernetes adds a redundant management layer.

### Gunicorn + UvicornWorker Configuration

> **Use the `uvicorn-worker` package, not `uvicorn.workers`.** Since Uvicorn 0.30 the bundled `uvicorn.workers.UvicornWorker` is deprecated and emits a warning; the worker now lives in the separate [`uvicorn-worker`](https://pypi.org/project/uvicorn-worker/) package as `uvicorn_worker.UvicornWorker`. Add `uvicorn-worker` to your dependencies.

```bash
gunicorn app.main:app \
    --worker-class uvicorn_worker.UvicornWorker \
    --workers 4 \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --graceful-timeout 30 \
    --keep-alive 5 \
    --max-requests 10000 \
    --max-requests-jitter 1000 \
    --access-logfile - \
    --error-logfile -
```

### What Each Flag Does

| Flag | Purpose |
|------|---------|
| `--worker-class uvicorn_worker.UvicornWorker` | Use Uvicorn as the ASGI worker (from the `uvicorn-worker` package) |
| `--workers 4` | Number of worker processes |
| `--timeout 120` | Kill worker if it doesn't respond in 120s |
| `--graceful-timeout 30` | Time for graceful shutdown per worker |
| `--max-requests 10000` | Recycle worker after N requests (prevents memory leaks) |
| `--max-requests-jitter 1000` | Randomize restart point (prevents all workers restarting at once) |

### Dockerfile with Gunicorn

```dockerfile
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd -r appuser && useradd -r -g appuser -s /sbin/nologin appuser

COPY ./app ./app

USER appuser

EXPOSE 8000

CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn_worker.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--max-requests", "10000", \
     "--max-requests-jitter", "1000"]
```

---

## 5. Docker Compose for Development

### Full Stack: App + Postgres + Redis

```yaml
# docker-compose.yml
# Compose V2 ignores the top-level `version:` key (and warns if present) —
# omit it.

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    env_file:
      - .env
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/appdb
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./app:/app/app  # Hot reload in development
    command: >
      uvicorn app.main:app
      --host 0.0.0.0
      --port 8000
      --reload
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 10s

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: appdb
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  postgres_data:
  redis_data:
```

### Key Details

**`depends_on` with health checks**: Without `condition: service_healthy`, Docker Compose only waits for the container to _start_, not for the service inside it to be _ready_. Your app will crash trying to connect to a Postgres that hasn't finished initialization.

**Volume mount for hot reload**: `./app:/app/app` maps your local code into the container so `--reload` picks up changes. Remove this in production.

**Named volumes for data persistence**: `postgres_data` and `redis_data` survive container restarts. Without them, you lose all data on `docker-compose down`.

---

## 6. `.dockerignore`

### Why It Matters

Without `.dockerignore`, `COPY . .` sends **everything** to the Docker daemon — git history, virtual environments, IDE files, test data.

```
# .dockerignore

# Version control
.git
.gitignore

# Python
__pycache__
*.pyc
*.pyo
.venv
venv
env

# IDE
.vscode
.idea
*.swp
*.swo

# Testing
.pytest_cache
.coverage
htmlcov
.tox

# Docker
docker-compose*.yml
Dockerfile*
.dockerignore

# Environment / secrets
.env
.env.*
*.pem
*.key

# Documentation
*.md
docs/
LICENSE

# OS
.DS_Store
Thumbs.db

# Build artifacts
dist/
build/
*.egg-info

# uv
.python-version
```

### Impact

| Without `.dockerignore` | With `.dockerignore` |
|------------------------|---------------------|
| Build context: 500MB+ (includes `.git`) | Build context: 5MB (code + requirements) |
| Build time: 30s+ | Build time: 5s |
| Secrets potentially in image | Secrets excluded |
| Cache invalidated by irrelevant changes | Cache stable |

---

## 7. Health Checks

### Two Endpoints, Two Purposes

| Endpoint | Question | Used By | Action on Failure |
|----------|----------|---------|-------------------|
| `/health` (liveness) | Is the process responsive? | Docker health observer / Kubernetes liveness controller | Docker marks health; Kubernetes may restart |
| `/ready` (readiness) | Can it handle traffic? | Load balancer, Kubernetes | Stop sending traffic |

### Implementation

```python
from fastapi import FastAPI, Response
import asyncio
import asyncpg
import redis.asyncio as redis

app = FastAPI()


@app.get("/health")
async def health():
    """Liveness: is the process running and responsive?

    Keep this simple. No external dependency checks.
    A failed probe lets its configured observer/controller decide what to do.
    """
    return {"status": "alive"}


@app.get("/ready")
async def readiness(response: Response):
    """Readiness: can this instance handle traffic?

    Check critical dependencies. If any fail,
    this instance should be removed from the load balancer.
    """
    checks = {}

    # Check database
    try:
        async with asyncio.timeout(1):
            await app.state.db_pool.fetchval("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    # Check Redis
    try:
        async with asyncio.timeout(1):
            await app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unavailable"

    all_healthy = all(v == "ok" for v in checks.values())

    if not all_healthy:
        response.status_code = 503

    return {"status": "ready" if all_healthy else "degraded", "checks": checks}
```

A healthy probe returns `200` with both checks set to `ok`. If Redis stalls past one second, the
same endpoint returns `503` with `"redis": "unavailable"`; it does not hang until Kubernetes's
probe timeout kills the request.

### Common Mistake: Liveness Checks That Call Databases

```python
# ❌ WRONG — liveness check depends on external service
@app.get("/health")
async def health():
    await db.execute("SELECT 1")     # If DB is down, container restarts
    await redis.ping()               # Restarting won't fix a DB outage
    return {"status": "ok"}
```

```python
# ✅ CORRECT — liveness is self-contained, readiness checks dependencies
@app.get("/health")
async def health():
    return {"status": "alive"}

@app.get("/ready")
async def ready():
    # Check dependencies here
    ...
```

If liveness depends on the database and the database goes down, a Kubernetes liveness policy can cause **every affected container to restart in a loop**. The database comes back to a thundering herd of reconnections. This turns a database blip into a full outage.

### Docker HEALTHCHECK

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
```

| Parameter | Meaning |
|-----------|---------|
| `--interval` | Time between checks |
| `--timeout` | Max time for a single check |
| `--start-period` | Grace period during startup (failures don't count) |
| `--retries` | Consecutive failures before marking unhealthy |

> **`--start-period` is critical.** Without it, a slow-starting app (running migrations, loading ML models) can be marked unhealthy before it finishes starting. Ordinary Docker does not kill it solely for that health state.

---

## 8. Graceful Shutdown

### The Problem

When a container stops, Docker sends `SIGTERM`, waits 10 seconds (default), then sends `SIGKILL`.

If your app doesn't handle `SIGTERM`:

- In-flight requests are dropped mid-response
- Database transactions are left open
- WebSocket connections break without close frames
- Background tasks vanish

### How Uvicorn Handles Signals

Uvicorn already handles `SIGTERM` and `SIGINT`:

1. Receives `SIGTERM`
2. Stops accepting new connections
3. Waits for in-flight requests to complete
4. Calls ASGI lifespan shutdown
5. Exits

### FastAPI Lifespan for Resource Cleanup

```python
from contextlib import AsyncExitStack, asynccontextmanager
from fastapi import FastAPI
import asyncio
import os
import asyncpg
import httpx
import redis.asyncio as redis

async def close_pool(pool):
    try:
        async with asyncio.timeout(3):
            await pool.close()
    except TimeoutError:
        pool.terminate()  # don't let checked-out connections exceed shutdown grace

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=10)
        stack.push_async_callback(close_pool, pool)  # registered before next acquisition
        client = await stack.enter_async_context(httpx.AsyncClient(timeout=5.0))
        cache = redis.from_url(os.environ["REDIS_URL"], socket_timeout=2)
        stack.push_async_callback(cache.aclose)
        await cache.ping()  # failure still closes cache, HTTP client, then pool
        app.state.db_pool, app.state.http_client, app.state.redis = pool, client, cache
        yield

app = FastAPI(lifespan=lifespan)
```

This application-dependent excerpt requires reachable database and Redis services; the opening
lab does not claim to verify them. Give every cleanup operation a bounded policy appropriate to
its client and leave total cleanup time inside the outer stop grace. The stack handles both a
failed acquisition and cancellation after successful startup.


### Docker Stop Timeout

```yaml
# docker-compose.yml
services:
  app:
    stop_grace_period: 30s  # Give app 30s to finish, not just 10s
```

```bash
# Or via CLI
docker stop --time 30 my_container
```

### The PID 1 Problem

Docker signals the container’s main process. Exec form makes the server that process; a proper init or process manager may instead forward signals to its children. The requirement is a verified signal path, not that application code always has PID 1.

```dockerfile
# ❌ WRONG — shell wraps the process, eats signals
CMD uvicorn app.main:app --host 0.0.0.0

# This actually runs: /bin/sh -c "uvicorn app.main:app --host 0.0.0.0"
# SIGTERM goes to sh, not uvicorn
```

```dockerfile
# ✅ CORRECT — exec form, uvicorn is PID 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

The **exec form** (JSON array) runs the process directly without a shell wrapper. The **shell form** (plain string) wraps your command in `/bin/sh -c`, which intercepts signals.

### Connection Draining in Practice

An HTTP middleware counter around `call_next()` can reach zero when headers return while a
streaming body is still running. Wrap the ASGI call to track the whole response lifetime instead:

```python
class ActiveRequests:
    def __init__(self, app):
        self.app = app
        self.active = 0  # per process and event loop, not a fleet-wide count

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        self.active += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.active -= 1
```

Uvicorn still owns actual draining. This counter is telemetry, and separate worker processes have
separate counters; aggregate them explicitly. Use a bounded streaming test before trusting a
shutdown dashboard.


---

## 9. Environment Variables in Docker

### Three Mechanisms, Three Purposes

| Mechanism | Set at | Baked into image | Use case |
|-----------|--------|-----------------|----------|
| `ENV` in Dockerfile | Build time | Yes | Defaults, PATH, Python settings |
| `ARG` in Dockerfile | Build time | No (not in final image) | Build-time configuration |
| `environment` / `env_file` in Compose | Run time | No | Secrets, per-environment config |

### Dockerfile: `ENV` vs `ARG`

```dockerfile
# ARG — only available during build, not in running container
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

# ENV — available in running container
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
```

### Recommended Environment Variables

```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
```

| Variable | Purpose |
|----------|---------|
| `PYTHONDONTWRITEBYTECODE=1` | Don't create `.pyc` files (no point in containers) |
| `PYTHONUNBUFFERED=1` | Force stdout/stderr to be unbuffered (logs appear immediately) |

### Docker Compose: Runtime Configuration

```yaml
# docker-compose.yml
services:
  app:
    # Method 1: Inline (for non-sensitive values)
    environment:
      - APP_ENV=production
      - LOG_LEVEL=warning
      - WORKERS=4

    # Method 2: File (for secrets and many variables)
    env_file:
      - .env
```

```bash
# .env file (NEVER commit this)
DATABASE_URL=postgresql+asyncpg://user:secretpass@db:5432/appdb
REDIS_URL=redis://redis:6379/0
SECRET_KEY=your-secret-key-here
API_KEY=sk-abc123
```

### Reading Config in FastAPI

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str
    secret_key: str
    debug: bool = False
    workers: int = 4
    log_level: str = "warning"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

### Anti-Pattern: Hardcoded Secrets

```dockerfile
# ❌ WRONG — secrets baked into image
ENV DATABASE_URL=postgresql://user:realpassword@prod-db:5432/app
```

```python
# ✅ CORRECT — secrets injected at runtime
# Dockerfile: no secrets
# docker-compose.yml or Kubernetes: inject via env_file or secrets
```

---

## 10. Common Patterns

### Package Managers: pip vs Poetry vs uv

#### `requirements.txt` + pip — Simple and Universal

No extra tooling. Works everywhere.

```dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

#### Poetry — Lock File for Reproducibility

Requires Poetry installed in the build stage.

```dockerfile
# ---- Build stage ----
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir "poetry==2.5.1" "poetry-plugin-export==1.9.0"

WORKDIR /build
COPY pyproject.toml poetry.lock ./

# Export to requirements.txt, then install normally
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime stage ----
FROM python:3.12-slim

COPY --from=builder /install /usr/local
COPY ./app /app/app
```

> **Do not install Poetry in the runtime image.** Export to `requirements.txt` in the build stage and use plain `pip` in the runtime stage. Poetry is a build tool, not a runtime dependency.

#### uv — Project lock and dependency synchronization

[uv](https://github.com/astral-sh/uv) is a Python package manager written in Rust by Astral (the makers of Ruff). It has a project lockfile (`uv.lock`) and cache-aware installation. Compare clean and warm-cache timings on your actual dependency set instead of assuming a fixed speedup.

```dockerfile
# ---- Build stage ----
FROM python:3.13-slim AS builder
WORKDIR /app

# Copy uv binary directly from the official image — no pip install needed
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./

# Install dependencies only (no project itself yet)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy source and install the project
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ---- Runtime stage ----
FROM python:3.13-slim

WORKDIR /app
COPY --from=builder /app /app

# uv creates a .venv inside /app — just put it on PATH
ENV PATH="/app/.venv/bin:$PATH"
```

**What each flag does:**

| Flag / Setting | Purpose |
|---|---|
| `COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/` | Copies a version-pinned uv toolchain from the official image; pin a digest as well when the supply-chain policy requires immutable image identity |
| `UV_COMPILE_BYTECODE=1` | Pre-compile `.pyc` files during install. Faster cold start (no compilation at runtime) |
| `UV_LINK_MODE=copy` | Copy files into `.venv` instead of symlinking. Required for multi-stage builds where the source layer won't exist |
| `--frozen` | Use the existing lock without checking freshness against project metadata |
| `--locked` | Fail if the project metadata would require changing the lock |
| `--no-install-project` | Install only dependencies, not the project itself. Used in the first `RUN` to cache deps separately from source |
| `--no-dev` | Skip dev dependencies (pytest, mypy, etc.) |
| `--mount=type=cache,target=/root/.cache/uv` | Docker BuildKit cache mount. uv's cache can persist across builds; benchmark warm/cold behavior |

**The two-step install pattern** is the key Docker optimization:

```
Step 1: COPY pyproject.toml uv.lock → uv sync --no-install-project
         (cached unless dependencies change)

Step 2: COPY src/ → uv sync
         (only re-runs when source code changes, deps already cached)
```

This is the same principle as the pip layer ordering trick (copy requirements before source), but uv makes it explicit with `--no-install-project`.

### Comparison: pip vs Poetry vs uv

| Concern | pip | Poetry | uv |
|---|---|---|---|
| Dependency input | Pinned requirements; `--require-hashes` verifies listed artifacts | `poetry.lock`, optionally exported with its explicit plugin | `uv.lock`, checked with `--locked` or `uv lock --check` |
| Layer caching | Order dependency input before source | Export and install before source when project structure permits | Sync dependencies before source, then install project |
| Bytecode | Normally compiled during install | Depends on install/export path | Explicit `UV_COMPILE_BYTECODE=1` |
| Runtime tools | Python base commonly includes pip | Keep Poetry in builder | Keep uv in builder; Python base can still contain pip |

`--frozen` is appropriate only when a separate gate established lock freshness or a partial build
context intentionally lacks project metadata. It is not that freshness gate. See
[uv locking](https://docs.astral.sh/uv/concepts/projects/sync/) and
[Poetry export plugin](https://python-poetry.org/docs/cli/#export), checked 2026-10-30.

### `pip install --no-cache-dir`

```bash
# ❌ Without --no-cache-dir
pip install -r requirements.txt
# Leaves ~100MB+ of cached wheels in /root/.cache/pip

# ✅ With --no-cache-dir
pip install --no-cache-dir -r requirements.txt
# No cache written, smaller image
```

Every MB multiplies across every pull, node, and deployment.

### Layer Ordering for Cache

Docker caches each layer. If a layer changes, **all subsequent layers are rebuilt**.

```dockerfile
# ❌ WRONG — changing any source file invalidates pip install cache
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
```

```dockerfile
# ✅ CORRECT — requirements change rarely, source code changes often
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ./app ./app
```

With the correct ordering, `pip install` is cached as long as `requirements.txt` doesn't change. This turns a 60-second build step into a 0-second cache hit.

---

## 11. Common Mistakes

### Mistake 1: Running as Root

```dockerfile
# ❌ Default — container runs as root
FROM python:3.12-slim
COPY . .
CMD ["uvicorn", "app.main:app"]
```

```dockerfile
# ✅ Create and use non-root user
FROM python:3.12-slim
RUN groupadd -r appuser && useradd -r -g appuser appuser
COPY . .
USER appuser
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0"]
```

### Mistake 2: Using Full Base Image

```dockerfile
# ❌ 1 GB image with gcc, make, man pages
FROM python:3.12

# ✅ 150 MB image with only what's needed
FROM python:3.12-slim
```

### Mistake 3: Missing `.dockerignore`

```
# Without .dockerignore:
Sending build context to Docker daemon  450MB   # includes .git, .venv, node_modules

# With .dockerignore:
Sending build context to Docker daemon  4.2MB   # just code and requirements
```

### Mistake 4: `COPY .` Before `pip install` (Cache Busting)

```dockerfile
# ❌ Every code change triggers a full pip install (60+ seconds)
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

# ✅ pip install is cached unless requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ./app ./app
```

### Mistake 5: No `PYTHONUNBUFFERED`

```dockerfile
# ❌ Logs are buffered — you see nothing during crashes
FROM python:3.12-slim

# ✅ Logs appear immediately
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
```

Without this, Python buffers stdout. When your container crashes, the last log lines are lost because they're still in the buffer.

### Mistake 6: Shell Form CMD

```dockerfile
# ❌ Shell form — signals go to /bin/sh, not your app
CMD uvicorn app.main:app --host 0.0.0.0

# ✅ Exec form — your app receives signals directly
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Mistake 7: No Health Check

```dockerfile
# ❌ Docker has no idea if your app is healthy
FROM python:3.12-slim
CMD ["uvicorn", "app.main:app"]

# ✅ Docker records unhealthy state; a separate controller owns remediation
FROM python:3.12-slim
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0"]
```

### Mistake 8: Storing Secrets in `ENV`

```dockerfile
# ❌ Secrets visible in image history (docker history)
ENV API_KEY=sk-live-abc123
ENV DATABASE_PASSWORD=supersecret

# ✅ Inject at runtime via env_file or orchestrator secrets
# Dockerfile has no secrets at all
```

Anyone with access to the image can run `docker history` and see every `ENV` instruction.

---

## 12. Complete Production Dockerfiles

### Option A: pip-based (Traditional)

```dockerfile
# ============================================================
# Stage 1: Build dependencies
# ============================================================
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ============================================================
# Stage 2: Production runtime
# ============================================================
FROM python:3.12-slim AS runtime

# Runtime-only system dependency for psycopg2
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Non-root user
RUN groupadd -r appuser && useradd -r -g appuser -s /sbin/nologin appuser

# Copy application code (last layer — changes most often)
COPY ./app ./app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--log-level", "warning", \
     "--limit-concurrency", "100", \
     "--timeout-keep-alive", "5"]
```

### Option B: uv-based (Recommended)

```dockerfile
# ============================================================
# Base: shared between builder and runner
# ============================================================
FROM python:3.13-slim-bookworm AS base

WORKDIR /app

# ============================================================
# Stage 1: Build dependencies with uv
# ============================================================
FROM base AS builder

# Single static binary — no pip install, no version conflicts
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Step 1: Install dependencies only (cached unless pyproject.toml/uv.lock change)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Step 2: Copy source and install the project
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# ============================================================
# Stage 2: Production runtime (no uv, no build tools)
# ============================================================
FROM base AS runner

# Copy the entire /app (includes .venv with all dependencies)
COPY --from=builder /app /app

# .venv/bin has python, uvicorn, gunicorn — put it on PATH
ENV PATH="/app/.venv/bin:$PATH"

# Non-root user
RUN groupadd -r app \
 && useradd -m -r -g app -d /home/app app \
 && chown -R app:app /home/app /app

ENV HOME=/home/app

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--log-level", "warning", \
     "--limit-concurrency", "100", \
     "--timeout-keep-alive", "5"]
```

Compare builds using the same base digest, dependency versions, target architecture and cache
state. Record build duration, compressed image size and startup latency. Both installers need build
tools only for dependencies built from source; pip normally compiles bytecode and the shown Python
runtime base includes pip even when uv is confined to the builder.

> **Note on Gunicorn:** If you're running behind Gunicorn (recommended for non-Kubernetes deployments), replace the `CMD` with:
> ```dockerfile
> CMD ["gunicorn", "-k", "uvicorn_worker.UvicornWorker", \
>      "-w", "4", "-b", "0.0.0.0:8000", \
>      "--access-logfile", "-", \
>      "--max-requests", "10000", \
>      "--max-requests-jitter", "1000", \
>      "app.main:app"]
> ```

---

## 13. Summary

### Layer Responsibilities

| Layer | Decides | Configured By |
|-------|---------|---------------|
| Dockerfile | What's in the image | Developer |
| Uvicorn | How the ASGI server behaves | Flags or env vars |
| Gunicorn | Process management and recycling | Config file or flags |
| Docker Compose | How services connect | `docker-compose.yml` |
| Health checks | Is this instance usable | `/health` + `/ready` endpoints |
| Graceful shutdown | How to stop without data loss | Lifespan + signal handling |

### Quick Reference

```bash
# Build
docker build -t myapp:latest .

# Run
docker run -p 8000:8000 --env-file .env myapp:latest

# Development
docker compose up --build

# Production (single VM)
docker compose -f docker-compose.prod.yml up -d

# Check health
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### The Key Insight

> **A container is not a VM. It is a process with isolated filesystem and network.**

Treat it that way: small images, single process, no state, fast startup, clean shutdown. Everything else — scaling, failover, routing — is the orchestrator's job.

---

## Continue to deployment controllers

The [release lesson](02_ci_cd_and_releases.md) owns rolling/canary/blue-green choices, shared-schema
compatibility and rollback rehearsal. A routing flip does not undo database changes, drain old
requests instantly or stop old background workers. Coexistence safety must be proved for either
strategy. The [Kubernetes lesson](03_kubernetes_runtime.md) owns probes, resource/connection budgets,
PDB limits and termination overlap; avoid copying a second deployment recipe here.

## Recap

- An image fixes files and dependency inputs; its tested digest identifies the promoted artifact.
- Docker health is observation. Restart, traffic withdrawal and process exit have separate owners.
- Exec form or a forwarding supervisor delivers SIGTERM; the server drains before lifespan cleanup.
- Resource acquisition registers cleanup immediately, so partial startup cannot leak earlier resources.
- Worker counts multiply admission and pools; budget the whole fleet, including rollout overlap.

**An ordinary container remains running but health is unhealthy. Will its restart policy repair it?**

<details><summary>Answer</summary>

No. The restart policy reacts to process exit; health status alone does not exit it. Diagnose the
failed check and configure an appropriate controller if automatic remediation is needed. Restarting
a healthy process cannot repair a shared database outage.

</details>

**A response stream is still sending after `call_next` returns. Has the request finished draining?**

<details><summary>Answer</summary>

No. Headers and body completion are different events. Track the entire ASGI call and let the server
await bounded requests before cleanup. A counter ending at header return undercounts active streams.

</details>

**Try it:** In the lab, change `/slow` to take 5 seconds and reduce Uvicorn's drain timeout to 2.
Keep outer grace at 12. Predict the client result and which assertion fails before running it.
Hint: the process has time for cleanup even when the in-flight response exceeds its own budget.

<details><summary>Worked solution</summary>

The server cancels the request after its shorter drain budget, so the assertion expecting a complete
200 response fails. Lifespan may still finish and the process may exit within 12 seconds. Restore a
server budget longer than the bounded request plus cleanup allowance, rebuild, and rerun the
unchanged driver. Do not interpret “exited quickly” as proof that every response was preserved.

</details>
