# Unix Signals and Graceful Shutdown

> **Who this is for**: Backend developers running Python services, workers, or
> schedulers under Docker, Kubernetes, systemd, or a process supervisor. The
> operational examples focus on Unix-like systems.

A signal is a small asynchronous notification sent to a process. For backend
services, the important problem is not merely "catch `SIGTERM`." It is turning a
shutdown request into a bounded sequence that stops new work, finishes or
abandons active work safely, releases resources, and exits before the platform
uses `SIGKILL`.

---

## 1. How Python Receives a Signal

The operating system delivers a signal to the process. CPython's low-level
handler records that it arrived; the Python handler runs later in the main thread
of the main interpreter, usually at the next bytecode instruction.

```text
OS / supervisor
      │
      │ SIGTERM
      ▼
CPython low-level handler
      │ sets a pending flag
      ▼
main Python thread reaches a safe point
      │
      ▼
registered Python callback runs
```

Consequences:

- only the main thread of the main interpreter can register a Python signal
  handler;
- the Python handler runs in that main thread even if another thread received
  the signal;
- a long-running C extension can delay the Python callback until it returns;
- signals are not an inter-thread messaging API—use `threading` primitives or a
  queue for that;
- handler code should be tiny because it interrupts the main program at an
  arbitrary safe point.

Signals and exceptions are different mechanisms, although Python's default
`SIGINT` handler raises `KeyboardInterrupt`.

---

## 2. Signals a Backend Service Encounters

Use symbolic names such as `signal.SIGTERM`; numeric values and availability
vary by platform.

| Signal | Normal meaning | Catch or ignore? | Typical source |
|--------|----------------|------------------|----------------|
| `SIGTERM` | Request orderly termination | Yes | Docker, Kubernetes, systemd, supervisors |
| `SIGINT` | Interactive interruption | Yes | `Ctrl+C` |
| `SIGHUP` | Terminal hangup; conventionally reload | Yes | Shell/session or supervisor |
| `SIGUSR1`, `SIGUSR2` | Application-defined event | Yes | Operations tooling |
| `SIGKILL` | Terminate immediately | No | Grace period expired or force-kill |
| `SIGSTOP` | Suspend immediately | No | Job control / operator |

Both `SIGKILL` and `SIGSTOP` cannot be caught, blocked, or ignored. `SIGKILL`
provides no cleanup opportunity.

Do not install handlers for synchronous faults such as `SIGSEGV` and expect
Python code to recover. The invalid native operation usually remains invalid
after the handler returns. Use crash reporting and `faulthandler` for diagnosis.

---

## 3. The Grace Period Is a Deadline, Not a Delay

Docker normally sends the image's configured stop signal (`SIGTERM` when none is
configured), waits for its stop timeout, and then sends `SIGKILL`.

Kubernetes starts a Pod's termination grace period, runs a `preStop` hook when
configured, asks the container runtime to stop the container, and force-kills
remaining processes after the deadline. The `preStop` hook consumes the same
grace-period budget; it does not add extra time.

At the same time, service routing is converging away from the terminating Pod.
EndpointSlices mark terminating endpoints not ready, but already-routed
connections and propagation races still exist. The application must tolerate a
short overlap.

```
termination requested
        │
        ├── endpoint begins leaving service routing
        ├── optional preStop work
        └── configured stop signal reaches container process
                         │
                         ▼
               application drains work
                         │
              exits before deadline?
                  │              │
                 yes             no
                  │              │
             clean exit       SIGKILL
```

Set `terminationGracePeriodSeconds` from measured shutdown behavior, including
worst-case request time, queue acknowledgement policy, pool teardown, log
flushing, and the `preStop` duration. A long grace period does not fix work that
has no cancellation or timeout path.

---

## 4. Run one process through drain, repeated signal and recovery

