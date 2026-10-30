# Part 3: Client Delivery Patterns

<!-- length-justification: The delivery variants remain together because their central decision matrix and shared durable-status recovery contract are the canonical comparison; each implementation is a bounded protocol excerpt rather than a separate tutorial. -->

> **Who this is for**: Engineers returning long-running job status and progress to browsers, scripts,
> or partner services.

How the client gets the result back after submitting a long-running task. Every pattern starts the same way: the client sends a request, gets a `202 Accepted` with a job ID, and then... what?

> **Key insight**: Push reduces notification latency but never replaces a durable status read used
> for reconnect, replay, and missed-message recovery.

---

## One result contract survives every connection

The canonical [durable job](../../background_work/foundations/03_minimal_durable_task.md)
retains the state. Every transport below carries the same envelope:

```json
{"job_id":"abc","state":"succeeded","generation":2,"result":{"label":"billing"}}
```

`state` is `pending`, `running`, `succeeded`, or `failed`; a failed envelope carries a public
`error` code. `generation` identifies the accepted worker attempt. Treat cancellation separately
if your application adds it. These are protocol excerpts: authentication, authorization, durable
storage and notification adapters come from the application, not an in-memory replacement here.

This timeline separates a result from the connection that announces it:

```mermaid
sequenceDiagram
    participant C as Client
    participant J as Durable job abc
    participant A as Worker generation 1
    participant B as Worker generation 2
    A->>J: Claim generation 1
    Note over A,J: Lease expires; process may still run
    B->>J: Claim generation 2
    B->>J: Commit succeeded plus result if owner is 2
    J--xC: Completion notification lost
    A->>J: Complete with generation 1
    J-->>A: Reject stale owner
    C->>J: Authorized GET after reconnect
    J-->>C: state=succeeded, generation=2
```

The successful row survives a missed notification. The stale worker cannot replace it because its
conditional write names generation 1. A heartbeat timeout permits reassignment; it cannot prove
that worker 1 has stopped. Start with the read contract, then add whichever connection lowers the
latency your client needs.

## Start with short polling

The client periodically hits a status endpoint. Simplest pattern to implement; most wasteful of resources.

### Flow

```
Client                              Server
  │                                      │
  │── POST /jobs {payload} ──►           │
  │◄── 202 {job_id} ──                   │
  │                                      │
  │── GET /jobs/{job_id} ──►             │
  │◄── {"state": "pending"} ──          │
  │                                      │
  │    (wait 2 seconds)                  │
  │                                      │
  │── GET /jobs/{job_id} ──►             │
  │◄── {"state": "running",             │
  │     "progress": 45} ──               │
  │                                      │
  │    (wait 2 seconds)                  │
  │                                      │
  │── GET /jobs/{job_id} ──►             │
  │◄── {"state": "succeeded",           │
  │     "result": {...}} ──              │
```

### Client Implementation

The caller supplies an authenticated HTTPX client; the helper owns the *whole* waiting budget.
HTTP status errors are not job states. Reconnects use this same durable read, even after push fails.

```python
import asyncio
import httpx

async def poll_for_result(client: httpx.AsyncClient, job_id: str,
                          interval: float = 2.0, timeout: float = 600.0):
    if interval <= 0 or timeout <= 0:
        raise ValueError("positive interval and timeout required")
    async with asyncio.timeout(timeout):
        while True:
            response = await client.get(f"/jobs/{job_id}", timeout=10.0)
            response.raise_for_status()
            data = response.json()
            if data["state"] == "succeeded":
                return data["result"]
            if data["state"] == "failed":
                raise RuntimeError(data.get("error", "Task failed"))
            await asyncio.sleep(interval)
```

The outer timeout includes slow response bodies and sleeps, whereas HTTPX's phase timeouts
limit inactivity within one request. For backoff, update the interval after the sleep with
`interval = min(interval * 1.5, 30.0)` and add jitter across clients. Keep the same outer deadline;
backoff changes request frequency, not how long the caller agreed to wait.

### Characteristics

