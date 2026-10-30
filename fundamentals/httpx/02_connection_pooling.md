# HTTPX Connection Pooling

> **Who this is for**: Async Python engineers sizing reusable HTTP connections separately from
> application concurrency.

> **Core idea**: Pool limits control how many sockets exist, not how many coroutines run.

> **Key insight**: Pool limits bound sockets, while a separate application limiter bounds admitted
> coroutines.

---

## 1. Pool Limits Configuration

```python
limits = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=20
)

client = httpx.AsyncClient(limits=limits)
```

---

## 2. `max_connections`

**What it is**: Maximum number of TCP connections that may exist at the same time.

```python
httpx.Limits(max_connections=100)
```

### What This Controls

- Total sockets across all hosts
- Includes **active + idle** sockets
- A hard ceiling on connections; under HTTP/1.1 this usually also caps in-flight requests

HTTP/2 multiplexes request streams over a connection. Therefore `max_connections` is not an
application-wide concurrency limiter when HTTP/2 is negotiated; bound application work separately.

### When Limit Is Reached

If you have 100 active connections and request #101 arrives:

```python
await client.get(...)  # waits in pool queue
```

The request **waits** (does not fail immediately) until:
1. A connection becomes free
2. `pool` timeout expires

### What This Does NOT Control

- Number of async tasks
- Application-level concurrency
- Memory usage from pending requests

---

## 3. `max_keepalive_connections`

**What it is**: Maximum number of **idle** sockets kept open for reuse.

```python
httpx.Limits(max_keepalive_connections=20)
```

### What This Controls

- How many sockets stay open after requests complete
- Upper bound on "warm" connections

### When This Matters

After a burst of traffic:

```
Peak: 100 active connections
After burst: 20 kept idle, 80 closed
```

This prevents:
- Wasting server-side resources during low traffic
- Accumulating stale connections
- File descriptor exhaustion

### Relationship to `max_connections`

```
max_keepalive_connections ≤ max_connections
```

- `max_connections`: ceiling during load
- `max_keepalive_connections`: ceiling on idle reusable connections retained in the pool

---

## 4. Pool Behavior Summary

| Situation | Pool behavior |
|-----------|---------------|
| Request arrives, idle socket exists | Reuse socket immediately |
| Request arrives, no idle socket, under limit | Create new socket |
| Request arrives, at `max_connections` | Wait in pool queue |
| Request completes, under keepalive limit | Return socket to pool |
| Request completes, at keepalive limit | Close socket |

---

## 5. Pool Queue and `pool` Timeout

When all connections are busy:

```python
# All 100 connections in use
await client.get(...)  # enters pool queue
```

The `pool` timeout controls how long this wait is allowed:

```python
timeout = httpx.Timeout(30.0, pool=5.0)
```

### What Happens

| Outcome | Result |
|---------|--------|
| Socket becomes free within 5s | Request proceeds |
| 5s passes, no socket free | `httpx.PoolTimeout` raised |

### Common Mistake

```python
# Correct: supply a default, then override every phase that differs
timeout = httpx.Timeout(30.0, connect=5.0, pool=5.0)
```

Always set `pool` timeout explicitly in production.

---

## 6. Per-Host Limits

By default, HTTPX does **not** limit connections per host.

```python
# All 100 connections could go to one host
limits = httpx.Limits(max_connections=100)
```

### Implication

If you call multiple APIs:

```python
await asyncio.gather(
    client.get("https://api1.example.com/..."),  # could use 50
    client.get("https://api2.example.com/..."),  # could use 50
)
```

One slow API could starve connections for another.

### Solution

For multi-API scenarios, consider:
1. **Separate clients per API** — each gets its own independent pool.
2. **Application-level semaphores per API** — a shared client is fine, but gate calls to each API through its own `asyncio.Semaphore` so one slow API cannot starve the rest of the pool.

```python
import asyncio
import httpx

# One shared client, but a per-host semaphore caps concurrent in-flight calls per API.
client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
)

api1_sem = asyncio.Semaphore(20)  # cap on api1.example.com
api2_sem = asyncio.Semaphore(20)  # cap on api2.example.com


async def call_api1(path: str):
    async with api1_sem:
        return await client.get(f"https://api1.example.com{path}")


async def call_api2(path: str):
    async with api2_sem:
        return await client.get(f"https://api2.example.com{path}")
```

The semaphore does **not** replace the HTTPX pool — it sits in front of it and ensures no single API's slowness can consume all 100 pool slots. Set each semaphore to your target per-API concurrency (informed by the API's rate limit; see `safe_and_scalable_api_calls/01_core_concepts.md` for arrival-rate, measured duration and admission budgeting).

---

## 7. Connection Reuse Mechanics

### Keep-Alive Protocol

