# Part 1: Orchestration Patterns

> **Who this is for**: Backend engineers choosing how an orchestrator observes completion and
> recovers when a worker goes silent.

How the orchestrator dispatches work to workers and tracks the lifecycle of each task. This is the most architecturally significant decision — it determines your failure semantics, scalability ceiling, and operational complexity.

> **Key insight**: Successful callbacks close the happy path while an independently owned deadline
> closes the silence path; neither signal can substitute for the other.

---

## Pattern 1: Fire-and-Forget with Callback

The simplest async pattern. The orchestrator dispatches the task and immediately forgets about it. The worker is fully responsible for reporting the outcome.

### How It Works

```
Client                    Orchestrator                    Worker
  │                           │                             │
  │── POST /jobs ──►          │                             │
  │                           │── create job record ──►     │
  │                           │   (status: pending)         │
  │◄── 202 {job_id} ──        │                             │
  │                           │── enqueue task ──►          │
  │                           │   (fire and forget)         │
  │                           │                             │── pick up task
  │                           │                             │── do work (minutes)
  │                           │                             │
  │                           │                    ◄── callback: success ──│
  │                           │── update job record         │
  │                           │   (status: succeeded)       │
  │                           │── store result              │
```

### On Failure

```
Worker crashes without calling back
  │
  ├── No one knows. The job stays "pending" forever.
  │
  └── Mitigation: Stale-job sweeper (cron)
      - SELECT jobs WHERE status = 'pending' AND created_at < NOW() - interval '30 min'
      - Mark as 'failed' or re-enqueue for retry
```

### Characteristics

| Aspect | Detail |
|--------|--------|
| **Orchestrator complexity** | Minimal — dispatch and record, nothing else |
| **Failure detection** | Passive — relies on a timeout sweeper |
| **Failure detection latency** | High — depends on sweeper interval (minutes) |
| **Worker coupling** | Low — worker just needs to call a callback URL/endpoint |
| **Scalability** | Excellent — orchestrator does almost no work per task |
| **When to use** | Bulk processing, background jobs, anything where you can tolerate delayed failure detection |

### Implementation Notes

- The callback can be an HTTP POST to an internal endpoint, an SQS message, or a database write.
- The sweeper should use `updated_at` (not `created_at`) to avoid false positives on long-running tasks. Alternatively, have the worker update `updated_at` periodically as a soft heartbeat.
- Idempotent callbacks are critical — if the worker retries its callback and the orchestrator has already processed it, the second call should be a no-op.

---

## Pattern 2: Heartbeat Monitoring

The orchestrator actively monitors worker health. Workers must send periodic heartbeat signals; if a heartbeat is missed, the orchestrator declares the task failed.

### How It Works

```
Client                    Orchestrator                    Worker
  │                           │                             │
  │── POST /jobs ──►          │                             │
  │◄── 202 {job_id} ──        │                             │
  │                           │── dispatch task ──►         │
  │                           │   (with heartbeat config)   │
  │                           │                             │── start work
  │                           │                             │
  │                           │           ◄── heartbeat ────│  (every N seconds)
  │                           │── update last_heartbeat     │
  │                           │                             │
  │                           │           ◄── heartbeat ────│
  │                           │── update last_heartbeat     │
  │                           │                             │
  │                           │           ◄── heartbeat ────│
  │                           │── update last_heartbeat     │
  │                           │                             │── work complete
  │                           │     ◄── callback: success ──│
  │                           │── update status: succeeded  │
```

### On Failure (Ungraceful)

```
Worker crashes mid-task, no callback sent
  │
  ├── Heartbeats stop arriving
  │
  └── Orchestrator's heartbeat monitor detects:
      last_heartbeat + heartbeat_timeout < NOW()
      │
      ├── Mark task as 'failed' (reason: heartbeat timeout)
      ├── Optionally re-enqueue for retry
      └── Optionally alert / trigger cleanup
```

### On Failure (Graceful)

```
Worker catches an exception during processing
  │
  ├── Worker sends callback: failure (with error details)
  │
  └── Orchestrator immediately marks task as 'failed'
      │
      ├── No need to wait for heartbeat timeout
      └── Faster failure detection than ungraceful path
```

