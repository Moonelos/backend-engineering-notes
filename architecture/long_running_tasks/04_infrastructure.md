# Part 4: Infrastructure & Technology Choices

<!-- length-justification: This decision guide keeps the comparable queue, result, lease, and notification capabilities of each infrastructure option together so one requirements matrix can be evaluated without cross-file drift. -->

> **Who this is for**: Engineers who already understand durable jobs and need to choose the
> smallest infrastructure that preserves claims, results, and recovery.

Concrete tools and services that implement the patterns from Parts 1–3.

## Start with the crash you must survive

A worker claims job `abc` and dies halfway through. The minimum useful system must still retain the
pending job or an expired claim, let a replacement claim a newer generation, and expose one durable
result. If PostgreSQL is already authoritative and throughput is modest, begin with a database job
table and `FOR UPDATE SKIP LOCKED`; add a broker only when delivery throughput, routing, or isolation
justifies another system boundary.

The success signal is a crash test: terminate the first worker after claim, observe the lease expire,
then see one replacement finish job `abc` while the fenced old generation cannot commit. The product
sections below are decision branches, not prerequisites.

> **Key insight**: Infrastructure is adequate when its failure boundaries preserve the job protocol;
> a longer feature list does not make lost claims or ambiguous results durable.

---

## 1. Redis

The Swiss Army knife. Redis can serve as the queue, the result store, the heartbeat store, and the pub/sub notification layer — all at once.

### As a Task Queue (Redis Lists + BLMOVE)

`BLMOVE` only makes the list move atomic. It cannot simultaneously install a separately
written lease. Treat the list as a delivery hint over an authoritative job row, or use the
[Redis Streams pending-entry protocol](../../infrastructure/redis/02_pubsub_and_streams.md).
This bounded operation shows the timeout branch and the durable claim handoff:

```python
raw = await r.blmove("tasks", "processing", timeout=30, src="RIGHT", dest="LEFT")
if raw is not None:
    task = json.loads(raw)
    claim = await jobs.claim_if_pending_or_expired(task["job_id"])
    if claim is not None:
        await process_under_generation(claim)
    await r.lrem("processing", 1, raw)
```

The `jobs` adapter implements the [canonical fenced claim](../../background_work/foundations/03_minimal_durable_task.md).
A crash between `BLMOVE` and `claim` leaves an ownerless hint in `processing`; a reconciler scans
both pending/expired job rows and this list. It re-enqueues a hint only after consulting durable
state, and uses conditional updates for job ownership. Duplicate hints are harmless because a live
claim or completed job cannot be claimed again. A lost list entry cannot erase an accepted job.
If Redis alone must own the job, use an atomic Lua claim/expiry index and a tested recovery protocol;
a sequence of `HINCRBY` then `HSET` does not provide that guarantee.

### As a Result Store

```python
# Worker writes result
await r.set(f"result:{job_id}", json.dumps(result), ex=3600)  # 1h TTL

# Client reads result
raw = await r.get(f"result:{job_id}")
if raw:
    result = json.loads(raw)
```

### As a Heartbeat Store

```python
# Worker: update heartbeat with TTL
await r.set(f"heartbeat:{job_id}", datetime.now(UTC).isoformat(), ex=90)

# Monitor: check heartbeat
alive = await r.exists(f"heartbeat:{job_id}")
# Missing key → renewal was not observed; worker loss is suspected
```

TTL removes stale heartbeat data, but expiration does not transition or requeue a job. Maintain a
deadline index (for example a sorted set keyed by lease expiry) and run a monitor that scans due
leases, atomically advances the generation, and transitions/requeues the job. Do not depend on
keyspace notifications for correctness because they can be disabled or missed.

### As Pub/Sub Notification

```python
# Orchestrator: publish result when worker completes
await r.publish(f"job:{job_id}", json.dumps({"state": "succeeded", "result": result}))

# Client: subscribe and wait
pubsub = r.pubsub()
await pubsub.subscribe(f"job:{job_id}")
async for msg in pubsub.listen():
    if msg["type"] == "message":
        return json.loads(msg["data"])
```

### Redis Streams (Modern Alternative to Lists)

Redis Streams are purpose-built for task queues with consumer groups, acknowledgements, and replay.

```python
# Producer
await r.xadd("task_stream", {"job_id": "abc", "payload": json.dumps(data)})

# Consumer (in a consumer group)
results = await r.xreadgroup(
    groupname="workers",
    consumername="worker-1",
    streams={"task_stream": ">"},  # ">" = only new messages
    count=1,
    block=5000,  # Block for 5 seconds
)

# Acknowledge after processing
await r.xack("task_stream", "workers", message_id)
```

