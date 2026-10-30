# Safe and Scalable External API Calls

> **Who this is for**: FastAPI engineers calling LLMs, agents, and external APIs under bounded
> capacity and partial failure.

> **Key insight**: Admit work before execution and keep local overload distinct from retryable
> dependency failure.

---

## First runnable baseline: classify capacity separately from dependency failure

This self-contained transport makes no network call. It runs one success, one local admission
failure, and one downstream read failure, then closes the client:

```python
import asyncio
import httpx


class AdmissionTimeout(Exception):
    pass


async def provider(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/slow":
        raise httpx.ReadTimeout("provider stalled", request=request)
    return httpx.Response(200, json={"result": "ok"})


async def call(client: httpx.AsyncClient, gate: asyncio.Semaphore, path: str):
    try:
        async with asyncio.timeout(0.01):
            await gate.acquire()
    except TimeoutError as exc:
        raise AdmissionTimeout("local capacity unavailable") from exc

    try:
        return await client.get(f"https://provider.test{path}")
    finally:
        gate.release()


async def main() -> None:
    gate = asyncio.Semaphore(1)
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        response = await call(client, gate, "/ok")
        print(response.status_code, response.json())

        await gate.acquire()  # hold local capacity to make admission fail
        try:
            await call(client, gate, "/ok")
        except AdmissionTimeout:
            print("admission_timeout")
        finally:
            gate.release()

        try:
            await call(client, gate, "/slow")
        except httpx.ReadTimeout:
            print("downstream_read_timeout")


asyncio.run(main())
# 200 {'result': 'ok'}
# admission_timeout
# downstream_read_timeout
```

The semaphore wait fails before execution and must not be retried locally; `ReadTimeout` means an
admitted provider attempt stalled and may be eligible for a bounded retry if the operation is
idempotent. If the program hangs instead of printing `admission_timeout`, the capacity wait is not
inside its own deadline.

**Stop here** to explain the difference between local admission and provider failure. This tiny mock is not the complete transport/deadline policy.
Continue when real load introduces queues, retries, multiple pods, or shared provider quotas.

---

## Prerequisites

Before reading this guide, understand HTTPX internals:

**[HTTPX Guide](../../httpx/README.md)** — connection pooling, timeouts, and HTTP client behavior.

---

## Core Principle

Concurrency exists at several boundaries. A semaphore can strictly cap admitted application work,
while the HTTP client's pool strictly caps simultaneous connections. Neither cap substitutes for
the other: queued coroutines still consume memory, and a socket cap alone does not enforce tenant or
provider policy.

---

## Contents

| Part | Topic | Description |
|------|-------|-------------|
| [01](01_core_concepts.md) | Core Concepts | Mental model, the real concurrency limit, fundamental bound |
| [02](02_concurrency_and_timeouts.md) | Concurrency & Timeouts | Timeout layers, asyncio vs httpx, what each controls |
| [03](03_call_patterns.md) | Call Patterns | One bounded implementation, retry eligibility, typed failures |
| [04](04_kubernetes.md) | Kubernetes | Multi-pod concerns, local vs global limits |
| [05](05_production_architecture.md) | Production Architecture | Complete stack, execution order, deployment |
| [06](06_advanced_patterns.md) | Advanced Patterns | Circuit breakers, bulkheads, hedging, priority queues, load shedding |
| [07](07_streaming_patterns.md) | Streaming Patterns | SSE, streaming timeouts, semaphore duration |
| [08](08_streaming_advanced.md) | Streaming Advanced | Retained stream owners, first-useful-frame race, bounded merge and replay |
| [09](09_distributed_admission_control.md) | Distributed Admission Control | Atomic leased attempts, stable recovery identities, rate and concurrency limits |
| [10](10_llm_token_economics.md) | LLM Token Economics | Durable PostgreSQL reservation, every-attempt usage, unknown outcomes and reconciliation |
| [11](11_idempotency.md) | Idempotency Keys | Tenant-scoped PostgreSQL effect/result transaction, fenced recovery and remote identity |

---

## One composed implementation