| Aspect | Detail |
|--------|--------|
| **Latency** | Medium — bounded by polling interval |
| **Server cost** | Medium — repeated HTTP requests, but no held connections |
| **Client complexity** | Lowest — just a loop |
| **Progress updates** | Yes — each poll returns current status |
| **Infrastructure** | Any HTTP stack, no special requirements |
| **Best for** | Server-to-server integrations, simple clients, batch scripts |

---

## Pattern 1: WebSocket

The client opens a persistent bidirectional connection. The server pushes the result (and optionally progress updates) when ready.

### Flow

```
Client                              Server (Orchestrator)
  │                                      │
  │── POST /jobs {payload} ──►           │
  │◄── 202 {job_id} ──                   │── dispatch to worker
  │                                      │
  │── WS CONNECT /ws/jobs/{job_id} ──►   │
  │◄── connection established ──         │
  │                                      │
  │    (connection held open)            │    (worker processing)
  │                                      │
  │◄── WS: {"progress": 30} ──           │◄── worker heartbeat
  │◄── WS: {"progress": 70} ──           │◄── worker heartbeat
  │◄── WS: {"state": "succeeded",            │◄── worker callback
  │         "result": {...}} ──          │
  │                                      │
  │── WS CLOSE ──►                       │
```

### Server Implementation

Use the complete [bounded notification server](../../apis/examples/websocket_notifications/app.py)
and its [launch and test instructions](../../apis/websockets/06_implementation_testing_and_operations.md).
It owns one sender per connection, a bounded outbound queue, a send deadline, and a supervisor
that cancels and joins the sender/receiver before attempting a bounded close. Publishers put
messages in the queue; they never call `send_json` on another task's connection. A full queue
signals the supervisor independently of that queue, so a blocked send cannot hide overload.

For jobs, adapt the application boundary as follows; these adapters require your durable store:

| Boundary | Job adapter and invariant |
|---|---|
| Authentication | Keep the canonical route's session validation, Origin allowlist and required subprotocol; authorize each requested job against the authenticated tenant/user. |
| Subscription | Register the connection before reading authorized durable status; queue that snapshot through the same sender. Serialize snapshot and later updates or reject an older generation/revision at the client. |
| Publication | After committed job changes, route the shared envelope only to currently authorized job subscribers; both progress and heartbeat responses use the outbound queue. |
| Slow consumer | Close with `1013` after the bounded sender stops; the client reconnects and reads durable status. Progress may be coalesced, but the durable terminal state remains recoverable. |
| Revocation | Recheck permission on subscription and application policy expiry; close sessions whose authorization expires. The canonical local fixture validates its short session at connection setup only. |

A process-local hub only reaches that process. A broker subscriber per API process can feed its
hub; a lost broker hint still recovers from the job row. The complete server is a transport lab,
not a job database or a substitute for tenant-aware subscription policy.

### Client Implementation (JavaScript)

