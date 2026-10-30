# Part 7: Own a finite SSE request until cleanup completes

> **Role:** implementation tutorial. Prerequisites: [the bounded JSON caller](03_call_patterns.md), async iteration and the ownership rules in [Part 6](06_advanced_patterns.md).
>
> **Outcome:** run a local authenticated SSE proxy that admits before headers, bounds idle and total time, handles disconnects, and releases every resource. The fake provider needs no external API key or billable account.

A JSON caller owns a permit until it has read and closed the response. Streaming extends
that lifetime: receiving response headers only means the body can begin. A text generation
may emit a word every second for a minute. Releasing capacity after `client.send()` would
let hundreds of open bodies hide behind a concurrency limit of four.

Our running request returns three text deltas followed by a semantic completion event.
The browser receives SSE: UTF-8 text frames separated by a blank line. An event name
identifies its meaning; a `data:` field contains its payload. This tutorial uses one
explicit provider dialect, then translates it to client-facing events.

## 1. Trace the owner before writing the endpoint

The response object owns the whole ASGI lifetime, including the period before any body
iterator has started. This matters because calling `aclose()` on a never-started async
generator does not execute a `finally` block inside that generator.

```mermaid
sequenceDiagram
  participant B as Browser
  participant O as FiniteSSE owner
  participant G as Capacity gate
  participant P as Provider response
  B->>O: GET /events with verified identity
  O->>G: acquire 1 unit; at most 1 second
  G-->>O: lease owned
  O->>P: open + validate status + first useful frame
  P-->>O: text 0
  O-->>B: 200 headers, then SSE delta
  P-->>O: text 1
  O-->>B: SSE delta
  B->>O: disconnect
  O->>O: cancel and join owned work
  O->>P: await response close
  O->>G: release 1 unit
```

The ordering is the guarantee: provider close precedes permit release. No admission
rejection can become a 503 after 200 headers have been sent. The fixture therefore
acquires capacity, opens the actual provider request, validates status/content type and
obtains a useful first frame **before** sending headers. It does not run a preliminary
`/models` request: that tests another operation and cannot reserve success for the real one.