**Advantages over Lists:**
- Consumer groups (multiple workers, each gets different messages)
- Acknowledgement (unacked messages can be reclaimed by other workers)
- Message replay (re-read old messages)
- Built-in pending message tracking

### When to Use Redis

| Use Case | Redis Feature | Alternative |
|----------|---------------|-------------|
| Simple task queue | Lists + BLMOVE | SQS, RabbitMQ |
| Task queue with consumer groups | Streams | Kafka, RabbitMQ |
| Result cache | SET with TTL | S3, DynamoDB |
| Heartbeat tracking | SET with TTL | DynamoDB, PostgreSQL |
| Real-time notification | Pub/Sub | WebSocket, SSE |
| Job status tracking | Hashes | PostgreSQL, DynamoDB |

**Pick Redis when:** You need multiple of the above in one system, latency matters (sub-ms), and you're comfortable with at-most-once delivery (pub/sub) or at-least-once (Streams).

Redis persistence is a configurable durability/latency trade-off: RDB snapshots can lose the window
since the last snapshot, while AOF with `appendfsync everysec` can lose roughly the latest second;
`appendfsync always` narrows that local persistence window at a substantial write-latency cost.
Replication is asynchronous, so acknowledged writes can still be lost during failover. Choose a
broker whose documented loss window matches the job contract rather than treating “Redis” as one
durability mode.

**Avoid Redis when:** The accepted loss window is stricter than the selected Redis persistence and
failover design, you require an end-to-end exactly-once effect, or the measured throughput/retention
requirement calls for a partitioned event log such as Kafka.

---

## 2. RabbitMQ (AMQP)

A traditional message broker with rich routing, acknowledgements, and delivery guarantees.

### As a Task Queue

```python
import aio_pika
import os

connection = await aio_pika.connect_robust(os.environ["TASKS_RABBITMQ_URL"])
channel = await connection.channel()
await channel.set_qos(prefetch_count=1)  # One task at a time

queue = await channel.declare_queue("tasks", durable=True)

# Producer
await channel.default_exchange.publish(
    aio_pika.Message(body=json.dumps(task).encode(), delivery_mode=2),  # persistent
    routing_key="tasks",
)

# Consumer
async for message in queue:
    async with message.process():  # Auto-ack on success, nack on exception
        task = json.loads(message.body)
        await process(task)
```

Create a least-privilege RabbitMQ user with access only to the task vhost, then supply its URL
through `TASKS_RABBITMQ_URL`. The built-in `guest` account is a real credential pair, not an
example placeholder.

### Key Features

| Feature | Detail |
|---------|--------|
| **Acknowledgements** | Manual ack/nack — message stays in queue until explicitly acknowledged |
| **Dead Letter Exchange** | Routing requires a configured DLX and a qualifying rejection, expiry, length or queue-specific delivery-limit policy |
| **Priority Queues** | Messages can have priority levels |
| **TTL** | Per-message and per-queue TTL |
| **Routing** | Topic exchanges, fanout exchanges, header-based routing |

### When to Use RabbitMQ

**Pick RabbitMQ when:** You need complex routing (one message to multiple queues based on rules), message priority, or you're in an on-premise environment without cloud-managed queues.