```javascript
async function submitAndWait(payload) {
    // 1. Submit the job
    const res = await fetch('/jobs', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
    if (!res.ok) throw new Error(`Submit failed: ${res.status}`);
    const { job_id } = await res.json();

    // 2. Connect WebSocket for result
    return new Promise((resolve, reject) => {
        const ws = new WebSocket(`wss://api.example.com/ws/jobs/${job_id}`);

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.state === 'succeeded') {
                resolve(msg.result);
                ws.close();
            } else if (msg.state === 'failed') {
                reject(new Error(msg.error));
                ws.close();
            } else if (msg.progress !== undefined) {
                updateProgressBar(msg.progress);
            }
        };

        ws.onerror = () => reject(new Error('WebSocket error'));

        // Timeout safety net
        setTimeout(() => { ws.close(); reject(new Error('Timeout')); }, 600_000);
    });
}
```

### Characteristics

| Aspect | Detail |
|--------|--------|
| **Latency** | Near-instant — push-based |
| **Server cost** | High — one open connection per waiting client |
| **Client complexity** | Medium — must handle reconnection, missed messages |
| **Progress updates** | Native — bidirectional channel |
| **Infrastructure** | Requires WebSocket-capable load balancer (ALB, nginx, Cloudflare) |
| **Scalability** | Measure connection memory, file descriptors, send buffers and proxy limits |
| **Best for** | Interactive UIs, real-time dashboards, when progress updates matter |

### Edge Cases

- **Client disconnects and reconnects**: Must handle "catch-up" — on reconnect, send current status and any missed updates. Store updates in Redis sorted set or similar.
- **Load balancer timeout**: AWS ALB's idle timeout defaults to 60s and is configurable up to 4000s. Send periodic pings to keep the connection alive.
- **Multiple tabs**: Same job, multiple WebSocket connections. Use Redis pub/sub to fan out.

---

## Pattern 2: Server-Sent Events (SSE)

Unidirectional server-to-client push over HTTP. Simpler than WebSocket — no upgrade handshake, works through most proxies, automatic reconnection built into the browser API.

### Flow

```
Client                              Server
  │                                      │
  │── POST /jobs {payload} ──►           │
  │◄── 202 {job_id} ──                   │
  │                                      │
  │── GET /jobs/{job_id}/stream ──►      │
  │◄── Content-Type: text/event-stream   │
  │◄── data: {"progress": 30}            │
  │◄── data: {"progress": 70}            │
  │◄── data: {"state": "succeeded", ...}     │
  │◄── (connection closed by server)     │
```

### Server Implementation

```python
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json

@app.get("/jobs/{job_id}/stream")
async def job_stream(job_id: str, principal=Depends(get_current_principal)):
    if not await principal_can_read_job(principal, job_id):
        raise HTTPException(status_code=404, detail="job not found")

    async def event_generator():
        while True:
            status = await get_job_status(job_id)

            yield f"data: {json.dumps(status)}\n\n"

            if status["state"] in ("succeeded", "failed"):
                return

            await asyncio.sleep(2)  # Poll interval

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### Client Implementation (JavaScript)

```javascript
const evtSource = new EventSource(`/jobs/${jobId}/stream`);

evtSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.state === 'succeeded') {
        handleResult(data.result);
        evtSource.close();
    } else if (data.state === 'failed') {
        handleError(data.error);
        evtSource.close();
    }
};

// EventSource auto-reconnects on network failure — built into the spec
```

### Characteristics

| Aspect | Detail |
|--------|--------|
| **Latency** | Low — push-based with small polling delay on server side |
| **Server cost** | Medium — one open HTTP connection per client (lighter than WS) |
| **Client complexity** | Low — `EventSource` API handles reconnection |
| **Progress updates** | Yes — natural fit |
| **Infrastructure** | No protocol upgrade, but buffering and idle-timeout settings must permit streaming |
| **Best for** | Progress updates, when you don't need client-to-server messages |

---

Disable proxy response buffering for the event-stream route, send periodic comment heartbeats
before the shortest proxy idle timeout, and cancel the generator when the client disconnects.
Verify with `curl -N`: progress lines should appear at their production intervals, not arrive in
one batch when the response closes. A buffered SSE response is not working push delivery.

## Pattern 4: Long Polling

The client sends a request, and the server holds it open until the result is ready (or a timeout elapses). Reduces the number of round-trips compared to short polling.

### Flow

```
Client                              Server
  │                                      │
  │── POST /jobs {payload} ──►           │
  │◄── 202 {job_id} ──                  │
  │                                      │
  │── GET /jobs/{job_id}?wait=30 ──►     │
  │    (server holds request for         │
  │     up to 30 seconds)               │
  │                                      │    (worker completes at T+12s)
  │◄── {"state": "succeeded", ...} ──  │    (server responds immediately)
```

### Server Implementation

```python
from typing import Annotated
from fastapi import Depends, HTTPException, Query

_waiters: dict[str, set[asyncio.Event]] = {}

@app.get("/jobs/{job_id}")
async def get_job(job_id: str, wait: Annotated[int, Query(ge=0, le=30)] = 0,
                  principal=Depends(get_current_principal)):
    if not await principal_can_read_job(principal, job_id):
        raise HTTPException(status_code=404, detail="job not found")
    event = asyncio.Event()
    _waiters.setdefault(job_id, set()).add(event)  # subscribe before reading
    try:
        status = await get_job_status(job_id)
        if wait and status["state"] not in ("succeeded", "failed"):
            try:
                await asyncio.wait_for(event.wait(), timeout=wait)
            except TimeoutError:
                pass
            status = await get_job_status(job_id)
        return status
    finally:
        _waiters[job_id].discard(event)
        if not _waiters[job_id]:
            del _waiters[job_id]
```