The complete Unix [shutdown_lab.py](examples/shutdown_lab.py) owns one local SQLite job, one async worker and its closers. [shutdown_probe.py](examples/shutdown_probe.py) creates subprocesses and sends real signals only to those children. From the repository root:

```bash
python3 fundamentals/core_concepts/runtime/examples/shutdown_probe.py
```

The worker first records durable `job-42` intent, prints `job started`, then performs a simulated operation. Its effect row and job completion share one transaction, so cancellation before that commit leaves a retryable obligation; a repeated run cannot create a second effect row.

The first case uses a 50ms job. SIGTERM stops intake and gives that job a 200ms drain interval; it commits, closes the client and closes the database exactly once. A second SIGTERM only records repeated intent. The handler never starts another cleanup routine.

The second case changes the operation to five seconds. Drain expires at 200ms, cancellation reaches the cooperative sleep and the durable job remains pending. A deliberately slow closer then reaches the **same** absolute 350ms deadline. Its timeout is recorded before the independently owned database is closed. Measured drain plus closer time is about 350ms, leaving margin before a 500ms outer grace budget. The fixture's local SQLite close is short; real database/pool close operations need their own measured behavior and outer supervisor.

The third case sends SIGKILL, which skips all application cleanup. The database still says pending with zero effects. A fresh child replays the same job ID and commits one effect. Its result is `PASS: repeated SIGTERM, bounded drain/closer, SIGKILL leaves pending, restart commits one effect`.

The final case injects a processing error without sending any signal. The owner waits on both the stop event and worker completion, so it observes the error immediately, closes the client and database, and exits unsuccessfully with the job still pending. Expected result: `PASS: work error exits without a signal, closes client/database, and preserves pending intent`. Waiting only on the stop event would leave a failed worker unobserved until a later signal.

## 5. Separate signal intent from the bounded shutdown owner

`loop.add_signal_handler()` schedules a callback on the Unix event loop. In the lab it sets one stop Event; the normal task owns intake stop, drain, cancellation and closers. Repeated signals do not create concurrent shutdown tasks. A synchronous service uses the same separation with a flag, finite poll/read timeouts, and `try/finally` around its processing loop so a processing exception also closes resources.

The time budget is shared: drain first, then closers spend only what remains until an absolute monotonic deadline. Giving every closer a fresh full grace interval would exceed the process deadline. `asyncio.wait` lets the owner inspect unfinished work without silently cancelling the accounting task; explicit cancellation then awaits cooperative cleanup.

This is a cooperative async fixture. Code that blocks the event loop or suppresses cancellation cannot be forcibly bounded by an asyncio timer; the platform's final process kill remains the hard boundary. Preserve durable ownership before that boundary. On Windows or inside a framework, expose the same shutdown function/event and let the platform/framework choose how to trigger it. `loop.add_signal_handler` is Unix-specific and belongs in the main thread.

---

## 6. FastAPI and Uvicorn Own the Signal Handler

Uvicorn already handles termination signals, stops taking new work, finalizes
connections and tasks within configured timeouts, and drives the ASGI lifespan
shutdown phase. Application cleanup belongs in FastAPI's lifespan:

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.http_client = httpx.AsyncClient(timeout=10.0)
    try:
        yield
    finally:
        await app.state.http_client.aclose()


app = FastAPI(lifespan=lifespan)
```

Do not replace Uvicorn's `SIGTERM` or `SIGINT` handler from application code.
Doing so can bypass its drain sequence. Configure the server's graceful-shutdown
timeout and the platform grace period so the outer platform deadline is longer
than Uvicorn's internal deadline plus cleanup margin.

The same ownership rule applies under Gunicorn or another supervisor: understand
which process receives signals, which process forwards them, and which lifecycle
hook your application owns.

---

## 7. PID 1 and Signal Forwarding in Containers

The container stop signal goes to the container's main process. Make the Python
server that process with the JSON/exec form:

```dockerfile
# ✅ Uvicorn becomes PID 1 and receives the stop signal directly.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Avoid a shell wrapper that does not `exec` its child:

```dockerfile
# ❌ A shell is PID 1 and may not forward the signal to Uvicorn.
CMD uvicorn app.main:app --host 0.0.0.0 --port 8000
```

If an entrypoint script is necessary, end it with `exec "$@"`. If the container
spawns child processes, use a real init process—such as Docker's `--init`
option—or ensure the supervisor forwards signals and reaps children.

PID 1 has special signal behavior on Linux, so relying on default termination
behavior is fragile. A framework or explicit application handler should own the
shutdown sequence.

---

## 8. Design Shutdown in Reverse Dependency Order

A practical service sequence is:

1. mark the instance unready or stop accepting new work;
2. stop polling queues and scheduling new jobs;
3. wait for active requests/jobs up to a deadline;
4. cancel, requeue, or abandon remaining work according to its durability
   contract;
5. flush telemetry and stop logging listener threads;
6. close HTTP clients, database pools, brokers, and other resources;
7. exit before the platform deadline.

Close dependants before their dependencies. A background telemetry exporter may
need its HTTP client, and a transaction may need its database pool, so shutting
the pool first can make later cleanup fail.

Make each cleanup step:

- **bounded**—it has a timeout;
- **idempotent**—a second call is harmless;
- **observable**—start, completion, timeout, and forced abandonment are visible;
- **failure-tolerant**—one failed closer does not skip every remaining closer.

`SIGKILL`, node loss, and power loss still bypass graceful shutdown. Durable
systems therefore also need acknowledgements, transactions, idempotency, leases,
or retryable work. Graceful shutdown improves normal deploys; it is not a
durability guarantee.

---

## 9. Test the Real Process Lifecycle

Unit-testing the callback is not enough. Start the service as a subprocess,
create in-flight work, send `SIGTERM`, and verify:

- readiness changes or new work stops;
- accepted work follows the documented finish/requeue policy;
- lifespan and resource cleanup run;
- the process exits inside the grace budget;
- final logs arrive;
- the next process can recover any unfinished durable work.

A second test should deliberately exceed the grace period and verify that the
system remains correct after force-kill. That is where missing acknowledgements
and non-idempotent jobs appear.

> **Key insight**: the signal is only the trigger. Graceful shutdown is a
> deadline-driven application protocol, and abrupt death must still be safe.

---

## 10. Official References

- [Python `signal` module](https://docs.python.org/3/library/signal.html)
- [Kubernetes Pod termination flow](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-termination-flow)
- [Docker container stop](https://docs.docker.com/reference/cli/docker/container/stop/)
- [Uvicorn graceful process shutdown](https://www.uvicorn.org/server-behavior/#graceful-process-shutdown)

---


## Recap

- Signal receipt requests shutdown; one normal control path owns cleanup.
- Drain and closers share the outer deadline, with measured margin.
- SIGKILL skips finally; durable job identity enables recovery.

## Check yourself

**Q: Grace is 30s, preStop 8s, drain 20s and closers 5s. Is that safe?**

<details><summary>Answer</summary>

No. 8+20+5=33 seconds exceeds the shared 30-second budget before routing and exit margin. Reduce stages or increase the measured outer grace.

</details>

**Q: Two SIGTERM signals arrive during drain. Should the second start another closer?**

<details><summary>Answer</summary>

No. Record the stop intent idempotently; retain one owner for cleanup. Framework-specific second-signal escalation is a separate policy.

</details>

## Try it

Allocate a 20-second outer budget with 4 seconds of preStop and 3 seconds of closers.

Hint: Reserve scheduling/routing margin before choosing drain time.

<details><summary>Worked solution</summary>

With a 2-second margin, drain may use at most 11 seconds. Test a job exceeding that limit and assert durable retry remains after forced exit.

</details>

**Next**: [Concurrency and Parallelism](../../concurrency/README.md)
