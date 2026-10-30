# Dramatiq + FastAPI: One Durable Submission Path

> **Who this is for**: FastAPI engineers who have chosen Dramatiq and need submission, status, retries, tests and deployment to agree on one durable job.

Read [Dramatiq's runtime](overview.md), the [minimal durable job](../../foundations/03_minimal_durable_task.md), and the [outbox boundary](../../execution/01_queue_and_worker_architectures.md#3-a-broker-needs-an-outbox-at-the-database-boundary) first. The runnable baseline uses Python 3.11+, PostgreSQL 17, Redis 7.4, Dramatiq 2.2.1 and FastAPI 0.162.0; exact Python dependencies live with the example.

## Run the canonical service first

A document request creates work that must survive an API restart. The API, publisher and worker run in separate processes. They share code, while PostgreSQL owns the obligation and result. The complete [example directory](../../examples/durable_job/main.py) contains every adapter and fixture; later changes extend this same actor rather than replacing it with partial alternatives.

From the repository root:

```bash
cd background_work/examples/durable_job
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-brokers.txt
docker compose -p background-job-lab --profile broker up -d --wait postgres redis
export DATABASE_URL=postgresql://lab:lab@127.0.0.1:56432/jobs
export REDIS_URL=redis://127.0.0.1:56379/0
.venv/bin/python main.py init
.venv/bin/python -m dramatiq dramatiq_tasks --queues parse.dramatiq --processes 1 --threads 2
```

Keep that worker running. In a second terminal in the same directory, export the same two URLs and run:

```bash
.venv/bin/python publisher.py dramatiq
```

In a third terminal, again with both URLs:

```bash
.venv/bin/python broker_smoke.py
.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8086
```

The bounded smoke test prints `one durable job, words=3, status=SUCCEEDED`. It submits the same operation twice and observes one database job with its deterministic result. While the API is running, send:

```bash
curl -i http://127.0.0.1:8086/document-parses \
  -H 'Content-Type: application/json' -H 'Idempotency-Key: document-42' \
  -d '{"text":"one two three"}'
```

The response is `202` with a `Location`. GET that exact location until it reports `SUCCEEDED` and `words=3`. Repeating the POST returns the same ID; changing the text under `document-42` returns `409`.

This is a local, fixed-tenant lab with loopback ports and disposable credentials. The parser counts words in at most 10,000 characters of text and commits a small result in PostgreSQL. A real document service adds authenticated tenant authorization, immutable object storage, bounded parsing and provider-specific effect protection. Those additions do not change who owns the job.

## Follow the obligation across three commits

The request does not publish a broker message. It commits input, job and outbox together; only afterward may the API return `202`. Watch the two crash windows in this sequence.

```mermaid
sequenceDiagram
    participant C as Client
    participant A as FastAPI
    participant D as PostgreSQL
    participant P as Publisher
    participant B as Redis broker
    participant W as Dramatiq worker
    C->>A: POST document-42
    A->>D: Commit input, PENDING job, outbox
    A-->>C: 202 and job URL
    P->>D: Lock unpublished outbox row
    P->>B: Publish job ID
    Note over P,B: Crash here repeats delivery
    P->>D: Commit published_at
    B->>W: Deliver job ID
    W->>D: Claim token A and lease
    W->>D: Commit token-bound result
    Note over W,B: Crash here causes harmless redelivery
    W-->>B: Acknowledge
```

If the publisher dies after Redis accepts the message, its transaction rolls back the publication mark. The next publisher sends again. The actor must therefore tolerate duplicate deliveries even when the publisher works correctly. If the worker dies after committing completion, the repeated delivery cannot claim a terminal job.

There are three distinct IDs: the request key identifies one caller operation, the job ID identifies the durable obligation, and a broker message ID identifies one delivery. Never use a new message ID as a new provider operation key when retrying the same effect.

The source files have one responsibility each:

| File | Responsibility |
|---|---|
| [main.py](../../examples/durable_job/main.py) | Validate bounded input; submit and read job status |
| [schema.sql](../../examples/durable_job/schema.sql) | Jobs, immutable inputs, results, outbox and constraints |
| [store.py](../../examples/durable_job/store.py) | Transaction-owning submission, claim, completion, retry and recovery |
| [dramatiq_tasks.py](../../examples/durable_job/dramatiq_tasks.py) | Initialize broker before declaring the actor; invoke the unchanged job protocol |
| [publisher.py](../../examples/durable_job/publisher.py) | Confirm outbox publication and reconcile owed work |
| [test_lifecycle.py](../../examples/durable_job/test_lifecycle.py) | HTTP replay, competing claims, crash recovery and budgets |
| [test_dramatiq.py](../../examples/durable_job/test_dramatiq.py) | Real actor with a stub transport; publisher crash window |

## Configure the broker before importing actors

The canonical actor module creates `RedisBroker`, calls `dramatiq.set_broker`, and only then evaluates `@dramatiq.actor`. Import order matters because decorators bind to the configured broker. If no broker was set, Dramatiq may construct a default at localhost; the API can publish to one broker while workers consume another.

For a larger application, move initialization to `broker.py` and import it before every actor declaration. Do not construct database sessions or live connection pools before forking worker processes; create them per process or operation. This example opens and closes one database connection per transaction.

Result storage is optional. `Results` middleware is not needed here because the domain database answers status. If you add `store_results=True`, first install/register `Results` and its backend as shown in the [runtime reference](overview.md#results-are-opt-in-per-actor-and-not-a-status-store). A bare job ID cannot reconstruct a result key: the original message ID and message metadata belong to the transport result API, whose retention is independent of business retention.

Redis numbered databases are namespaces, not security isolation, and Redis Cluster supports only database 0. Key prefixes avoid collisions; they do not grant isolation or prove a particular client supports cluster topology. Use separate instances when queues and disposable results need different eviction/durability policies, and scoped ACL users when service access must differ. Never flush a shared instance to clean up a test.

## The database, not broker retries, bounds execution

The actor is intentionally small:

```python
@dramatiq.actor(queue_name="parse.dramatiq", max_retries=0, time_limit=30_000)
def parse_job(job_id: str):
    store.execute(job_id)
```

This excerpt comes from the complete configured module above. `max_retries=0` means Dramatiq does not own the application retry schedule. `store.execute` recovers expired jobs, claims this ID if eligible, executes the bounded parser, and completes only with the current token. The DB supplies `attempt`, `max_attempts`, `next_attempt_at` and `retry_deadline`. A transient failure moves the same job to `PENDING` and creates a fresh outbox hint in one transaction. Exhaustion moves it to `FAILED`; it cannot remain pending after the broker stops retrying.

`claim` requires all of: a pending row, eligibility time reached, attempts remaining and an unexpired deadline. Completion requires `RUNNING`, the same attempt token and a live lease. Checking only the token after the lease expired would let an old worker write before a replacement happened to claim.

The lab's 30-second actor bound is below its 90-second lease; parsing 10,000 characters should finish much sooner. A runtime time limit is not a universal hard interrupt for blocking native code. Expensive parsing or remote calls need a real operation deadline, supervised heartbeats and process isolation where cancellation cannot stop the operation. Follow [leases and fencing](../../reliability/02_leases_heartbeats_and_fencing.md) before extending the lab's workload.

If a worker is killed, no exception handler runs. `publisher.repair_missing_hints` reclaims expired leases, checks budgets and records another hint. It also replaces old published hints for still-pending work, so a broker loss does not erase the database obligation. This can produce extra deliveries; ownership makes them harmless. Scan limits and indexes bound the repair load.

For a payment or remote report, completion and provider success are separate transactions. Use the same business operation key across redelivery, record the request hash, query/reconcile ambiguous outcomes, then publish local completion under the current token. A lease token alone cannot undo a provider effect. The [external-effects lesson](../../reliability/03_idempotency_and_external_effects.md) owns that protocol.

## Carry correlation without replacing ownership

A `ContextVar` in FastAPI does not cross a broker. Persist the request/trace ID in the outbox transaction, then put it in message options when the publisher sends. This is an extension excerpt for an application that adds a `request_id` column to `job_outbox`:

```python
parse_job.send_with_options(args=(str(row.job_id),), request_id=row.request_id)
```

Do not write `options={"request_id": ...}`: that becomes a nested option rather than the field middleware reads. Never derive tenant authority from an arbitrary message option; the worker reloads the job and applies authorization policy from durable state.

Middleware can bind and clear correlation around the existing actor:

```python
from contextvars import ContextVar
import dramatiq

request_id_var = ContextVar("request_id", default="unknown")

class Correlation(dramatiq.Middleware):
    def before_process_message(self, broker, message):
        request_id_var.set(message.options.get("request_id", "unknown"))

    def after_process_message(self, broker, message, *, result=None, exception=None):
        request_id_var.set("unknown")

    def after_skip_message(self, broker, message):
        request_id_var.set("unknown")
```

Register that middleware before worker startup. Log the request/job IDs and a bounded error class around `store.execute`; do not replace its claim/complete logic with a logging-only actor. Deliver the same job twice and assert both correlation and one authoritative result. Avoid logging whole arguments, tokens, document text or arbitrary exception strings.

## Async libraries still need the same claim protocol

Dramatiq's opt-in `AsyncIO` middleware provides one event-loop thread per worker process. Actor worker threads wait on coroutine completion, so actor concurrency remains tied to the configured thread count. The worker loop is separate from FastAPI's loop.

Changing to `async def` must preserve submission, claim, retry and completion conditions. For this synchronous small adapter, there is no reason to change it. When integrating asynchronous providers, implement an async counterpart of the complete store protocol and supervise the provider operation and heartbeat together. An unconditional `await db.update_job(..., status="completed")` would discard the fence.

If a coroutine actor needs to call this synchronous adapter during migration, `await asyncio.to_thread(store.execute, job_id)` retains its database rules and moves blocking I/O off the loop. Cancellation of the await does not stop the thread; keep the operation bounded and never interpret cancellation as proof that no effect occurred. `asyncio.run` per synchronous actor is another integration choice, but creates a new loop each message; do not share a loop-bound client across those invocations.

## Verify rows and failure boundaries, not only a `202`

Stop the background publisher and worker so test jobs are controlled by their fixtures. In the initialized example directory:

```bash
.venv/bin/python -m pytest -q test_lifecycle.py test_dramatiq.py
```

The six checks cover same-key replay and input mismatch, two competing claims, stale completion, attempt/deadline exhaustion, real child-process death, duplicate delivery to the actual actor, and publication rollback. Several assertions belong to one test; the count is tests, not guarantees.

The stub test changes the actual actor's broker, declares that actor on the stub, starts a worker and uses bounded joins. It restores the actor afterward. Replacing only the global broker after decorators ran would leave actors bound to their old broker. `StubBroker.join` defaults to failing fast on a failed message in Dramatiq 2.x; a test deliberately exercising retries must use `fail_fast=False`, a short explicit backoff and a bounded timeout, then inspect the final business state.

The live `broker_smoke.py` check proves real Redis publication and a separately running worker. It does not certify broker quorum, failover, security, backup/restore or remote-provider idempotency. The local lifecycle tests deliberately manipulate lease timestamps to create a controlled crash boundary rather than sleeping for 90 seconds.

A response-only endpoint test passes while the publisher is dead. Inspect the outbox row and, in the integrated path, wait for the job result under a deadline. Stop the publisher, submit a request, observe `PENDING` and unpublished age grow, restart it, and confirm eventual success with the same ID.

## Deploy every owner, including the publisher

The complete [Compose file](../../examples/durable_job/compose.yaml) and [Dockerfile](../../examples/durable_job/Dockerfile) include PostgreSQL, Redis, schema initialization, API, publisher and worker. Stop host-run copies before using the container version:

```bash
docker compose -p background-job-lab --profile broker --profile dramatiq up --build -d
```

Initialization must complete before the three application processes start. The API binds to loopback on the host. All processes receive the same database URL; publisher and worker also receive the broker URL. Run the HTTP request above and inspect all three application logs. A healthy API and worker with no publisher cannot discharge accepted obligations.

The image is shared; commands differ. Scale the worker independently only after measuring database and provider ceilings. Separate queues and processes provide isolation for urgent and expensive work; listing a queue first does not create strict priority. Queue names must match the actor's `queue_name`: this lab consumes `parse.dramatiq` explicitly.

This is a local deployment fixture, not a production secret distribution or HA template. Before production, replace disposable credentials, use restricted network/service identities, choose broker durability and eviction policy, rehearse restores and apply resource limits. Images and dependencies need a tested patch-update policy rather than an indefinite lab pin.

## Operate the obligation through shutdown and recovery

Measure the oldest unpublished *outbox* timestamp, not a column absent from the job schema:

```sql
SELECT coalesce(max(now() - created_at), interval '0') AS oldest_unpublished
FROM job_outbox
WHERE published_at IS NULL;
```

Old irrelevant hints for terminal jobs can be archived by a bounded retention job. For active progress, join to nonterminal jobs. Track both unpublished age and oldest ready job age: publication can be healthy while consumers are missing, and broker depth can be zero while publication is broken. Also track expired leases, attempts per completed job, terminal failures and submission-to-result latency.

Dramatiq stops consuming and waits for in-flight actors during graceful shutdown. `ShutdownNotifications` injects its `Shutdown` exception only into actors with `notify_shutdown=True`. That exception derives from `BaseException`; broad `except Exception` does not catch it. It cannot reliably interrupt every blocking native call.

The lab chooses bounded work and `stop_grace_period: 40s`, above its 30-second actor bound. If a process is killed anyway, the 90-second lease and reconciler recover it. A longer operation needs an explicit drain or checkpoint policy. If an actor safely checkpoints on `Shutdown`, release through the current token and set the intended next eligible time explicitly; ordinary retry jitter is not an immediate requeue. Do not claim a provider call was cancelled merely because the actor released its lease.

Worker process liveness is separate from business progress. Prometheus middleware requires the `dramatiq[prometheus]` extra and exposes its own listener; secure its network access. A heartbeat thread can prove a process is alive during idle periods, but a healthy thread does not prove consumers make progress. Pair infrastructure checks with oldest-job age and a bounded synthetic job. A file touched only when jobs finish makes an idle worker look dead.

A permanent failure should create durable terminal evidence and an owned alert/recovery queue. Dramatiq's retry-exhausted callback or middleware hook can notify operators, but it must not be the sole record of application failure. The DB retry budget already records `FAILED`; an alerting outage must not leave the status ambiguous. Redrive is an authorized new operational decision with a stable business identity and a durable delivery intent, as shown in the [runtime DLQ section](overview.md#dead-letter-queues-dlq).

Production readiness:

- [ ] Repeated and conflicting request keys produce one job or `409`.
- [ ] Publisher crash after send repeats safely; missing publisher raises an age alert.
- [ ] Worker loss produces a new token; stale completion changes zero rows.
- [ ] Retry age/attempt exhaustion becomes a terminal DB state.
- [ ] API, publisher and workers use scoped identities, bounded payloads and redacted logs.
- [ ] Graceful drain, forced kill, DB/broker recovery and restore are rehearsed separately.
- [ ] Queues, job rows, input/result retention and DLQ replay horizons agree with the product contract.

## Recap and check yourself

- A committed job plus outbox makes the promise survive the API process.
- Publication acknowledgement and its DB mark are separate; a crash can repeat delivery.
- The worker's current lease token governs local mutation; the stable job key governs business replay.
- Retry limits and reconciliation belong to the same durable state used by the status endpoint.

**The API returns `202`, worker health is green, and unpublished age rises. Where do you look first?**

<details><summary>Answer</summary>

The publisher and its broker connectivity. Accepted rows have not crossed the handoff; adding workers cannot consume messages that were never published. Restart the publisher and observe age fall and the original job finish.

</details>

**Worker A succeeds at the provider after B has reclaimed its lease. May A write local completion?**

<details><summary>Answer</summary>

No. A's token is stale. Preserve or query provider evidence under the stable operation key, then let the current owner reconcile it. Overwriting with A would bypass the ownership race even if its result was real.

</details>

**Try it:** add a test that calls `store.retry(job, delay_seconds=0)` three times, claiming between calls. Fill the last assertion: `assert store.get_job(job_id)['status'] == ...`. Then deliver the ID again and check the attempt count.

<details><summary>Hint and worked solution</summary>

The DB default allows three attempts. After the third failure, assert `FAILED`; `store.claim(job_id)` returns `None` and attempt remains 3. The message has no authority to reopen a terminal row. Manual redrive requires a separate reviewed business policy, not a reset hidden in transport retry.

</details>

Sources: [Dramatiq guide](https://dramatiq.io/guide.html), [middleware and broker APIs](https://dramatiq.io/reference.html), and [Dramatiq 2.0 release notes](https://github.com/Bogdanp/dramatiq/releases/tag/v2.0.0), checked 2026-10-30. These define runtime behavior; the example's database protocol supplies application durability.