A local notifier sets every registered event after a committed change. Multiple API processes need
a broadcast adapter per process; reconnect and the bounded timeout always re-read durable state.
Subscribe-before-read closes the commit-between-read-and-subscribe race. A lost broadcast can
increase latency to 30 seconds, but does not lose the result. Recheck permission on each new request.


### Characteristics

| Aspect | Detail |
|--------|--------|
| **Latency** | Low — near-instant once result is ready |
| **Server cost** | Medium — held connections, but fewer total requests than short polling |
| **Client complexity** | Low — same as short polling, just with a `wait` parameter |
| **Infrastructure** | Needs server/LB timeouts > wait parameter |
| **Best for** | When you want low latency but can't use WebSocket/SSE |

---

## Pattern 5: Webhook (Client Callback)

The client provides a callback URL when submitting the job. The server POSTs the result to that URL when done.

### Flow

```
Client                              Server                      Worker
  │                                      │                         │
  │── POST /jobs                         │                         │
  │   {payload, callback_url} ──►        │                         │
  │◄── 202 {job_id} ──                   │── dispatch ──►          │
  │                                      │                         │── work
  │                                      │                         │
  │                                      │            ◄── done ────│
  │               ◄── POST callback_url  │                         │
  │                   {job_id, result}   │                         │
  │── 200 OK ──►                         │                         │
```

### Server Implementation

Submission and completion each commit their durable intent in one database transaction. The
following asyncpg excerpt uses this minimal schema (run only in a disposable learning database):

```sql
CREATE TABLE delivery_jobs (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    callback_registration_id TEXT,
    state TEXT NOT NULL DEFAULT 'pending',
    generation BIGINT NOT NULL DEFAULT 0,
    lease_expires_at TIMESTAMPTZ,
    result JSONB
);
CREATE TABLE job_dispatch_outbox (
    job_id TEXT PRIMARY KEY REFERENCES delivery_jobs(id),
    state TEXT NOT NULL DEFAULT 'pending'
);
CREATE TABLE callback_deliveries (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES delivery_jobs(id),
    registration_id TEXT NOT NULL,
    body BYTEA NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (job_id)
);
```

```python
import json
from uuid import uuid4

async def create_job_intent(db, tenant_id: str, payload: dict, callback_id: str | None):
    job_id = uuid4().hex
    async with db.transaction():
        await db.execute(
            "INSERT INTO delivery_jobs (id,tenant_id,payload,callback_registration_id) "
            "VALUES ($1,$2,$3::jsonb,$4)",
            job_id, tenant_id, json.dumps(payload), callback_id,
        )
        await db.execute("INSERT INTO job_dispatch_outbox (job_id) VALUES ($1)", job_id)
    return job_id  # Both rows have committed before the HTTP response.

async def on_worker_complete(db, job_id: str, generation: int, result: dict) -> bool:
    async with db.transaction():
        job = await db.fetchrow(
            "UPDATE delivery_jobs SET state='succeeded', result=$3::jsonb "
            "WHERE id=$1 AND generation=$2 AND state='running' "
            "AND lease_expires_at > clock_timestamp() "
            "RETURNING callback_registration_id",
            job_id, generation, json.dumps(result),
        )
        if job is None:
            return False  # Stale generation, expired lease, or already terminal.
        if job["callback_registration_id"] is not None:
            body = json.dumps(
                {"job_id": job_id, "state": "succeeded", "generation": generation,
                 "result": result}, separators=(",", ":"), sort_keys=True,
            ).encode("utf-8")
            await db.execute(
                "INSERT INTO callback_deliveries (id,job_id,registration_id,body) "
                "VALUES ($1,$2,$3,$4)",
                f"{job_id}-{generation}", job_id, job["callback_registration_id"], body,
            )
    return True  # Terminal result and callback intent commit or roll back together.
```