### Heartbeat Design Decisions

| Decision | Options |
|----------|---------|
| **Heartbeat interval** | 10–60 seconds is typical. Too frequent = noisy. Too infrequent = slow failure detection. |
| **Timeout multiplier** | Usually 2–3x the heartbeat interval. If heartbeat is every 30s, timeout at 60–90s. |
| **Where to store heartbeats** | Redis (fast, TTL-based), DynamoDB (conditional writes), PostgreSQL (simple UPDATE) |
| **Who checks?** | Dedicated monitor process (cron/scheduler) or the orchestrator on every client poll |
| **Heartbeat payload** | Minimal: `{job_id, timestamp}`. Optionally: progress percentage, current step, resource usage. |

### Characteristics

| Aspect | Detail |
|--------|--------|
| **Orchestrator complexity** | Medium — needs a heartbeat monitor process/loop |
| **Failure detection** | Active — bounded by heartbeat_timeout |
| **Failure detection latency** | Low — seconds to minutes depending on config |
| **Worker coupling** | Medium — worker must implement heartbeat sending |
| **Scalability** | Good — but heartbeat storage/checking can become a bottleneck at very high scale |
| **When to use** | Production systems with SLAs, when you need fast failure detection |

### Implementation Skeleton (Worker Side)

```python
import logging
import threading
import requests

logger = logging.getLogger(__name__)


class LeaseLost(RuntimeError):
    pass


def post_checked(url: str, **kwargs) -> requests.Response:
    response = requests.post(url, timeout=(2, 5), **kwargs)
    response.raise_for_status()
    return response


def heartbeat_loop(
    stop_event: threading.Event,
    lease_lost: threading.Event,
    job_id: str,
    orchestrator_url: str,
    interval: int = 30,
    max_consecutive_failures: int = 2,
):
    """Stop the worker before its 90-second lease can expire silently."""
    failures = 0
    while not stop_event.is_set():
        try:
            post_checked(f"{orchestrator_url}/jobs/{job_id}/heartbeat")
            failures = 0
        except requests.RequestException:
            failures += 1
            logger.exception("heartbeat_failed", extra={"job_id": job_id, "failures": failures})
            if failures >= max_consecutive_failures:
                lease_lost.set()
                return
        stop_event.wait(interval)


def run_task(job_id: str, orchestrator_url: str):
    # Per-task stop event — never share one Event across tasks, or finishing
    # one task would silently kill the heartbeats of others in the same process.
    stop_event = threading.Event()
    lease_lost = threading.Event()
    hb = threading.Thread(
        target=heartbeat_loop,
        args=(stop_event, lease_lost, job_id, orchestrator_url, 30),
        daemon=True,
    )
    hb.start()

    try:
        # Long work must check this event between bounded chunks and abort its
        # external effects when set. Otherwise a replacement worker can overlap.
        result = do_actual_work(cancel_event=lease_lost)
        if lease_lost.is_set():
            raise LeaseLost("heartbeat lease can no longer be renewed")
        terminal = ("complete", {"result": result})
    except Exception:
        terminal = ("fail", {"error": "worker_failed"})
    finally:
        stop_event.set()
        hb.join(timeout=6)

    # Persist first. A separate dispatcher retries this idempotently after a
    # crash; the orchestrator deduplicates by the stable callback ID.
    callback_id = durable_terminal_outbox.insert(job_id, *terminal)
    try:
        post_checked(
            f"{orchestrator_url}/jobs/{job_id}/{terminal[0]}",
            json=terminal[1],
            headers={"Idempotency-Key": callback_id},
        )
        durable_terminal_outbox.mark_delivered(callback_id)
    except requests.RequestException:
        logger.exception("terminal_callback_pending", extra={"callback_id": callback_id})
        # Leave the outbox row pending for the retry dispatcher.
```

---

## Pattern 3: Task Token (WaitForTaskToken)

The orchestrator generates a unique token and passes it to the worker alongside the task. The orchestrator **suspends** — it does no work and holds no resources. The worker uses the token to resume the orchestrator when done.

