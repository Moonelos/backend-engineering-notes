# HTTPX vs aiohttp

> **Who this is for**: Python engineers choosing an async HTTP client from concrete lifecycle,
> protocol, and streaming requirements.

For a conventional JSON API client, start with HTTPX. Choose aiohttp when a requirement specifically
needs its native WebSocket client or connector-level per-host controls. For example, an orders
service that needs sync and async callers fits HTTPX; a WebSocket-heavy gateway fits aiohttp.

Acceptance criteria should be workload-shaped: both candidates must close cleanly, meet the same
tail-latency budget, and return the same status/body under the same local test server.

> **Key insight**: Choose between clients by required protocol and lifecycle features plus verified
> current behavior, not brand-level preference.

---

## 1. Philosophy

The default comparison subset is **protocol support, lifecycle ownership, timeouts, and per-host
capacity**. The remaining feature rows are reference material after those gates produce no winner.

| Aspect | HTTPX | aiohttp |
|--------|-------|---------|
| Design | High-level, requests-like API | Low-level, flexible |
| Timeout shape | Phase inactivity; add a total clock | Total plus connection/read controls |
| Distinct features | Sync and async APIs; HTTP/2 extra | Native WebSocket client; per-host connector limits |

Run the same bounded local request through both clients. In one terminal:

```bash
python -m http.server 8765 --bind 127.0.0.1
```

In another terminal:

```python
import asyncio
import aiohttp
import httpx


async def main() -> None:
    url = "http://127.0.0.1:8765/"
    async with httpx.AsyncClient(timeout=5.0) as client:
        httpx_response = await client.get(url)

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5.0)) as session:
        async with session.get(url) as response:
            aiohttp_status = response.status
            aiohttp_body = await response.read()

    print(httpx_response.status_code, len(httpx_response.content) > 0)
    print(aiohttp_status, len(aiohttp_body) > 0)


asyncio.run(main())
# 200 True
# 200 True
```

Those two lines prove successful status/body reads. Context managers implement cleanup;
assert `client.is_closed` and `session.closed` after the blocks to observe closed owners.
Neither output alone verifies peer socket teardown. A connection-refused error
means the local server is not running; an unclosed-session warning means the aiohttp context owner
was removed.

---

## 2. Timeout Models

### HTTPX: Phase-Based

```python
timeout = httpx.Timeout(
    connect=5.0,    # DNS + TCP + TLS
    pool=5.0,       # wait for socket
    write=10.0,     # send request
    read=30.0       # receive response
)
```

**Characteristics**:
- Clear mapping to network lifecycle
- `read` timeout resets per chunk (safe for streaming)
- Explicit about what each timeout controls

### aiohttp: Total + Socket

```python
timeout = aiohttp.ClientTimeout(
    total=60,        # total request time
    connect=5,       # pool wait plus connection establishment
    sock_read=30,    # socket read
    sock_connect=5   # new peer connection only
)
```

**Characteristics**:
- `total` is a global ceiling
- Use total for finite jobs; configure long-lived subscriptions deliberately
- In current aiohttp, `sock_read` is the maximum interval between incoming data portions, so it
  behaves as an inactivity bound and resets as data arrives

### Practical Difference

```python
# HTTPX: This works fine with streaming
timeout = httpx.Timeout(30.0, read=30.0)
# read=30s means "30s between chunks"

# aiohttp: This can break streaming
timeout = aiohttp.ClientTimeout(total=60)
# total=60s means "entire request must complete in 60s"
```

---

## 3. Connection Pooling

### HTTPX: Explicit Pool Behavior

```python
limits = httpx.Limits(
    max_connections=100,        # total sockets
    max_keepalive_connections=20  # idle sockets
)
```

**Characteristics**:
- Pool queue exposed via `pool` timeout
- Clear separation: pool limits vs task limits
- Easy to understand contention behavior

### aiohttp: Connector-Based

```python
connector = aiohttp.TCPConnector(
    limit=100,           # total connections
    limit_per_host=0,    # per-host limit (0 = unlimited)
    ttl_dns_cache=300    # DNS caching built-in
)
session = aiohttp.ClientSession(connector=connector)
```

**Characteristics**:
- More implicit behavior
- Built-in DNS caching (HTTPX uses OS resolver)
- Easier to confuse connector limits with application concurrency
- `limit_per_host` provides per-host control HTTPX lacks

---

## 4. HTTP/2 Support

### HTTPX

```python
client = httpx.AsyncClient(http2=True)
```

- First-class HTTP/2 support
- Easy to enable
- Works transparently

### aiohttp

- No HTTP/2 support (HTTP/1.1 only, as of aiohttp 3.x in 2026)
- Long-requested but repeatedly deferred upstream
- You'd need a separate library (e.g. `httpx`, `h2`) for HTTP/2

**Winner**: HTTPX for HTTP/2 use cases.

---

## 5. Streaming and Low-Level Control

### aiohttp Excels At

| Use case | Why aiohttp |
|----------|-------------|
| Long-lived connections | Fine-grained socket control |
| WebSockets | Native, mature support |
| Proxies/gateways | Lower-level access |
| Custom protocols | More extensibility |

### HTTPX Suffices For

| Use case | Why HTTPX |
|----------|-----------|
| API clients | Clean, simple API |
| Standard HTTP | Explicit phase timeouts and connection limits |
| Existing HTTPX integration | Compatible transports, mocks and sync/async API surface |