The authenticated POST handler resolves a tenant-owned `callback_id` before calling
`create_job_intent`; it never persists an arbitrary callback URL. Return `202` with the job ID
only after this call commits. Give retrying POSTs a tenant-scoped idempotency key as taught in
[the durable submission contract](../../background_work/foundations/03_minimal_durable_task.md).
A dispatcher scans `job_dispatch_outbox`; a broker outage leaves a pending row, and a crash after
publish can redeliver the same job ID. The worker claim/reclaim protocol in
[Part 2](02_worker_patterns.md) increments the generation and sets the lease in `delivery_jobs`.
Only a trusted worker identity may request completion, and its generation must match the live
claim. The conditional update locks the matching row until the callback insert commits. No
remote call occurs inside that transaction.

A callback dispatcher scans the committed `callback_deliveries` table directly. There is no
separate record-then-enqueue step that can strand a notification. The adapter below maps its
`delivery.delivery_id` to the table's stable `id`; claiming and retry scheduling must use the
same owner/generation predicates described in Part 2. Two send attempts can still overlap after
a lease expires, so the receiver must deduplicate the stable signed ID.

```python
import base64
import hashlib
import hmac
import httpx
import random
import time

async def deliver_callback(delivery_id: str):
    delivery = await callback_deliveries.get(delivery_id)
    registration = await load_callback_registration(delivery.registration_id)
    body = delivery.body
    try:
        timestamp = str(int(time.time()))
        signature = hmac.new(
            registration.signing_secret,
            delivery.delivery_id.encode("ascii") + b"." + timestamp.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()

        # The egress service owns the verified registration and enforces HTTPS,
        # DNS resolution at connect time, private/link-local/loopback rejection,
        # no redirects, and network egress policy. The worker never fetches a
        # caller-controlled URL directly.
        response = await callback_egress_client.post(
            "/v1/deliver",
            json={
                "registration_id": registration.id,
                "body_base64": base64.b64encode(body).decode("ascii"),
                "headers": {
                    "Content-Type": "application/json",
                    "X-Webhook-Version": "v1",
                    "X-Webhook-Timestamp": timestamp,
                    "X-Webhook-Signature": f"v1={signature}",
                    "X-Webhook-Delivery": delivery.delivery_id,
                },
            },
            timeout=10,
        )
        response.raise_for_status()
        await callback_deliveries.mark_delivered(delivery.id, delivered_at=time.time())
    except httpx.HTTPError as exc:
        attempt = delivery.attempt_count + 1
        if attempt >= 8:
            await callback_deliveries.mark_failed(
                delivery.id, attempt_count=attempt, last_error=type(exc).__name__
            )
            callback_delivery_failed_total.inc()
        else:
            delay = min(900, 2**attempt) + random.uniform(0, 1)
            await callback_deliveries.schedule_retry(
                delivery.id,
                attempt_count=attempt,
                next_attempt_at=time.time() + delay,
                last_error=type(exc).__name__,
            )
```

A dispatcher queries durable `pending` rows whose `next_attempt_at` is due. Success is visible as a
`delivered` row and counter; exhaustion is an inspectable `failed` row plus
`callback_delivery_failed_total`, not a webhook silently abandoned after an in-memory loop.

The sender signs `<delivery_id>.<timestamp>.<raw_body>` with HMAC-SHA256. Delivery IDs are
server-generated ASCII identifiers, stable across retries. A timestamp limits the age of this
attempt; the signed delivery ID binds retry identity to the body. A changed timestamp needs a new
signature, while a new signature does not turn the same delivery into new work.