[Part 3](03_call_patterns.md#run-one-operation-before-studying-the-policy) supplies the complete
caller, local app and tests. Its active-owner cap and waiter cap are separate. The admission
timer exits before execution begins; the original total clock remains around every attempt
and sleep. Optional rate and shared-admission policies are added only when the provider or
product has that quota.

Use that implementation when adding behavior so exception classification, cancellation and
resource ownership cannot drift between copied production variants.

---

## Key Principles

1. **Outer deadlines bound total wall time** — `asyncio.timeout()` cancels the waiting task
2. **HTTPX timeouts bound transport phases/inactivity** — they are not a total deadline
3. **Rate limiting ≠ concurrency control** — they serve different purposes
4. **Retries must be outside semaphore** — never sleep while holding resources
5. **Quota scope must match its owner** — use shared atomic decisions or conserved allocations across processes
6. **Queue timeout is not retryable** — overload should fail fast

---

## Common Mistakes This Guide Prevents

❌ Client without connection limits (unbounded sockets)
❌ Using only one total deadline without phase limits or failure-specific diagnostics
❌ Holding a permit across retry sleep
❌ Missing waiter-count bound or admission deadline
❌ Per-pod rate limiters for vendor protection
❌ One circuit-breaker state shared across unrelated dependency partitions or failure domains
❌ Catching only `asyncio.TimeoutError` (missing httpx exceptions)
❌ Retrying queue timeouts (amplifies overload)

---

## Learning paths

### For Beginners

**Working result by entry 2**: run the Quick Start above, then explain why admission failure and a
downstream attempt timeout take different retry paths.

1. **Do:** run the [first baseline](#first-runnable-baseline-classify-capacity-separately-from-dependency-failure) and observe its three outcomes.
2. **Understand capacity:** [Core Concepts](01_core_concepts.md) traces admitted attempts, waiting tasks and connections.
3. **Understand time:** [Concurrency & Timeouts](02_concurrency_and_timeouts.md) separates admission, attempt and total clocks.
4. **Compose and verify:** [Call Patterns](03_call_patterns.md) runs the complete caller and changed-condition tests.

**Stop here if** one process owns the quota and only idempotent operations are retried. Continue to
distributed admission or idempotency when those conditions stop holding.

### For Production Deployment

1. Review Parts 1-3
2. Read [Kubernetes](04_kubernetes.md) — multi-pod concerns
3. Read [Production Architecture](05_production_architecture.md) — complete stack

### For Advanced Systems

1. Review Parts 1-5
2. Read [Advanced Patterns](06_advanced_patterns.md) — circuit breakers, bulkheads, hedging, priority queues
3. Read [Idempotency Keys](11_idempotency.md) — preserve operation identity and effects across caller and process recovery

### For Distributed / Multi-Pod Systems

1. Review Part 4 (Kubernetes) and Part 5 (Production Architecture)
2. Read [Distributed Admission Control](09_distributed_admission_control.md) — Redis as the shared authority for leased provider attempts, retaining local bounds and separate durable quota ownership
3. For LLM workloads, also read [LLM Token Economics](10_llm_token_economics.md) — Reserve → Retry → Reconcile

> **Note**: Parts 1–3 describe the **transport layer** (sockets, timeouts, in-process semaphores). Part 9 describes the **admission layer** (cluster-wide Redis-backed checks). Real systems need both. If you only read parts 1–3, you'll have process-local bounds that need a conserved fleet allocation or shared authority when the quota is fleet-wide.

---

## Architecture at a Glance

```
Internet
  ↓
API Gateway (flood protection)
  ↓
Kubernetes Service
  ↓
ASGI Server (admission control)
  ↓
FastAPI
  ├─ Load shedding (local)
  ├─ User rate limiter (Redis)
  ├─ Queue timeout
  ├─ Circuit breaker (scoped to the dependency failure domain)
  ├─ Global vendor limiter (Redis)
  ├─ Local rate limiter
  ├─ Semaphore
  └─ Call timeout
  ↓
HTTP Client (with timeouts)
  ↓
Vendor API
```

---

## Dependencies

Use the versions for the selected executable path:

- [Part 3 setup](03_call_patterns.md#run-one-operation-before-studying-the-policy) installs the HTTPX/FastAPI test baseline; optional process-local start spacing is implemented explicitly.
- [Container requirements](examples/requirements.txt) pin hashes for the local app image.
- [Advanced requirements](examples/advanced_requirements.txt) pin the Redis, Psycopg, HTTP and test libraries for Parts 6–11; [Compose](examples/advanced_compose.yaml) supplies isolated Redis/PostgreSQL.

The advanced path's database owns durable usage and idempotency state. Redis owns short-lived admission leases and rate history; its existence alone does not establish durable business accounting.

---

**Start with [Part 1: Core Concepts →](01_core_concepts.md)**