Classic and quorum queues remove acknowledged messages; [RabbitMQ Streams](https://www.rabbitmq.com/docs/streams) retain records for replay. Choose the data structure before comparing replay requirements. Delivery limits and dead lettering are [queue-specific policies](https://www.rabbitmq.com/docs/quorum-queues), not a universal automatic retry count. Benchmark routing, retention and recovery on the chosen queue type; throughput rankings by product name hide those choices. Sources checked 2026-10-30.

---

## 3. Amazon SQS

Managed queue service: AWS operates the brokers; you still own permissions, quotas, visibility, retry/DLQ policy, retention and cost.

### Standard Queue (At-Least-Once, Best-Effort Ordering)

```python
import boto3

sqs = boto3.client("sqs")

# Producer
sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps(task))

# Consumer
response = sqs.receive_message(QueueUrl=QUEUE_URL, MaxNumberOfMessages=1, WaitTimeSeconds=20)
for msg in response.get("Messages", []):
    process(json.loads(msg["Body"]))
    sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=msg["ReceiptHandle"])
```

### FIFO Queue (Exactly-Once *Processing*, Ordered)

```python
sqs.send_message(
    QueueUrl=FIFO_QUEUE_URL,
    MessageBody=json.dumps(task),
    MessageGroupId=task["account_id"],  # Stable domain ID across producers
    MessageDeduplicationId=job_id,  # Prevent duplicate enqueue
)
```

FIFO queues guarantee:
- **Exactly-once processing** (AWS's term): `MessageDeduplicationId` drops duplicate *sends* within a 5-minute window. This is enqueue-side dedup, not exactly-once *delivery* — a consumer can still receive the same message more than once (crash after receive but before delete → visibility timeout expires → redelivery), so your handler must still be idempotent
- **Ordered delivery** within a message group
- **Ordered batches within each group** — one receive can contain several messages from the same group; further receives for that group wait for deletion or visibility expiry. Process that batch in group order rather than starting all its effects concurrently

Use a stable domain group such as `account:42`; Python’s randomized `hash()` can map the same
entity differently in separate producer processes. More groups permit parallel work only when the
business entities can safely execute independently. [SQS FIFO delivery](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/FIFO-queues-understanding-logic.html), checked 2026-10-30.

### Lambda Event Source Mapping (ESM)

```hcl
# Terraform
resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.tasks.arn
  function_name    = aws_lambda_function.worker.arn
  batch_size       = 1

  scaling_config {
    maximum_concurrency = 10  # Max 10 Lambda invocations
  }

  function_response_types = ["ReportBatchItemFailures"]
}

resource "aws_sqs_queue" "tasks_dlq" {
  name = "tasks-dlq"
}

resource "aws_sqs_queue" "tasks" {
  name = "tasks"
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.tasks_dlq.arn
    maxReceiveCount     = 5
  })
}
```

The ESM automatically:
- Polls the queue
- Invokes the Lambda with the message
- Deletes the message on successful Lambda return
- Sends to the configured DLQ after `maxReceiveCount`; without the source queue's redrive policy,
  repeated failures remain on the source queue. With batches, return only failed item identifiers
  through `ReportBatchItemFailures` so successful records are not retried.

### When to Use SQS

**Pick SQS when:** You're on AWS, want zero ops, need reliable delivery, and your throughput is moderate (default FIFO: 300 msg/s per API action, or 3,000/s with batching; high-throughput FIFO mode scales much higher; Standard queues are effectively unlimited).

**Avoid SQS when:** You need message replay, complex routing, or you're not on AWS.

---

## 4. Apache Kafka

Distributed event log. Messages are persisted to disk and can be replayed. Built for very high throughput.

### As a Task Queue

```python
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

async def publish(task):
    producer = AIOKafkaProducer(bootstrap_servers="kafka:9092")
    await producer.start()
    try:
        await producer.send_and_wait("tasks", json.dumps(task).encode())
    finally:
        await producer.stop()

async def consume():
    consumer = AIOKafkaConsumer(
        "tasks", bootstrap_servers="kafka:9092", group_id="workers",
        enable_auto_commit=False,
    )
    await consumer.start()
    try:
        async for message in consumer:
            await process(json.loads(message.value))
            await consumer.commit()  # sequential loop; effect committed first
    finally:
        await consumer.stop()
```

These functions require a provisioned topic, reachable broker and idempotent `process` adapter.
The [Kafka course](../../infrastructure/kafka/README.md) supplies the complete lab and the
partition/rebalance rules required before adding parallel handling.


### Key Differentiators

| Requirement | Kafka retained log | Destructive work queue |
|---|---|---|
| Replay after successful handling | Seek retained offsets, subject to retention | Store a separate history or select a stream product |
| Independent readers | Separate consumer groups maintain progress | Route copies to separate queues when needed |
| Ordered effects | Partition order plus serial/fenced application handling | Group/queue ordering plus matching handler discipline |
| Capacity | Measure partitions, batch size, replication and disk/network limits | Measure queue type, message size, consumers and quotas |

### When to use Kafka

Choose a retained log when job `abc` must feed independent audit and search consumers that can
replay without resubmitting business work. For one worker pool that deletes accepted tasks, measure
the existing database/queue first. Neither a universal jobs-per-second cutoff nor a vendor name
establishes the needed recovery guarantee.


---

## 5. AWS Step Functions

Managed orchestrator with visual workflow designer. Natively supports the Task Token pattern, retries, error handling, and parallel execution.

### Task Token Pattern (Native)

```json
{
  "StartAt": "InvokeWorker",
  "States": {
    "InvokeWorker": {
      "Type": "Task",
      "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken",
      "Parameters": {
        "FunctionName": "worker-lambda",
        "Payload": {
          "job_id.$": "$.job_id",
          "task_token.$": "$$.Task.Token"
        }
      },
      "HeartbeatSeconds": 900,
      "TimeoutSeconds": 3600,
      "Catch": [{
        "ErrorEquals": ["States.Timeout", "States.TaskFailed"],
        "Next": "HandleFailure"
      }],
      "Next": "StoreResult"
    },
    "StoreResult": { "Type": "Pass", "End": true },
    "HandleFailure": { "Type": "Fail" }
  }
}
```

### Distributed Map (Batch Processing)

```json
{
  "Type": "Map",
  "ItemProcessor": {
    "ProcessorConfig": {
      "Mode": "DISTRIBUTED",
      "ExecutionType": "STANDARD"
    },
    "StartAt": "ProcessItem",
    "States": {
      "ProcessItem": {
        "Type": "Task",
        "Resource": "arn:aws:lambda:...",
        "End": true
      }
    }
  },
  "MaxConcurrency": 10
}
```

### When to Use Step Functions

The callback example above is a **Standard Workflow**: Standard supports `.waitForTaskToken` and is
billed per state transition, so waiting does not hold worker compute. **Express Workflows** are
duration/memory billed and do not support callback task tokens; choose them for high-rate,
short-duration flows whose execution and pricing model fits.

**Pick Step Functions when:** You're on AWS and need managed orchestration with visual debugging,
built-in retries, and—when using Standard Workflows—task token callbacks.

**Avoid Step Functions when:** You're not on AWS, a queue plus worker fully owns the lifecycle, or
the selected workflow type's measured latency and billing model do not fit the workload.

---

## 6. Celery

Python-native distributed task queue. Workers are Python processes.

### Setup

```python
from celery import Celery

app = Celery("tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/1")

@app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_job(self, job_id: str, payload: dict):
    try:
        result = do_inference(payload)
        store_result(job_id, result)
    except Exception as exc:
        self.retry(exc=exc)
```

### Client (Submit and Wait)

```python
# Fire and forget
result = process_job.delay(job_id, payload)

# Wait for result (blocking)
result = process_job.delay(job_id, payload)
output = result.get(timeout=600)  # Blocks for up to 10 minutes

# Check status (polling)
result = process_job.delay(job_id, payload)
while not result.ready():
    time.sleep(2)
output = result.get()
```

### When to Use Celery

**Pick Celery when:** Your stack is Python, you want rich task features (retries, rate limits, priority, chords, chains), and you're OK running worker processes.

**Avoid Celery when:** You need language-agnostic workers, you want serverless execution, or you need very high throughput (Celery's overhead per task is higher than raw Redis/SQS).

---

## 7. Temporal

Durable workflow platform. Workflow history supports replay after worker restarts; activities
still require bounded timeouts and idempotent effects. Recovery depends on service/history
durability and the documented deployment contract, not a blanket ranking against Step Functions.

### Workflow Definition

```python
from temporalio import workflow, activity
from datetime import timedelta

@activity.defn
async def process_inference(job_id: str, payload: dict) -> dict:
    return await do_inference(payload)

@workflow.defn
class InferenceWorkflow:
    @workflow.run
    async def run(self, job_id: str, payload: dict) -> dict:
        result = await workflow.execute_activity(
            process_inference,
            args=[job_id, payload],
            start_to_close_timeout=timedelta(minutes=30),
        )
        return result
```

This excerpt uses a 30-minute start-to-close deadline and no heartbeat timeout. If early worker-loss
detection is required, add periodic `activity.heartbeat()` while doing bounded chunks and a
heartbeat timeout longer than the maximum chunk; declaring the timeout alone does not send renewal.

### When to Use Temporal

**Pick Temporal when:** You need recorded workflow progress, recoverable timers or multi-step coordination whose replay/versioning rules your team can operate.

**Avoid Temporal when:** Your workflows are simple (queue + worker), you don't want to run the Temporal server, or you're fully committed to a cloud provider's native tools.

---

## 8. PostgreSQL (LISTEN / NOTIFY + Advisory Locks)

Your database can be the queue. Not the most scalable option, but eliminates infrastructure when you already have PostgreSQL.

### As a Task Queue (SELECT FOR UPDATE SKIP LOCKED)

```sql
-- Create jobs table
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status TEXT DEFAULT 'pending',
    payload JSONB,
    result JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Worker: atomically claim one pending job
UPDATE jobs
SET status = 'running', updated_at = NOW()
WHERE id = (
    SELECT id FROM jobs
    WHERE status = 'pending'
    ORDER BY created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
RETURNING *;
```

### As Real-Time Notification (LISTEN / NOTIFY)

```python
import asyncpg

# Worker/Orchestrator: notify when job completes. NOTIFY's grammar does not
# accept a bind parameter in the payload position; pg_notify() does.
await conn.execute(
    "SELECT pg_notify($1, $2)",
    "job_updates",
    json.dumps({"job_id": job_id, "state": "succeeded"}),
)

# Client: dedicate one persistent pool connection to LISTEN. Returning this
# connection to the pool would make notification ownership ambiguous.
listener_conn = await pool.acquire()
await listener_conn.add_listener(
    "job_updates", lambda conn, pid, channel, payload: handle(payload)
)
assert await listener_conn.fetchval(
    "SELECT EXISTS (SELECT 1 FROM pg_listening_channels() AS channel WHERE channel = $1)",
    "job_updates",
)
```

### When to Use PostgreSQL as Queue

**Pick PostgreSQL when:** Its measured claim rate, table maintenance and connection budget meet the workload and the authoritative data already lives there. Include lease/generation recovery from the canonical job schema; the small `SKIP LOCKED` statement above demonstrates selection only.

**Avoid PostgreSQL when:** Your volume is high (database becomes a bottleneck), you need long message retention, or you need consumer groups.

---

## Decision Matrix

| Need | Best Choice | Runner-Up |
|------|-------------|-----------|
| **Simple async task queue** | SQS (AWS) or Redis Streams | RabbitMQ |
| **Long-running orchestration** | Step Functions (AWS) or Temporal | Celery (simple cases) |
| **Real-time result notification** | Redis Pub/Sub or WebSocket | SSE |
| **Result storage (small)** | Redis (TTL) or PostgreSQL | DynamoDB |
| **Result storage (large)** | S3 / Blob Storage | — |
| **Heartbeat tracking** | Redis (TTL keys) | DynamoDB |
| **Complex routing** | RabbitMQ | Kafka |
| **Event replay / audit** | Kafka | Redis Streams |
| **Zero ops** | SQS + Lambda + Step Functions | — |
| **Already have PostgreSQL, low volume** | PostgreSQL SKIP LOCKED + LISTEN/NOTIFY | — |
| **Python-native workers** | Celery (Redis broker) | — |

---

## Reference Architecture: Putting It All Together

A production system for batched LLM inference using the patterns from this guide:

```
                                    ┌─────────────────────────┐
                                    │      Redis              │
                                    │  - Task queue (Streams) │
                                    │  - Result store (TTL)   │
                                    │  - Heartbeat (TTL keys) │
                                    │  - Pub/Sub notification │
                                    └───────┬────┬────┬───────┘
                                            │    │    │
┌──────────┐    ┌────────────────┐          │    │    │      ┌──────────────┐
│  Client   │──►│  Orchestrator  │──enqueue─┘    │    │      │   Worker(s)  │
│  (any of: │   │  (FastAPI)     │◄──heartbeat───┘    │      │  - Pull from │
│  WS/SSE/  │   │                │◄──result───────────┘      │    Stream    │
│  poll/    │   │  - POST /jobs  │                           │  - Batch     │
│  webhook) │   │  - GET /jobs/  │                           │    collect   │
│           │◄──│  - WS /ws/     │           ┌──subscribe──► │  - Process   │
└──────────┘    │  - SSE /stream │           │               │  - Heartbeat │
                └────────────────┘           │               │  - Callback  │
                         │                   │               └──────────────┘
                         │                   │
                         └── notify clients  │
                             via Redis pub/sub
```

**Flow:**
1. Client POSTs to `/jobs` → gets `202 {job_id}`
2. Orchestrator enqueues to Redis Stream
3. Worker pulls from Stream (consumer group), batches items, runs inference
4. Worker sends heartbeat (Redis TTL key) every 30s
5. Worker writes result to Redis, publishes to pub/sub channel
6. Orchestrator receives pub/sub notification, pushes to connected WebSocket/SSE clients
7. Polling clients hit `GET /jobs/{id}` → orchestrator reads from Redis
8. Webhook clients receive a POST to their callback URL

## Decide from a recovery requirement

**Job `abc` fits PostgreSQL capacity, but a disconnected consumer cannot miss completion. Must you
add Kafka?**

<details><summary>Reasoned answer</summary>

No. Commit a durable result, then notify as a hint; the consumer subscribes and re-reads the row
when connecting or after a bounded wait. That solves missed live notifications. A later requirement
for multiple independently replaying consumers may justify a retained log. Measure that requirement
separately from the worker queue and preserve application effect deduplication either way.

</details>