[FiniteSSE and StreamOwner](examples/advanced_streaming.py) are complete implementations.
`StreamOwner` retains exactly one byte iterator, its partial-frame buffer, the HTTPX
response and semantic outcome. HTTPX manual streaming requires explicit `aclose()`;
its [async streaming guide](https://www.python-httpx.org/async/) documents that ownership
obligation. An async context manager is preferable when the whole lifetime fits one scope.

## 2. Give each wait the right clock

| Bound | Fixture default | What it protects |
|---|---:|---|
| Admission | 1 second | Time spent waiting to own local capacity |
| First response/frame | 5 seconds | Open, status validation and first useful data |
| Idle frame | 30 seconds | Time to obtain the next complete provider frame |
| Total operation | 90 seconds | Admission, startup, reads and downstream sends together |
| Downstream send | 5 seconds | One client write which stops making progress |
| HTTPX transport | 5 seconds in local app | Connection/pool/read/write operations underneath |

The total clock starts when the response owner runs. A provider emitting every 20 seconds
keeps satisfying a 30-second idle bound but still stops at 90 seconds. A finite product
response needs both. A truly indefinite subscription is a different contract: use a
renewable session policy, explicit shutdown/reconnect semantics and a separate capacity
pool; do not silently remove the total bound from a finite generation endpoint.

Cancellation deadlines trigger cleanup; they cannot guarantee that a remote provider
stops processing at that instant. Cleanup can also take bounded transport time. At 90
seconds the application stops ordinary work, closes the response, joins owned tasks and
releases admission. Measure cleanup latency separately from the user-visible deadline.

The admission timeout encloses acquisition itself. This is incorrect in principle:
first await the semaphore forever, then start a timer for the stream. It leaves the
waiting population unbounded in time even though the provider portion is timed.

## 3. Frame meaning is different from socket progress

The fake provider emits this wire representation:

```text
data: {"text":"0"}

data: {"text":"1"}

data: {"text":"2"}

data: [DONE]

```

`StreamOwner.next()` checks `[DONE]` before decoding JSON. A delta must be a JSON object
with a string `text`. The client receives `event: delta`, `event: done`, or a sanitized
`event: error` with a stable code. EOF without the terminal marker means the completion
is unknown, even if ten thousand chunks arrived. Chunk count is a progress metric, not
proof that the model completed or that final usage was delivered.

This parser intentionally accepts only one LF-delimited `data:` line per provider frame.
It rejects multiline SSE fields, CRLF variants and other event types; it is a complete
fixture for this stated dialect, not a general SSE implementation. A production adapter
must implement the selected provider's documented field/event contract. The browser-side
SSE protocol also supports IDs, comments and multiline data; see the
[HTML event-stream specification](https://html.spec.whatwg.org/multipage/server-sent-events.html#parsing-an-event-stream).
Do not forward raw provider bytes while claiming to parse arbitrary SSE correctly.

The retained parser buffer is limited to 4096 bytes, total provider bytes to 262144, and compressed bodies are rejected. A total byte limit also bounds a provider which emits small frames extremely quickly.
The transport may hand the application one larger chunk before it is rejected; this is
an application bound on retained parsing data, not a claim about kernel/proxy buffer
sizes. HTTPX, your proxy and the provider need compatible transport limits. Payloads
larger than the fixture contract must fail, not accumulate until memory exhaustion.

## 4. Backpressure starts with reading less

The baseline has no producer queue. It reads a frame, awaits the browser send, then
reads the next frame. If the browser slows down, the owner stops reading upstream;
transport flow control propagates the pressure. A five-second send bound prevents a
client which never reads from retaining a permit indefinitely.

Sometimes transformation or merging needs a queue. Bound both the queue cardinality
and individual frame size. Four 4 KiB frames give at most about 16 KiB of queued payload
per request, in addition to decoder and transport buffers. An unbounded `Queue()` or
`put_nowait()` loop defeats backpressure. [Part 8's bounded merge](08_streaming_advanced.md)
uses one owned producer per source, source-labelled terminal/error events, and cancel/join
on consumer exit. Producer failure must reach the consumer; a dead producer and an
empty queue must not leave a consumer waiting forever.

Proxy buffering can hide early chunks even when application code is correct. The fixture
sets `Cache-Control: no-cache` and `X-Accel-Buffering: no`; the latter is only a hint to
compatible proxy configuration. Test through your actual ingress with a slow reader.
Heartbeats, if the chosen protocol allows them, keep middleboxes aware of an idle stream;
they must not reset a product's hard total deadline or stand in for semantic progress.

## 5. Atomic weighted capacity

A small stream may reserve one unit while an expensive transformation reserves three.
Acquiring three semaphore tokens one at a time is unsafe: timeout after the second
acquisition leaks two tokens unless partial ownership is correctly unwound, and two
large requests can each hold partial capacity forever.

[WeightedGate](examples/advanced_streaming.py) instead waits under an `asyncio.Condition`
until `used + weight <= capacity`, then increments `used` once. Cancellation before that
increment owns zero units; after it, cleanup subtracts the whole weight. Invalid weights
(zero, negative or larger than capacity) fail immediately. Waiting callers are counted
and capped separately from active units.

For capacity three with two units occupied, a request for two units waits; it does not
hold the remaining unit. If its timeout expires, usage remains two. The regression test
asserts exactly this state and zero waiters. This simple gate is not FIFO: small requests
can overtake large ones. Choose reserved classes or a fair dispatcher if starvation is
unacceptable. A weight estimates local resources; it is not a financial token reservation.

## 6. Run the whole proxy and client

From `examples/`, use the environment from Part 6 or create it:

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r advanced_requirements.txt
.venv/bin/python -m pytest -q advanced_test_streaming.py
.venv/bin/uvicorn advanced_stream_app:app --host 127.0.0.1 --port 8087
```

In another terminal:

```bash
curl -N -H 'Authorization: Bearer local-demo' http://127.0.0.1:8087/events
curl -H 'Authorization: Bearer local-demo' http://127.0.0.1:8087/metrics
curl -i http://127.0.0.1:8087/events
```

Expect three `delta` events, one `done`, then EOF. The metrics response reports zero active
units and a `done` outcome. The unauthenticated request returns 401 before any upstream
work. `local-demo` is a fixed laboratory credential. Replace it with the application's
verified identity dependency, resolve tenant/tier on the server, and keep a provider key
only in the provider adapter. Never accept arbitrary upstream URLs from the caller.

The app uses lifespan to own one HTTPX client. The custom response owns every individual
stream and watches ASGI disconnect messages concurrently with its work. On disconnect
it cancels and joins the work task; on server cancellation it also joins the disconnect
watcher. Failure before headers returns 503. Failure afterward emits a sanitized error
frame if the client is still writable, because HTTP status cannot change mid-response.

The tests use real async byte streams through HTTPX MockTransport, not buffered
`Response(content=...)` objects. They assert response closure and zero owned units for
success, bad status, empty first frame, idle timeout, total timeout despite continuous
progress, client disconnect and stalled downstream send. The 20/30/90-second acceptance
case is scaled to 20/30/90 milliseconds for deterministic local execution.

## 7. Operate and upgrade the lifetime contract

Watch admission wait/rejections, active units, time to first useful event, idle gaps,
stream duration, downstream send duration, bytes per stream, semantic outcome and cleanup
latency. Keep outcome labels bounded; use request IDs in sampled traces rather than
high-cardinality metric labels. Log a stable error classification, not raw provider
exceptions which can contain URLs, prompts or credentials.

Before production:

- Test admission saturation before headers and a provider error immediately after headers.
- Exercise browser disconnect, server shutdown and cancellation while opening the provider.
  Every path must close the response and return active/waiting gauges to baseline.
- Configure reverse-proxy buffering, read/write idle limits and maximum response duration
  against the same product contract; verify through the ingress, not only localhost.
- Keep streams separate from short JSON calls when their lifetimes would exhaust the
  shared pool. Test pool limits with the chosen HTTP/1.1 or HTTP/2 transport.
- Pin framework/transport versions. Run lifecycle tests when upgrading Starlette/HTTPX;
  middleware and disconnect behavior can change without changing your endpoint signature.

If clients receive all deltas at once, inspect buffering before changing provider concurrency.
If a successful provider generation is followed by a broken client connection, keep those
outcomes separate: provider completion does not prove client receipt. If final usage is
missing, retain the financial obligation as [Part 10](10_llm_token_economics.md) explains.

## Recap

The owner spans admission through awaited cleanup. Admit and validate before headers;
keep independent idle, total and send bounds; retain one parser iterator; distinguish
semantic completion from EOF; propagate backpressure and join every task on disconnect.

## Check yourself

<details><summary>The provider emits every 20 seconds. Idle is 30 seconds; total is 90. When does work stop?</summary>
At the 90-second total deadline. Progress prevents an idle timeout but does not extend
the product budget. Cleanup closes the provider, joins producers if present and releases
the owned permit; cleanup latency is measured separately.
</details>

<details><summary>Why is a generator's finally block insufficient for a response opened before the generator starts?</summary>
An unstarted generator has not entered its try/finally scope. Its close need not run that
cleanup. The surrounding response owner must explicitly close resources regardless of
whether iteration started.
</details>

## Try it

Change the fake provider to emit a delta and then EOF. Predict the client event and metric
outcome, then verify the response closes and active units return to zero. Next stall the
client after the first delta while the provider keeps producing. Keep the send bound
smaller than total and assert cleanup completes without an accumulating queue.

Scaffold: modify `DemoBytes.__aiter__` to yield one delta, then `return` before the
terminal marker; finish `assert stats == {_____: 1}` and `assert gate.used == _____`.

Hint: transport EOF cannot prove semantic done, and ownership is independent of outcome.

<details><summary>Reasoned solution</summary>
Expect `{'failed': 1}` in the response owner's metrics, an in-band
`stream_interrupted` event after the already-sent 200, and `gate.used == 0`. The underlying
provider owner never observed done. Stalling downstream triggers the send bound, closes
the upstream and returns capacity without continuing to buffer new frames.
</details>

**Next:** [Coordinate multiple streams](08_streaming_advanced.md). **Back:** [learning map](README.md).