This is the native pattern in AWS Step Functions, Azure Durable Functions, and Temporal.

### How It Works

```
Client                    Orchestrator                    Worker
  │                           │                             │
  │── POST /jobs ──►          │                             │
  │◄── 202 {job_id} ──        │                             │
  │                           │── generate task_token       │
  │                           │── dispatch task ──►         │
  │                           │   {task, task_token}        │
  │                           │                             │
  │                           │── SUSPEND ─┐                │── start work
  │                           │   (zero    │                │
  │                           │    cost    │                │── work (minutes/hours)
  │                           │    while   │                │
  │                           │    waiting)│                │── work complete
  │                           │            │                │
  │                           │◄───────────┘  ◄── send_task_success(token, result)
  │                           │── RESUME                    │
  │                           │── store result              │
  │                           │── update status: succeeded  │
```

### On Failure (Ungraceful — Worker Crashes)

```
Worker crashes, never calls send_task_success or send_task_failure
  │
  ├── Orchestrator has a HeartbeatSeconds timeout configured
  │   (renewed by SendTaskHeartbeat; TimeoutSeconds separately caps total duration)
  │
  └── After HeartbeatSeconds expires:
      │
      ├── Orchestrator transitions to error/catch path
      ├── Cleanup logic runs (stop worker session, release resources)
      └── Task marked as failed (reason: heartbeat timeout)
```

