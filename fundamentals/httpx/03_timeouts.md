# HTTPX Timeouts

> **Who this is for**: Python engineers who use HTTPX and need phase limits plus an explicit end-to-end deadline for outbound calls.

> **Key insight**: HTTPX phase timers bound individual waits; an application deadline separately bounds the total operation across phases and retries.

---

## 1. Timeout Configuration

```python
timeout = httpx.Timeout(
    connect=5.0,
    pool=5.0,
    write=10.0,
    read=30.0
)

client = httpx.AsyncClient(timeout=timeout)
```

Each timeout applies to a **specific blocking operation**.

---

## 2. The Four Timeout Phases

```
Request lifecycle:

┌─────────────┐
│   pool      │ ← wait for free socket
├─────────────┤
│   connect   │ ← DNS + TCP + TLS
├─────────────┤
│   write     │ ← send request data
├─────────────┤
│   read      │ ← receive response data
└─────────────┘
```

---

## 3. `pool` Timeout

**What it covers**: Time waiting for a connection from the pool.

```python
httpx.Timeout(30.0, pool=5.0)
```

### When This Applies

Only when `max_connections` is reached:

```python
# All connections busy
await client.get(...)  # waits up to 5s for free socket
```

### What Triggers `PoolTimeout`

- All connections in use
- No connection becomes free within timeout
- Raises `httpx.PoolTimeout`

### What This Does NOT Cover

- Actual network operations
- Server response time

---

## 4. `connect` Timeout

**What it covers**: Establishing a new connection.

```python
httpx.Timeout(30.0, connect=5.0)
```

### Phases Included

| Phase | What happens |
|-------|--------------|
| DNS lookup | Resolve hostname to IP |
| TCP handshake | SYN → SYN-ACK → ACK |
| TLS handshake | Certificate exchange, encryption setup |

### What Triggers `ConnectTimeout`

- DNS server slow or unreachable
- Target server not responding to TCP
- TLS negotiation too slow
- Raises `httpx.ConnectTimeout`

### What This Does NOT Cover

- Sending HTTP request
- Receiving HTTP response
- Pool wait time

---

## 5. `write` Timeout

**What it covers**: Sending request data to the server.

```python
httpx.Timeout(30.0, write=10.0)
```

### What Gets Sent

| Data | When relevant |
|------|---------------|
| Request headers | Always |
| Request body | POST/PUT with JSON, files |
| Multipart data | File uploads |

### What Triggers `WriteTimeout`

- Network congestion
- Server not accepting data
- Large request body on slow connection
- Raises `httpx.WriteTimeout`

### Typical Values

| Use case | Suggested timeout |
|----------|-------------------|
| Simple API calls | 5-10s |
| File uploads | 30-60s |
| Large payloads | 30-120s |

---

## 6. `read` Timeout

**What it covers**: Receiving response data.

```python
httpx.Timeout(30.0, read=30.0)
```

### Critical Behavior

The `read` timeout **resets whenever data is received**.

```
Server sends chunk 1 → timer reset
  ... 5 seconds ...
Server sends chunk 2 → timer reset
  ... 5 seconds ...
Server sends chunk 3 → timer reset
```

This bounds read inactivity. A finite streaming job still needs a total deadline and
explicit response ownership.

### What Triggers `ReadTimeout`

- Server stops sending data for `read` seconds
- Connection stalls
- Raises `httpx.ReadTimeout`

### What This Does NOT Cover

- Total response time
Read timeout **does** cover waiting for response headers while the server computes.
A silent six-second computation can therefore fail with `read=5`, before the first byte.
It does not bound the sum of many successful reads.
[HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/) (checked 2026-10-30).

### Important Distinction

```python
# This is NOT "total request time = 30s"
# This is "max 30s between any two data chunks"
httpx.Timeout(30.0, read=30.0)
```

For total request time, use application-level timeout:

```python
async with asyncio.timeout(60):  # total time
    response = await client.get(...)  # read=30s between chunks
```

---

## 7. Default Timeout

If not specified:

```python
client = httpx.AsyncClient()  # default timeout = 5.0 for all
```

HTTPX default is 5 seconds for each phase.

**Always configure explicitly in production.**

---

## 8. Timeout Interactions

### Request Phases in Order

```
1. pool    → wait for socket         (if pool full)
2. connect → establish connection    (if new socket)
3. write   → send request
4. read    → receive response
```

### Phase timeouts do not add up to a total deadline

Pool and connect are conditional, while read and write limits bound periods of network inactivity
and may reset as chunks move. A streaming response can therefore run longer than the sum of the
four configured values. Put an explicit outer application deadline around the operation when the
caller needs a maximum wall-clock budget.