```python
import hashlib
import hmac
import json
import re
import time

async def verify_callback(raw_body: bytes, headers, secret: bytes, replay_store) -> dict:
    try:
        timestamp = headers["X-Webhook-Timestamp"]
        delivery_id = headers["X-Webhook-Delivery"]
        signature = headers["X-Webhook-Signature"]
        if (headers.get("X-Webhook-Version") != "v1"
                or not re.fullmatch(r"[0-9]{1,12}", timestamp)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", delivery_id)
                or not re.fullmatch(r"v1=[0-9a-f]{64}", signature)):
            raise ValueError("malformed webhook")
        if abs(int(time.time()) - int(timestamp)) > 300:
            raise ValueError("stale webhook")
        expected = hmac.new(
            secret,
            delivery_id.encode("ascii") + b"." + timestamp.encode("ascii")
            + b"." + raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature[3:], expected):
            raise ValueError("invalid webhook signature")
        payload = json.loads(raw_body)
        if not isinstance(payload, dict):
            raise ValueError("object body required")
    except (KeyError, TypeError, UnicodeError) as exc:
        raise ValueError("malformed webhook") from exc
    # Atomic durable insert of (registration_id, delivery_id, raw_body, pending).
    # This store is scoped to the already authenticated registration.
    # Same ID/body returns existing state; same ID/different body raises conflict.
    await replay_store.admit(delivery_id, raw_body)
    return payload
```

Return a successful intake response only after `admit` commits. A separate worker claims pending
inbox rows and commits its local effect plus completion together. An existing pending row must
remain runnable after receiver restart; recording only a short-lived “seen” key would lose work
if the process died before the effect. Retain delivery identity for the sender's entire supported
retry/manual-replay horizon, which can be days; the five-minute signature window is unrelated.
For remote effects, use the destination's idempotency key and reconcile ambiguous timeouts.
The [webhook intake course](../../apis/webhooks/README.md) owns the full durable inbox protocol.

Run the local verifier/inbox crash fixture from the repository root:

```bash
python3 architecture/long_running_tasks/examples/recovery_contracts.py
```

With `asyncpg` installed and local Docker available, execute the current submission/completion
fences against an automatically removed PostgreSQL 17 container:

```bash
python3 architecture/long_running_tasks/examples/verify_delivery_transaction.py
```

The transaction probe rejects stale and expired claims, rolls back a result when delivery insertion
fails, and reconnects to verify that the generation-bearing pending delivery survives. The first
script extracts the verifier above and checks identity substitution, malformed signatures, replay after
receiver restart and body conflicts using a disposable SQLite inbox. It does not verify a deployed
webhook route, broker or remote side effect.

### Characteristics

| Aspect | Detail |
|--------|--------|
| **Latency** | Lowest — push-based, no polling overhead |
| **Server cost** | Lowest — no held connections, no polling load |
| **Client complexity** | Medium — must expose an endpoint, handle retries, verify authenticity |
| **Infrastructure** | Client must be reachable from server (not always possible) |
| **Best for** | Server-to-server, CI/CD pipelines, Slack/GitHub-style integrations |

### Security Considerations