For `HeartbeatSeconds=60` and `TimeoutSeconds=180`, start at t=0 and heartbeat at t=40.
Silence after that allows heartbeat expiry at t=100. Continued heartbeats never extend execution
past t=180. These are independent clocks: renewal proves a signal arrived, not that every external
effect finished. [AWS SendTaskHeartbeat](https://docs.aws.amazon.com/step-functions/latest/apireference/API_SendTaskHeartbeat.html), checked 2026-10-30.

### On Failure (Graceful — Worker Catches Error)

```
Worker catches exception
  │
  └── send_task_failure(token, error_details)
      │
      └── Orchestrator resumes on error path
          ├── Cleanup logic
          └── Optional retry logic
```

### Characteristics

| Aspect | Detail |
|--------|--------|
| **Orchestrator complexity** | Low (if using managed service like Step Functions) or High (if building your own) |
| **Failure detection** | Active — HeartbeatSeconds timeout |
| **Failure detection latency** | Configurable — set HeartbeatSeconds to desired ceiling |
| **Worker coupling** | Medium — worker must know about the token and how to call back |
| **Scalability** | Excellent — orchestrator holds no compute resources while waiting |
| **Cost** | Standard Step Functions is transition-billed and supports callback tokens; Express is duration/memory billed and does not support `.waitForTaskToken` |
| **When to use** | Cloud-native architectures, workflows that need guaranteed completion or cleanup |

### Key Distinction: Token Heartbeat vs Worker Heartbeat

| | Token Heartbeat | Worker Heartbeat (Pattern 2) |
|---|---|---|
| **Who sends it?** | Worker sends `SendTaskHeartbeat(token)` to extend the timeout | Worker sends a ping to the orchestrator |
| **What happens on miss?** | Orchestrator auto-transitions to failure state | Orchestrator's monitor must detect and act |
| **Purpose** | "I'm still alive, don't time me out" | "I'm still alive, for your records" |
| **Built-in to orchestrator?** | Yes (Step Functions, Temporal) | No — you build the monitor |

---

## Pattern 4: Orchestrator-Polls-Worker

The orchestrator periodically checks the worker (or a shared store) for task status. The worker writes its status somewhere; the orchestrator reads it.

### How It Works

```
Client                    Orchestrator                    Worker
  │                           │                             │
  │── POST /jobs ──►          │                             │
  │◄── 202 {job_id} ──        │                             │
  │                           │── dispatch task ──►         │
  │                           │                             │── start work
  │                           │                             │── write status: running
  │                           │                             │
  │                           │── poll status ──►           │
  │                           │◄── running ──               │
  │                           │                             │
  │                           │── poll status ──►           │
  │                           │◄── running (70%) ──         │── still working
  │                           │                             │
  │                           │── poll status ──►           │
  │                           │◄── succeeded ──             │── done, result written
  │                           │── fetch result              │
  │                           │── update job record         │
```

### Characteristics

| Aspect | Detail |
|--------|--------|
| **Orchestrator complexity** | Medium — needs a polling loop per active task (or batched polling) |
| **Failure detection** | Passive — detects "stuck" tasks via staleness of status updates |
| **Worker coupling** | Low — worker writes to a shared store, doesn't need to know about the orchestrator |
| **Scalability** | Moderate — polling frequency × active tasks = load on the status store |
| **When to use** | When workers can't make outbound calls (VPC-isolated, air-gapped environments) |

### Anti-Pattern Warning

Polling from the orchestrator is often a sign that you should use callbacks instead. The main valid use case is when the worker **cannot** make outbound network calls (e.g., it's in a restricted VPC with no egress). In most other cases, callbacks (Pattern 1 or 3) are simpler and more efficient.

---

## Pattern 5: Event-Driven (Pub/Sub)

Workers emit events to a message bus. The orchestrator subscribes to relevant topics and reacts to state changes. This is the most decoupled pattern.

### How It Works

```
Client                    Orchestrator                    Worker
  │                           │                             │
  │── POST /jobs ──►          │                             │
  │◄── 202 {job_id} ──        │                             │
  │                           │── publish: task.created ──► │
  │                           │── subscribe: task.* events  │
  │                           │                             │── consume: task.created
  │                           │                             │── start work
  │                           │                             │
  │                           │              ◄── event: task.progress {70%} ──│
  │                           │── update progress           │
  │                           │                             │
  │                           │              ◄── event: task.completed {result} ──│
  │                           │── store result              │
  │                           │── update status             │
```

### Characteristics

| Aspect | Detail |
|--------|--------|
| **Orchestrator complexity** | Medium — event subscription and handling |
| **Failure detection** | Passive — needs a separate timeout mechanism |
| **Worker coupling** | Very low — worker just publishes events, doesn't know who listens |
| **Scalability** | Excellent — pub/sub systems are built for high throughput |
| **When to use** | Microservice architectures, when multiple systems need to react to task lifecycle |

---

## Comparison Matrix

| Pattern | Failure Detection | Latency to Detect Failure | Worker Complexity | Orchestrator Complexity | Best For |
|---------|-------------------|---------------------------|-------------------|------------------------|----------|
| **Fire-and-Forget + Callback** | Passive (sweeper) | Minutes | Low | Low | Bulk processing, tolerance for delayed detection |
| **Heartbeat Monitoring** | Active | Seconds | Medium | Medium | SLA-bound production systems |
| **Task Token** | Active (built-in timeout) | Configurable | Medium | Low (managed) / High (DIY) | Cloud-native, Step Functions, Temporal |
| **Orchestrator-Polls-Worker** | Passive (staleness) | Depends on poll interval | Low | Medium | VPC-isolated workers |
| **Event-Driven** | Passive (needs timeout) | Minutes | Low | Medium | Microservices, multi-consumer |

---

## Combining Patterns

In production, you rarely use one pattern in isolation:

- **Fire-and-Forget + Heartbeat**: Worker calls back on completion, but also sends heartbeats so the orchestrator can detect crashes quickly.
- **Task Token + Heartbeat**: Step Functions' `HeartbeatSeconds` is exactly this — a task token pattern where the worker must periodically call `SendTaskHeartbeat` to extend the timeout.
- **Event-Driven + Sweeper**: Workers publish events, but a background sweeper catches tasks that never emitted a completion event.

The general principle: **callbacks for the happy path, timeouts for the sad path**.

## Decide when the callback path fails

**The callback endpoint is unreachable while worker generation 1 continues. Does heartbeat expiry
prove it died, and may its delayed callback replace generation 2's result?**

<details><summary>Reasoned answer</summary>

No. Expiry proves only that renewal was not observed. The orchestrator can issue generation 2,
but every completion and local effect must check current ownership. Generation 1's delayed callback
is rejected; generation 2's accepted result remains the durable truth. For a remote side effect,
the receiver must enforce an idempotency or fencing contract too.

</details>