---

## 9. Error Handling

HTTPX raises specific exceptions:

```python
import httpx

try:
    response = await client.get("https://api.example.com")
except httpx.PoolTimeout:
    # Pool exhausted, no socket available
    ...
except httpx.ConnectTimeout:
    # Could not establish connection
    ...
except httpx.WriteTimeout:
    # Could not send request
    ...
except httpx.ReadTimeout:
    # Server stopped responding
    ...
except httpx.TimeoutException:
    # Base class for all timeout errors
    ...
```

### Exception Hierarchy

```
httpx.TimeoutException
├── httpx.ConnectTimeout
├── httpx.PoolTimeout
├── httpx.WriteTimeout
└── httpx.ReadTimeout
```

### Best Practice

```python
# Catch specific first
try:
    response = await client.get(url)
except httpx.ConnectTimeout:
    # Network issue, maybe retry
    ...
except httpx.ReadTimeout:
    # Server slow, maybe retry
    ...
except httpx.TimeoutException:
    # Catch-all for other timeouts
    ...
```

---

## 10. Production Configuration

### API Client (Fast APIs)

```python
timeout = httpx.Timeout(
    connect=5.0,
    pool=5.0,
    write=5.0,
    read=10.0
)
```

### LLM/AI Service (Slow APIs)

```python
timeout = httpx.Timeout(
    connect=5.0,
    pool=5.0,
    write=10.0,
    read=60.0  # LLMs can be slow
)
```

### File Upload Service

```python
timeout = httpx.Timeout(
    connect=5.0,
    pool=10.0,
    write=120.0,  # large uploads
    read=30.0
)
```

### Streaming Response

```python
timeout = httpx.Timeout(
    connect=5.0,
    pool=5.0,
    write=10.0,
    read=30.0  # per-chunk, not total
)
```

---

## 11. Common Mistakes

### ❌ Single Timeout for Everything

```python
# WRONG: same timeout for all phases
client = httpx.AsyncClient(timeout=30.0)
```

**Problem**: Connect should fail fast; read might need longer.

**Fix**:

```python
timeout = httpx.Timeout(30.0, connect=5.0, pool=5.0, write=10.0)
```

### ❌ No Timeout

```python
# WRONG: no timeout
client = httpx.AsyncClient(timeout=None)
```

**Problem**: Requests can hang forever.

**Fix**: Always set explicit timeouts.

### ❌ Expecting Total Time

```python
# WRONG mental model
timeout = httpx.Timeout(30.0, read=30.0)
# "My request will complete in 30s max" ← FALSE
```

**Reality**: `read=30s` means "30s between chunks".

**Fix**: Use `asyncio.timeout` for total time.

---

## 12. Timeout vs `asyncio.timeout`

| Mechanism | Scope | Effect |
|-----------|-------|--------|
| `httpx.Timeout` | Per-phase | Controls socket I/O directly |
| `asyncio.timeout` | Application | Cancels the coroutine |

### When to Use Each

```python
# Transport-level: HTTPX timeout
client = httpx.AsyncClient(
    timeout=httpx.Timeout(30.0, read=30.0)
)

# Application-level: asyncio.timeout
async with asyncio.timeout(60):
    response = await client.get(...)
```

Both are needed for production safety.

---

## Summary

| Timeout | Phase | Typical value | Raises |
|---------|-------|---------------|--------|
| `pool` | Wait for socket | 5s | `PoolTimeout` |
| `connect` | DNS + TCP + TLS | 5s | `ConnectTimeout` |
| `write` | Send request | 5-10s | `WriteTimeout` |
| `read` | Receive response | 10-60s | `ReadTimeout` |

**Key principle**:

> Phase-based timeouts give precise control over each network operation.
> `read` timeout resets on each chunk — it's not total time.

---

**Next**: [Advanced Features](04_advanced.md) — HTTP/2, streaming, retries

## Check your understanding

Phase limits bound individual waits. An outer monotonic deadline bounds the whole logical operation, including retries and backoff.

**Prediction:** One byte arrives every four seconds for a minute; read=5 and total=20. What stops it?

<details><summary>Answer</summary>
The outer deadline around twenty seconds. Successful individual reads can keep satisfying the five-second inactivity limit.
</details>

**Diagnosis:** The server computes silently for six seconds before sending headers, with read=5. Is that computation excluded?

<details><summary>Answer</summary>
No. Waiting for response headers is a network read wait and can raise ReadTimeout before any body arrives.
</details>