- **HMAC verification**: Sign the callback payload with a shared secret so the client can verify it came from your server.
- **Idempotency**: The client's callback endpoint must be idempotent (same delivery = same effect) because retries will happen.
- **Allowlisting**: Validate callback URLs to prevent SSRF (don't POST to `http://169.254.169.254/`).

---

## Pattern 6: Redis Pub/Sub Notification

The client subscribes to a Redis channel for the job. The orchestrator publishes the result when the worker completes.

### Flow

```
Client                     Redis                     Orchestrator
  │                           │                           │
  │── SUBSCRIBE job:{id} ──►  │                           │
  │   (blocking listen)       │                           │
  │                           │                           │── worker completes
  │                           │  ◄── PUBLISH job:{id}     │
  │                           │      {result}             │
  │◄── message received ──    │                           │
  │── UNSUBSCRIBE ──►         │                           │
```

### Client Implementation (Python)

```python
import redis.asyncio as redis

async def wait_for_result(redis_client: redis.Redis, job_id: str, timeout: float = 600.0):
    pubsub = redis_client.pubsub()
    try:
        await pubsub.subscribe(f"job:{job_id}")
        async with asyncio.timeout(timeout):
            async for message in pubsub.listen():
                if message["type"] == "message":
                    return json.loads(message["data"])
    finally:
        await pubsub.unsubscribe(f"job:{job_id}")
        await pubsub.aclose()
```

### With Fallback (Pub/Sub + Polling)

Pub/Sub is fire-and-forget — if the client subscribes *after* the result is published, it misses it. Always combine with a check:

```python
async def wait_for_result_safe(redis_client: redis.Redis, job_id: str, timeout: float = 600.0):
    # 1. Check if already done (race condition safety)
    existing = await redis_client.get(f"result:{job_id}")
    if existing:
        return json.loads(existing)

    # 2. Subscribe and wait
    pubsub = redis_client.pubsub()
    try:
        await pubsub.subscribe(f"job:{job_id}")

        # 3. Check again after subscribing (close the race window)
        existing = await redis_client.get(f"result:{job_id}")
        if existing:
            return json.loads(existing)

        # 4. Wait for pub/sub message under the caller's deadline
        async with asyncio.timeout(timeout):
            async for message in pubsub.listen():
                if message["type"] == "message":
                    return json.loads(message["data"])
    finally:
        await pubsub.unsubscribe(f"job:{job_id}")
        await pubsub.aclose()
```

### Characteristics

| Aspect | Detail |
|--------|--------|
| **Latency** | Near-instant (pub/sub) |
| **Server cost** | Low — Redis handles the fan-out |
| **Client complexity** | Medium — must handle subscribe/unsubscribe lifecycle, race conditions |
| **Infrastructure** | Requires shared Redis instance accessible to both client and server |
| **Best for** | Internal microservices, when Redis is already in the stack |

---

## Comparison Matrix

| Pattern | Latency | Server Load | Client Complexity | Needs Special Infra | Real-Time Progress | Best For |
|---------|---------|-------------|-------------------|--------------------|--------------------|----------|
| **WebSocket** | Instant | High (connections) | Medium | WS-capable LB | Yes | Interactive UIs |
| **SSE** | Instant | Medium | Low | None | Yes | Progress bars, dashboards |
| **Short Polling** | Medium | Medium (requests) | Lowest | None | Yes (per-poll) | Scripts, simple clients |
| **Long Polling** | Low | Medium (held conns) | Low | Longer LB timeouts | No (one-shot) | Low-latency without WS |
| **Webhook** | Instant | Lowest | Medium | Client must be reachable | No | Server-to-server |
| **Redis Pub/Sub** | Instant | Low | Medium | Shared Redis | No (one-shot) | Internal microservices |

---

## Combining Patterns

Start with the durable status endpoint. Add delivery mechanisms only for a demonstrated client requirement; every additional transport needs its own authorization and recovery checks.

```python
@app.post("/jobs")
async def create_job(
    payload: dict,
    callback_id: str | None = None,   # Webhook delivery
    # Client can also:
    # - Connect to /ws/jobs/{id} for WebSocket
    # - GET /jobs/{id}/stream for SSE
    # - GET /jobs/{id} for polling
    # - SUBSCRIBE job:{id} on Redis for pub/sub
):
    ...
```

A typical production API offers:
1. **Short polling** as the universal fallback (always works)
2. **WebSocket or SSE** for interactive clients that need progress
3. **Webhook** for server-to-server integrations

## Choose under a changed condition

**An internal consumer starts after the Redis notification was published. What can it recover?**

<details><summary>Reasoned answer</summary>

Pub/Sub retains no message for the absent subscriber. Read durable status, subscribe, then recheck
before waiting; use a bounded wait and re-read on reconnect. If the consumer is a browser without
Redis access, the API performs this reconciliation and exposes authorized polling or SSE. A new
transport does not replace the retained job row.

</details>

**Worker 2 committed `succeeded`, its push vanished, and worker 1 later calls back. What changes?**

<details><summary>Reasoned answer</summary>

Nothing changes in the durable result: the generation predicate rejects worker 1. Polling reads
success immediately; SSE/WebSocket recover it on reconnect; a webhook sender retries its durable
delivery. A transport failure changes notification latency, not who may commit the result.

</details>