---

## 6. Error Model

### HTTPX: Lifecycle-Specific

```python
httpx.ConnectTimeout    # DNS + TCP + TLS failed
httpx.PoolTimeout       # no socket available
httpx.ReadTimeout       # response stalled
httpx.WriteTimeout      # request stalled
```

Each exception maps to a specific phase.

### aiohttp: Connection, socket-read and total timeouts

```python
aiohttp.ConnectionTimeoutError  # connect or sock_connect budget
aiohttp.SocketTimeoutError      # sock_read inactivity
aiohttp.ClientConnectorError    # connection establishment error
asyncio.TimeoutError            # also catches total timeout
```

`connect` includes waiting for a pooled connection; `sock_connect` covers a new peer
connection. The concrete subclasses preserve that distinction.
[aiohttp reference](https://docs.aiohttp.org/en/stable/client_reference.html), checked 2026-10-30.

---

## 7. API Design

### HTTPX

```python
async with httpx.AsyncClient() as client:
    response = await client.get(url)
    data = response.json()
```

- Familiar to `requests` users
- Sync and async APIs mirror each other
- Response methods are synchronous

### aiohttp

```python
async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.json()
```

- Double context manager pattern
- Response methods are async
- More explicit about resource lifecycle

---

## 8. Feature Comparison

| Feature | HTTPX | aiohttp |
|---------|-------|---------|
| **Sync API** | ✅ | ❌ |
| **HTTP/2** | ✅ Native | ❌ None |
| **WebSockets** | ❌ | ✅ Native |
| DNS caching | ❌ (OS) | ✅ Built-in |
| **Per-host limits** | ❌ | ✅ |
| **Phase-based timeouts** | ✅ | ⚠️ Partial |
| requests-like API | ✅ | ⚠️ |
| Connection hooks | ✅ | ✅ |
| Proxy support | ✅ | ✅ |
| Streaming | ✅ | ✅ |

---

## 9. When to Choose What

### Choose HTTPX If

- Building an API client
- Want the same library interface for sync and async HTTP clients
- Need HTTP/2
- Have existing HTTPX transports or tests to preserve
- Standard REST/JSON APIs

### Choose aiohttp If

- Building a proxy or gateway
- Need deep socket control
- Handling long-lived connections
- WebSocket-heavy workloads
- Need per-host connection limits
- Accept higher complexity for more power

---

## 10. Migration Considerations

### From aiohttp to HTTPX

```python
# aiohttp
async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.json()

# HTTPX equivalent
async with httpx.AsyncClient() as client:
    response = await client.get(url)
    data = response.json()
```

**Watch out for**:
- `response.json()` is sync in HTTPX
- Timeout model is different
- No built-in DNS caching

### From HTTPX to aiohttp

```python
# HTTPX
async with httpx.AsyncClient() as client:
    response = await client.get(url)
    data = response.json()

# aiohttp equivalent
async with aiohttp.ClientSession() as session:
    async with session.get(url) as response:
        data = await response.json()
```

**Watch out for**:
- Response must be consumed in context manager
- `await response.json()` (async)
- Configure `total` timeout carefully

---

## 11. Benchmark the same workload

Use identical concurrency, payloads, TLS, server and timeout budgets. Record throughput,
CPU, resident memory, p95/p99 latency, error rate and cleanup under cancellation. HTTP/2
can reduce connection count through multiplexing, but peer limits and bottlenecks still
matter. There is no universal memory/throughput ranking independent of that workload.

## HTTPX2 is a separate migration decision

HTTPX2 uses the `httpx2` import and `httpcore2` transport stack. Its default truststore uses
operating-system trust, whereas this course's HTTPX 0.28.1 uses certifi by default.
Do not only rename imports: test private CA acceptance, wrong-host rejection, environment
proxy/trust policy, custom transports, MockTransport fixtures and response cleanup. Keep
old and new dependency locks so a failed migration can roll back without ambiguous imports.
[HTTPX2 documentation](https://pydantic.dev/docs/httpx2/get-started/) (checked 2026-10-30).

Current Starlette supports HTTPX2 for TestClient and deprecates its old HTTPX backend.
Run endpoint and streaming-lifecycle tests on the intended lock before switching; in-process
transport behavior is not a real-socket streaming test. HTTPX2's optional WebSocket support
also means the older HTTPX/aiohttp feature table cannot be applied to it unchanged.

## Recap

- Choose protocol, timeout and per-host requirements before comparing ergonomics.
- Successful body reads and observed owner cleanup are different acceptance claims.
- Both clients need explicit finite-operation budgets and cancellation/resource checks.

## Check yourself

**You need WebSockets and ten connections per host. Does HTTP/2 alone choose the client?**

<details><summary>Reasoned answer</summary>

No. aiohttp directly supplies those features; HTTPX2 offers a separate option to investigate.
If HTTP/2 is also mandatory, validate one candidate against all requirements or use distinct
owned clients. The original HTTPX 0.28.1 feature list is not HTTPX2's feature list.

</details>

**A finite response emits a byte every second indefinitely. Does sock_read=5 finish the job?**

<details><summary>Reasoned answer</summary>

No. Repeated progress satisfies inactivity. A total deadline must end a finite operation,
while cleanup closes the response/session resources it owns.

</details>