HTTP/1.1 connections are persistent by default when message framing permits reuse and neither side requests closure. `Connection: keep-alive` is not required; `Connection: close` ends persistence. See [RFC 9112 §9.3](https://httpwg.org/specs/rfc9112.html#persistence).

```
Client → Server: GET /data HTTP/1.1
                 Connection: keep-alive

Server → Client: HTTP/1.1 200 OK
                 Connection: keep-alive
```

The explicit keep-alive headers above are unnecessary for ordinary HTTP/1.1 persistence. Reuse still requires an available compatible connection and fully consumed or closed response.

### When Connections Close

| Reason | Who closes |
|--------|-----------|
| `Connection: close` header | Either side |
| Server idle timeout | Server |
| Server max requests reached | Server |
| Pool limit reached | Client |
| Client closed | Client |

### Detection

When server closes connection:
- HTTPX detects on next use
- Automatically creates new connection
- Transparent to your code

---

## 8. Production Configuration

### Small Service (Low Traffic)

```python
limits = httpx.Limits(
    max_connections=20,
    max_keepalive_connections=10
)
```

### Medium Service

```python
limits = httpx.Limits(
    max_connections=50,
    max_keepalive_connections=20
)
```

### High-Traffic Service

```python
limits = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=30
)
```

### Considerations

| Factor | Effect on limits |
|--------|------------------|
| Target latency distribution | Higher variance → more connections |
| Upstream API capacity | Match their limits |
| Pod resources | Memory for buffers, file descriptors |
| Concurrent users | Scale with expected concurrency |

---

## 9. Monitoring Pool Health

### Key Metrics

Track these in production:

| Metric | What it indicates |
|--------|-------------------|
| Pool wait time | Contention for connections |
| Active connections | Current concurrency |
| Idle connections | Warm connection availability |
| Connection creation rate | Handshake frequency |
| Pool timeout errors | Undersized pool |

### Warning Signs

- High pool wait times → pool too small
- Many new connections → poor reuse or aggressive closing
- Pool timeout errors → increase `max_connections` or reduce concurrency

---

## 10. Common Mistakes

### ❌ Pool Too Small

```python
limits = httpx.Limits(max_connections=5)
# With 50 concurrent requests → massive pool queue
```

**Fix**: Size pool for expected concurrency.

### ❌ Pool Too Large

```python
limits = httpx.Limits(max_connections=1000)
# Allows up to 1000 connections under demand; it does not eagerly open them.
```

**Fix**: Match pool size to what downstream can handle.

### ❌ Keepalive Too High

```python
limits = httpx.Limits(
    max_connections=100,
    max_keepalive_connections=100
)
# Retains at most 100 idle connections, each subject to keepalive_expiry (default 5s).
```

**Fix**: Choose idle count and `keepalive_expiry` separately from active capacity. An idle
count of 100 does not disable expiry; retaining all idle connections may be appropriate
for a steady workload. [HTTPX limits](https://www.python-httpx.org/advanced/resource-limits/)
(checked 2026-10-30).

### ❌ No Pool Timeout

```python
client = httpx.AsyncClient()  # pool timeout = 5.0 (default)
```

**Fix**: Explicitly configure all timeouts.

---

## Summary

Size the pool from evidence rather than a universal range: start below the upstream's connection
quota, run representative concurrency, and inspect pool-wait latency, open connections, upstream
rejections, and end-to-end tail latency. Increase the pool only while pool wait dominates and the
upstream still has capacity; reduce it when open connections rise without improving tail latency.

| Setting | Purpose | Validation target |
|---------|---------|-------------------|
| `max_connections` | Peak concurrent connections | Pool wait stays within budget without exceeding the upstream quota |
| `max_keepalive_connections` | Idle connections retained | Handshake rate falls without accumulating unnecessary idle sockets |
| `pool` timeout | Maximum connection wait | Overload fails within the caller's queue budget |

**Key principle**:

> Pool limits bound **connections**. They approximate request concurrency for HTTP/1.1, but HTTP/2
> stream concurrency still needs an application admission limit.

---

**Next**: [Timeouts](03_timeouts.md) — phase-based timeout configuration

## Check your understanding

Socket count, idle retention and waiting-task admission have separate owners. Tune them against measured upstream capacity.

**Prediction:** PoolTimeout rises when upstream latency doubles but sockets remain at their ceiling. Must the ceiling increase?

<details><summary>Answer</summary>
No. Requests retain slots longer. More concurrency can overload the dependency. Inspect admission, service latency and pool wait before changing capacity.
</details>

**Diagnosis:** Does max_keepalive_connections=100 keep idle sockets forever?

<details><summary>Answer</summary>
No. It caps retained idle count; keepalive_expiry independently limits idle lifetime, five seconds by default in this HTTPX baseline.
</details>
