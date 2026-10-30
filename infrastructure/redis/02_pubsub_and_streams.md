# Redis Pub/Sub & Streams

<!-- length-justification: This is the canonical Redis messaging comparison and recovery reference; Pub/Sub and Streams remain together because the teaching goal is to expose how durability changes consumer acknowledgement, replay, and idempotency responsibilities. -->

> **Who this is for**: Backend engineers choosing between ephemeral Redis Pub/Sub and retained
> Redis Streams delivery.

> **Two messaging models, one database.** Redis offers two distinct ways to pass messages between producers and consumers. Pub/Sub is fire-and-forget: fast, ephemeral, no history. Streams are durable: messages persist, can be replayed, and support consumer groups. Knowing when to use each is the key decision.

> **Key insight**: Retained messages still require acknowledgement, recovery, and idempotency;
> durability changes consumer responsibility as well as storage.

Mental model:

> **Pub/Sub** = a loudspeaker in a room. If you are not in the room, you miss the message.
> **Streams** = a bulletin board. Messages stay posted. You can read them anytime, and mark which ones you have processed.

---

## Overview

| | Pub/Sub | Streams |
|---|---------|---------|
| Model | Fire-and-forget broadcast | Durable append-only log |
| Persistence | None — messages are lost if no subscriber is listening | Yes — messages persist until explicitly deleted or trimmed |
| Consumer groups | No | Yes |
| Message replay | Impossible | Read from any point in history |
| Delivery | At-most-once | At-least-once (with consumer groups) |
| Best for | Real-time notifications, cache invalidation | Event sourcing, job queues, audit logs |

---

## Part 1: Classic Pub/Sub

### How Pub/Sub Works

1. **Subscribers** listen on one or more channels.
2. **Publishers** send messages to a channel.
3. Redis delivers the message to **all current subscribers** of that channel.
4. If no one is subscribed, the message is **silently dropped**.

```
Publisher                Redis                 Subscribers
─────────              ─────────              ───────────
PUBLISH "chat" "hi" ──> channel: "chat" ──> Subscriber A (listening)
                                         ──> Subscriber B (listening)
                                              Subscriber C (offline) <-- missed
```

### Core Commands

| Command | Description | Example |
|---------|-------------|---------|
| `SUBSCRIBE channel` | Listen to a channel | `SUBSCRIBE notifications` |
| `UNSUBSCRIBE channel` | Stop listening | `UNSUBSCRIBE notifications` |
| `PUBLISH channel message` | Send a message | `PUBLISH notifications "new_order"` |
| `PSUBSCRIBE pattern` | Listen to channels matching a pattern | `PSUBSCRIBE events:*` |
| `PUNSUBSCRIBE pattern` | Stop pattern listening | `PUNSUBSCRIBE events:*` |

### Python Sync Example

```python
import redis
import json
import threading

r = redis.Redis(host="localhost", port=6379, decode_responses=True)

# --- Publisher ---
def publish_event(channel: str, data: dict):
    message = json.dumps(data)
    num_subscribers = r.publish(channel, message)
    print(f"Published to {num_subscribers} subscriber(s)")

# --- Subscriber ---
subscription_ready = threading.Event()


def subscribe_loop(channels: list[str]):
    pubsub = r.pubsub()
    pubsub.subscribe(*channels)

    for message in pubsub.listen():
        if message["type"] == "subscribe":
            print(f"Subscribed to {channels}")
            subscription_ready.set()
        elif message["type"] == "message":
            data = json.loads(message["data"])
            print(f"Received on {message['channel']}: {data}")
            return

# Run subscriber in a thread (it blocks)
thread = threading.Thread(target=subscribe_loop, args=(["notifications"],), daemon=True)
thread.start()
if not subscription_ready.wait(timeout=2):
    raise RuntimeError("subscriber did not confirm within 2 seconds")
publish_event("notifications", {"type": "order_created", "order_id": 42})
thread.join(timeout=2)
```

The observable result is `Published to 1 subscriber(s)` followed by `Received on notifications:`.
Publishing before the subscription acknowledgement legitimately returns zero and leaves a
one-message demo waiting forever because Redis Pub/Sub does not replay missed messages.

### Python Async Example

```python
import redis.asyncio as aioredis
import asyncio
import json

async def subscriber(channel_name: str):
    r = aioredis.Redis(host="localhost", port=6379, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(channel_name)

    print(f"Listening on {channel_name}...")
    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            print(f"Received: {data}")
            # process the message...

    await r.aclose()

async def publisher():
    r = aioredis.Redis(host="localhost", port=6379, decode_responses=True)

    for i in range(5):
        await r.publish("events", json.dumps({"event_id": i, "type": "test"}))
        await asyncio.sleep(1)

    await r.aclose()

async def main():
    # Run subscriber and publisher concurrently
    async with asyncio.TaskGroup() as tg:
        tg.create_task(subscriber("events"))
        tg.create_task(publisher())

asyncio.run(main())
```

### Pattern Subscriptions

Subscribe to multiple channels using glob patterns:

```python
pubsub = r.pubsub()

# Subscribe to all channels starting with "events:"
pubsub.psubscribe("events:*")

# Matches: events:orders, events:payments, events:users
# Does not match: events, notifications:orders

for message in pubsub.listen():
    if message["type"] == "pmessage":
        channel = message["channel"]    # "events:orders"
        pattern = message["pattern"]    # "events:*"
        data = message["data"]          # the message
        print(f"[{channel}] {data}")
```

### When Pub/Sub Works Well

- **Real-time notifications**: Push updates to connected WebSocket clients.
- **Cache invalidation**: Tell all app instances to invalidate a cached key.
- **WebSocket fan-out**: Broadcast messages to all connected users in a chat room.
- **Inter-service coordination**: Signal other services that something happened (and it is OK if they miss it).
- **Feature flag updates**: Notify running instances of configuration changes.

### When Pub/Sub Fails

- **Subscriber goes offline**: Messages during the downtime are permanently lost.
- **Slow subscribers**: Redis buffers messages, then disconnects a subscriber that crosses its configured output limit. Defaults are 32 MB hard or 8 MB for 60 seconds; messages missed during disconnection are permanently lost. Disabling those limits can permit unbounded growth. [Client limits](https://redis.io/docs/latest/develop/reference/clients/) (checked 2026-10-30).
- **Exactly-once processing**: Not possible. No acknowledgments, no retries.
- **Message history**: Cannot replay past messages. No way to ask "what did I miss?"
- **Consumer groups**: No built-in way to distribute messages across multiple workers (every subscriber gets every message).

> **If you need any of the above, use Streams instead.**

---

## Part 2: Streams

### How Streams Work

A stream is an **append-only log**. Each entry has:
- A unique **ID** (auto-generated, based on timestamp: `1679012345678-0`)
- A set of **field-value pairs** (the message data)

Messages persist until explicitly deleted or trimmed. Multiple consumers can read the same stream independently, at their own pace.

```
Stream: "events:orders"
──────────────────────────────────────────────────────────
ID                  Data
1679012345678-0     {"type": "created", "order_id": "1"}
1679012345679-0     {"type": "paid",    "order_id": "1"}
1679012345680-0     {"type": "created", "order_id": "2"}
                    entries persist, can be read anytime
```

### Basic Stream Operations (Async Python)

```python
import redis.asyncio as aioredis
import asyncio

async def stream_demo():
    r = aioredis.Redis(host="localhost", port=6379, decode_responses=True)

    # Add entries to a stream
    entry_id = await r.xadd("events:orders", {
        "type": "order_created",
        "order_id": "42",
        "total": "99.99"
    })
    print(f"Added entry: {entry_id}")

    # Add with a max length (auto-trim old entries)
    await r.xadd("events:orders", {
        "type": "order_paid",
        "order_id": "42"
    }, maxlen=10000, approximate=False)  # keep at most 10,000 entries

    # Approximate trimming (more efficient, slight overcount OK)
    await r.xadd("events:orders", {
        "type": "order_shipped",
        "order_id": "42"
    }, maxlen=10000, approximate=True)  # ~10,000 entries

    # Read all entries
    entries = await r.xrange("events:orders", "-", "+")
    for entry_id, data in entries:
        print(f"  {entry_id}: {data}")

    # Read entries after a specific ID
    entries = await r.xrange("events:orders", "1679012345678-0", "+")

    # Read last 5 entries
    entries = await r.xrevrange("events:orders", "+", "-", count=5)

    # Stream length
    length = await r.xlen("events:orders")
    print(f"Stream has {length} entries")

    await r.aclose()

asyncio.run(stream_demo())
```

### Simple Consumer (Blocking Read)

A simple consumer reads from a stream position and moves forward. Good for single-consumer scenarios or when you manage offsets yourself.

```python
async def stream_listener(r, stream_name: str):
    """Listen for new entries on a stream, starting from now."""
    last_id = "$"  # "$" means "only new entries from this point"

    while True:
        # Block for up to 5 seconds waiting for new entries
        result = await r.xread(
            streams={stream_name: last_id},
            count=10,
            block=5000  # milliseconds
        )

        if not result:
            continue  # timeout, no new entries

        for stream, entries in result:
            for entry_id, data in entries:
                print(f"New entry {entry_id}: {data}")
                last_id = entry_id  # track position
```

---

### Consumer Groups

Consumer groups allow **multiple workers to cooperatively process a stream**. Each delivery is
assigned to one consumer, but the group is at least once: an entry that is not acknowledged can be
claimed and delivered again.

```
Stream: "events:orders"
          |
          +---> Consumer Group "order-processors"
          |       +-- worker-1 (gets some messages)
          |       +-- worker-2 (gets other messages)
          |       +-- worker-3 (gets the rest)
          |
          +---> Consumer Group "analytics"
                  +-- analytics-1 (gets some messages)
                  +-- analytics-2 (gets the rest)
```

Key concepts:

- **Each delivery goes to one consumer within a group** (load distribution); failed deliveries can replay.
- **Different groups are independent** — each group sees every message.
- **Messages must be acknowledged** (`XACK`) — unacknowledged messages can be reclaimed.
- **Pending entries list (PEL)** tracks delivered-but-not-acknowledged messages.

That replay boundary is concrete: a worker can charge order `42`, crash before `XACK`, and leave
the entry pending. A second worker claims it and invokes the handler again. The handler therefore
needs an event ID recorded atomically with the business effect; consumer-group assignment alone
does not make the effect exactly once.

### Consumer Group: Complete Example

```python
import redis.asyncio as aioredis
import asyncio

STREAM = "events:orders"
GROUP = "order-processors"

async def setup_consumer_group(r):
    """Create the stream and consumer group if they don't exist."""
    try:
        await r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        print(f"Created consumer group '{GROUP}'")
    except aioredis.ResponseError as e:
        if "BUSYGROUP" in str(e):
            pass  # group already exists
        else:
            raise

async def consumer(r, consumer_name: str):
    """
    Consume messages from the stream as part of a consumer group.
    Each new delivery goes to one consumer. The handler remains idempotent because
    crash recovery can deliver the same message again.
    """
    print(f"[{consumer_name}] Starting...")

    while True:
        try:
            # Read messages not yet delivered to any consumer in this group
            result = await r.xreadgroup(
                groupname=GROUP,
                consumername=consumer_name,
                streams={STREAM: ">"},  # ">" = only new, undelivered messages
                count=5,
                block=5000
            )

            if not result:
                continue

            for stream, messages in result:
                for msg_id, data in messages:
                    print(f"[{consumer_name}] Processing {msg_id}: {data}")

                    # Simulate work
                    await asyncio.sleep(0.1)

                    # Acknowledge the message (removes it from the pending list)
                    await r.xack(STREAM, GROUP, msg_id)
                    print(f"[{consumer_name}] ACKed {msg_id}")

        except asyncio.CancelledError:
            print(f"[{consumer_name}] Shutting down...")
            break

async def producer(r, count: int = 20):
    """Produce test messages."""
    for i in range(count):
        entry_id = await r.xadd(STREAM, {
            "type": "order_created",
            "order_id": str(i),
            "total": f"{(i + 1) * 10:.2f}"
        })
        print(f"[producer] Added {entry_id}")
        await asyncio.sleep(0.2)

async def main():
    r = aioredis.Redis(host="localhost", port=6379, decode_responses=True)

    await setup_consumer_group(r)

    async with asyncio.TaskGroup() as tg:
        # Start 3 consumers
        tg.create_task(consumer(r, "worker-1"))
        tg.create_task(consumer(r, "worker-2"))
        tg.create_task(consumer(r, "worker-3"))
        # Start producer
        tg.create_task(producer(r, count=20))

    await r.aclose()

asyncio.run(main())
```

### Pending Entries List (PEL) & Recovery

When a consumer reads a message via `XREADGROUP`, that message enters the **Pending Entries List (PEL)**. It stays there until the consumer calls `XACK`. If the consumer crashes, the message remains pending.

```python
async def check_pending(r):
    """Inspect the pending entries list."""
    # Summary: how many pending messages per consumer
    pending_info = await r.xpending(STREAM, GROUP)
    print(f"Total pending: {pending_info['pending']}")
    for consumer_info in pending_info.get("consumers", []):
        print(f"  {consumer_info['name']}: {consumer_info['pending']} pending")

    # Detailed: list specific pending messages
    pending_messages = await r.xpending_range(
        name=STREAM,
        groupname=GROUP,
        min="-",
        max="+",
        count=20
    )
    for msg in pending_messages:
        print(f"  ID: {msg['message_id']}, consumer: {msg['consumer']}, "
              f"idle: {msg['time_since_delivered']}ms, deliveries: {msg['times_delivered']}")
```

#### Reclaiming Failed Messages

```python
async def reclaim_stale_messages(r, consumer_name: str, min_idle_ms: int = 60000):
    cursor = "0-0"
    recovered = 0
    while True:
        cursor, claimed, deleted = await r.xautoclaim(
            STREAM, GROUP, consumer_name, min_idle_time=min_idle_ms,
            start_id=cursor, count=10,
        )
        if deleted:
            raise RuntimeError("Pending payload was trimmed; reconcile source before continuing")
        for msg_id, data in claimed:
            await process_event(data)  # must durably deduplicate the business event
            await r.xack(STREAM, GROUP, msg_id)
            recovered += 1
        if cursor == "0-0":
            return recovered
        # An empty claimed batch does not imply the scan is complete.

# XCLAIM: manually claim specific message IDs (older approach)
claimed = await r.xclaim(
    STREAM,
    GROUP,
    "worker-2",
    min_idle_time=60000,
    message_ids=["1705312800000-0", "1705312800001-0"],
)
```

#### Recovery Pattern: Process Pending Then New

```python
async def consumer_with_recovery(r, group: str, consumer_name: str):
    """Consumer that first processes its own pending messages, then reads new ones."""

    # Phase 1: Re-process any pending (unACKed) messages from a previous crash
    pending_id = "0"
    while True:
        results = await r.xreadgroup(
            groupname=group,
            consumername=consumer_name,
            streams={STREAM: pending_id},  # "0" = read pending messages
            count=10,
        )
        if not results or not results[0][1]:
            break  # no more pending messages

        for stream_name, messages in results:
            for msg_id, msg_data in messages:
                await process_event(msg_data)
                await r.xack(STREAM, group, msg_id)
                pending_id = msg_id

    # Phase 2: Read new messages
    while True:
        try:
            results = await r.xreadgroup(
                groupname=group,
                consumername=consumer_name,
                streams={STREAM: ">"},
                count=10,
                block=5000,
            )
            if results:
                for stream_name, messages in results:
                    for msg_id, msg_data in messages:
                        await process_event(msg_data)
                        await r.xack(STREAM, group, msg_id)
        except asyncio.CancelledError:
            break
```

### Assemble continuous recovery with bounded processing and durable parking

A startup-only pending sweep cannot repair failures that happen later, and `>` never returns an
already-pending entry. The worker must keep alternating new deliveries with scans of the *whole*
group's pending list. This also recovers entries left by a consumer name that will never return.

```mermaid
sequenceDiagram
    participant R as Redis stream and PEL
    participant A as Worker A
    participant D as Durable effect store
    participant B as Replacement worker B
    R->>A: XREADGROUP entry 42 (pending A)
    A->>D: Commit event ID and result together
    Note over A: Crash before XACK
    B->>R: XAUTOCLAIM after idle threshold
    R-->>B: Entry 42, pending B, delivery count 2
    B->>D: Event already committed; skip effect
    B->>R: XACK 42
```

Claim changes delivery ownership; it cannot revoke a paused worker's external request. That is why
both workers use the same durable business event ID. The handler deadline is shorter than the idle
threshold so ordinary slow handling does not immediately trigger duplicate work, but pauses and
network uncertainty still require idempotency.

The complete [stream_worker.py](examples/stream_worker.py) implements one bounded batch at a time,
a preserved `XAUTOCLAIM` cursor, per-handler deadlines, cancellation propagation and a delivery
limit. A failed handler remains pending until the next idle reclaim pass; a successful handler is
acknowledged only after it returns. It deliberately does not claim that Redis makes a remote effect
atomic. Start it with a handler that commits event identity and result in one local transaction.

For a poison event, the worker's Lua script stores **the complete original payload**, source ID,
delivery count and safe error class in a parking stream, records the parking identity, then
acknowledges the source. Both keys and the source use the same hash tag, such as
`orders:{demo}:events`, so this atomic operation is valid on one Redis Cluster slot. Repeating the
script after a lost reply returns the existing parking ID instead of adding another record. Keep
parking identities through the replay horizon; archive them with the parked records instead of
expiring them while the source can still replay. Bound parking storage and stop admission before
exhaustion. Never trim a still-required pending payload: the worker surfaces missing payloads as a
reconciliation failure.

Run the complete fixture from the repository root against a disposable Redis 7 instance:

```bash
docker run --rm -d --name notes-redis-recovery -p 127.0.0.1:16379:6379 redis:7
python3 -m venv /tmp/notes-redis-recovery-venv
/tmp/notes-redis-recovery-venv/bin/python -m pip install 'redis>=5,<6'
/tmp/notes-redis-recovery-venv/bin/python infrastructure/redis/examples/recovery_demo.py
docker stop notes-redis-recovery
```

The fixture seeds an abandoned delivery, a transient failure and a poison payload. It requires two
unique durable results, no remaining pending entries, and one parked record whose payload remains
available after trimming the source. It then repeats the parking operation to verify one parking
identity. Connection refusal means Redis is not ready; the fixture retries startup with a deadline.
These are single-node recovery checks, not a failover or disk-durability certification.

### Stream Trimming

Streams grow indefinitely unless you trim them:

```python
# Trim to exact max length
await r.xtrim(STREAM, maxlen=10000, approximate=False)

# Approximate trim (more efficient — Redis trims in macro-node chunks)
await r.xtrim(STREAM, maxlen=10000, approximate=True)

# Trim by minimum ID (remove entries older than a specific ID)
await r.xtrim(STREAM, minid="1679012345678-0")

# Auto-trim on XADD (recommended approach)
await r.xadd(STREAM, {"data": "value"}, maxlen=10000, approximate=True)
```

---

## Pub/Sub vs Streams: Detailed Comparison

| Feature | Pub/Sub | Streams |
|---------|---------|---------|
| **Persistence** | None. Message gone after delivery. | Yes. Entries persist until trimmed. |
| **Delivery guarantee** | At-most-once | At-least-once (with consumer groups + ACK) |
| **Message replay** | Impossible | Read from any ID, re-read old entries |
| **Consumer groups** | No. Every subscriber gets every message. | Yes. Messages distributed among group members. |
| **Acknowledgments** | No | Yes (`XACK`) |
| **Backpressure** | Buffered until limit, then disconnected; missed messages lost | Consumer reads at its own pace |
| **Pattern matching** | `PSUBSCRIBE events:*` | No (subscribe to specific streams) |
| **Blocking read** | `SUBSCRIBE` (dedicated connection) | `XREAD BLOCK` / `XREADGROUP BLOCK` |
| **Fan-out** | Built-in (all subscribers get it) | Multiple consumer groups on same stream |
| **Throughput** | Very high (simple forwarding) | High (but write + store overhead) |
| **Memory usage** | Minimal (no storage) | Proportional to retained entries |
| **Use case** | Real-time broadcast, ephemeral events | Event sourcing, job queues, audit logs |

### Decision Guide

```
Do you need message persistence?
+-- No  --> Pub/Sub
+-- Yes
    +-- Do you need consumer groups (distribute work)?
    |   +-- No  --> Streams with XREAD
    |   +-- Yes --> Streams with XREADGROUP
    +-- Do you need massive scale (millions/sec)?
        +-- No  --> Redis Streams
        +-- Yes --> Consider Kafka
```

---

## Streams vs Kafka: Quick Comparison

If you are deciding between Redis Streams and Apache Kafka, here is the trade-off:

| Feature | Redis Streams | Apache Kafka |
|---------|---------------|--------------|
| **Setup complexity** | Minimal (Redis is probably already in your stack) | Significant (ZooKeeper/KRaft, brokers, schema registry) |
| **Throughput** | Hundreds of thousands msg/sec | Millions msg/sec |
| **Retention** | In-memory (bounded by RAM) | Disk-based (can retain indefinitely) |
| **Partitioning** | Single stream (no partitions) | Topics with N partitions |
| **Consumer groups** | Yes, with ACK | Yes, with offsets and rebalancing |
| **Ordering** | Per-stream total ordering (single node) | Per-partition ordering |
| **Replication** | Redis Cluster / Sentinel (async) | Built-in multi-broker replication (ISR) |
| **Exactly-once** | No (at-least-once with ACK) | Yes (with transactions) |
| **Schema enforcement** | None (field-value pairs) | Schema Registry (Avro, Protobuf) |
| **Ecosystem** | redis-py | confluent-kafka-python, KSQL, Connect |
| **Operational cost** | Low | High |

### When to Choose Each

**Choose Redis Streams when:**
- You already use Redis for caching/sessions
- Throughput needs are moderate (tens of thousands msg/sec)
- Retention window is hours/days, not months
- You want minimal operational complexity
- The data fits in memory

**Choose Kafka when:**
- You need massive throughput (millions msg/sec)
- You need long-term retention (weeks, months, or forever)
- You need exactly-once semantics
- You have multiple teams/services consuming the same events
- You need schema evolution and compatibility enforcement
- You already have a Kafka cluster

---

## Practical Patterns

### Pattern 1: Pub/Sub for Cache Invalidation

When one app instance updates data, all instances need to know:

```python
import redis.asyncio as aioredis
import asyncio
import json

INVALIDATION_CHANNEL = "cache:invalidate"

async def cache_invalidation_listener(r, local_cache: dict):
    """Listen for invalidation messages and clear local cache."""
    pubsub = r.pubsub()
    await pubsub.subscribe(INVALIDATION_CHANNEL)

    async for message in pubsub.listen():
        if message["type"] == "message":
            key = message["data"]
            local_cache.pop(key, None)
            print(f"Invalidated local cache key: {key}")

async def update_user(r, local_cache: dict, user_id: int, data: dict):
    """Update user in DB and invalidate cache across all instances."""
    # Update in database
    # await db.update_user(user_id, data)

    # Remove from local cache
    cache_key = f"user:{user_id}"
    local_cache.pop(cache_key, None)

    # Tell all instances to invalidate
    await r.publish(INVALIDATION_CHANNEL, cache_key)
```

### Pattern 2: Pub/Sub for WebSocket Fan-Out

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import redis.asyncio as aioredis
import json

app = FastAPI()

@app.websocket("/ws/chat/{room}")
async def websocket_chat(websocket: WebSocket, room: str):
    await websocket.accept()
    r = app.state.redis

    pubsub = r.pubsub()
    await pubsub.subscribe(f"chat:{room}")

    try:
        # Fan out: forward Redis messages to WebSocket
        async for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(f"chat:{room}")
        await pubsub.aclose()

async def send_chat_message(r, room: str, user: str, text: str):
    """Send a message to a chat room (from any app instance)."""
    await r.publish(f"chat:{room}", json.dumps({
        "user": user,
        "text": text,
        "room": room
    }))
```

### Pattern 3: Streams for Activity Feed

```python
async def add_activity(r, user_id: int, action: str, details: dict):
    """Add an activity event to the user's activity stream."""
    stream_key = f"activity:{user_id}"
    await r.xadd(stream_key, {
        "action": action,
        **{k: str(v) for k, v in details.items()}
    }, maxlen=1000, approximate=True)  # keep last ~1000 activities

async def get_recent_activity(r, user_id: int, count: int = 20):
    """Get the most recent activities for a user."""
    stream_key = f"activity:{user_id}"
    entries = await r.xrevrange(stream_key, "+", "-", count=count)
    return [
        {"id": entry_id, **data}
        for entry_id, data in entries
    ]
```

### Pattern 4: Combined Pub/Sub + Streams in FastAPI

Integration excerpt: combine the canonical worker with Pub/Sub notifications. Supply
`persist_order_effect_once` using the inbox transaction from the messaging lesson before running
this app; the complete recovery fixture above supplies an executable local effect implementation.
The deterministic event ID below assumes order IDs are unique and creation occurs only once.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import redis.asyncio as aioredis
import asyncio
import json

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.Redis(
        host="localhost", port=6379, decode_responses=True,
    )

    # Start stream consumer in background
    consumer_task = asyncio.create_task(
        order_stream_consumer(app.state.redis)
    )

    yield

    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await app.state.redis.aclose()

app = FastAPI(lifespan=lifespan)

@app.post("/orders")
async def create_order(order_id: int, user_id: int):
    r = app.state.redis

    # Retain the event in the stream. Processing still requires persistence,
    # pending-entry recovery, and an idempotent handler.
    await r.xadd("events:{orders}", {
        "event_id": f"order-created:{order_id}",
        "action": "created",
        "order_id": str(order_id),
        "user_id": str(user_id),
    })

    # Also notify via pub/sub (real-time, best effort)
    await r.publish(f"notifications:{user_id}", json.dumps({
        "message": f"Order {order_id} created",
    }))

    return {"order_id": order_id, "status": "created"}

async def order_stream_consumer(r: aioredis.Redis):
    from stream_worker import consume  # copy the linked example beside this app
    stop = asyncio.Event()

    async def handle(entry_id, fields):
        # Supply the application's atomic inbox/effect transaction here.
        await persist_order_effect_once(fields["event_id"], fields)

    await consume(r, "events:{orders}", "api-order-processors", "api-worker-1",
                  handle, stop=stop)

```

`XADD` retains the entry for later reads; it does not guarantee the business effect. The deployment
must choose an RDB/AOF loss window, reclaim stale pending entries, acknowledge only after the effect
is durable, and make the handler replay-safe. Use the reliable processor earlier in this note for
recovery and [HA and Persistence](06_ha_and_persistence.md) for the storage loss window.

---

## Common Mistakes

### Mistake 1: Using Pub/Sub When You Need Durability

```python
# BAD: Using Pub/Sub for job processing
# If the worker is down when the message is published, the job is lost
await r.publish("jobs", json.dumps(job_data))

# GOOD: Using Streams for job processing
await r.xadd("jobs:stream", job_data)
```

### Mistake 2: Not Acknowledging Stream Messages

```python
# BAD: Reading without ACK — messages pile up in pending list
result = await r.xreadgroup(groupname=GROUP, consumername="w1",
                             streams={STREAM: ">"}, count=10)
for stream, messages in result:
    for msg_id, data in messages:
        process(data)
        # forgot to XACK!

# GOOD: Always ACK after successful processing
for stream, messages in result:
    for msg_id, data in messages:
        process(data)
        await r.xack(STREAM, GROUP, msg_id)
```

### Mistake 3: Not Trimming Streams

```python
# BAD: Stream grows forever, eventually fills RAM
await r.xadd("events", {"data": "value"})

# GOOD: Trim on every add
await r.xadd("events", {"data": "value"}, maxlen=50000, approximate=True)
```

### Mistake 4: Using a Single Redis Connection for Pub/Sub and Commands

With RESP2, subscribing restricts that connection to the permitted Pub/Sub-mode commands. RESP3 permits other commands while subscribed; redis-py still gives its Pub/Sub object a dedicated pooled connection. [SUBSCRIBE protocol behavior](https://redis.io/docs/latest/commands/subscribe/) (checked 2026-10-30).

```python
# This works because redis-py uses connection pooling internally.
# r.pubsub() gets its own connection from the pool.
# But if you manually manage a single connection, you will get errors.

# GOOD: Use connection pooling (default behavior of redis-py)
r = aioredis.Redis(host="localhost", port=6379)  # has a pool
pubsub = r.pubsub()  # gets its own connection
await r.get("some_key")  # uses a different connection from pool
```

## Versioned stream capabilities

Checked 2026-10-30. **GA:** Redis 8.2's `KEEPREF`, `DELREF` and `ACKED` policies make payload
deletion versus consumer-group references explicit; `XACKDEL` combines acknowledgement and
policy-aware deletion. Choose a policy only after tracing every group that still needs the entry.
The Redis 7 worker above treats a trimmed pending payload as a failure requiring reconciliation.
[Stream lifecycle](https://redis.io/docs/latest/develop/data-types/streams/).

**GA:** 8.6 `XADD IDMP`/`IDMPAUTO` suppress eligible producer retries within configured retention.
They do not atomically commit your database effect with `XACK`; retain the durable inbox and
parking protocol. [XADD](https://redis.io/docs/latest/commands/xadd/).
**GA:** 8.10 `MAXCOUNT`/`MAXSIZE` cap cumulative `XREAD`/`XREADGROUP` replies across streams, whereas
`COUNT` alone applies per stream. Size application concurrency separately from reply bytes and
verify the installed client's command arguments before using them.
[XREAD limits](https://redis.io/docs/latest/commands/xread/).

### Serial delivery reservation is part of the idle budget

The complete worker reads or claims **one** entry before running its handler. Fetching ten and handling them serially would start all ten pending idle clocks at receipt; the last could be reclaimed while merely waiting behind healthy work. `processing_seconds < idle_ms` protects only an immediately started cooperative handler, with sufficient network/scheduling margin. It does not prove exclusivity against a stopped process or event-loop stall; durable business idempotency remains required.

Run the two-consumer regression against the same disposable Redis fixture:

```bash
python infrastructure/redis/examples/slow_consumer_probe.py redis://127.0.0.1:16379
```

Six 40ms effects use a 50ms handler deadline and 60ms reclaim threshold. At 75ms the second consumer must reclaim zero healthy queued entries; all six finish once with no pending entries. The old ten-entry reservation makes four waiting entries incorrectly eligible in this trace. For concurrent processing, budget queue residence plus processing and use an explicit ownership/renewal design.

## Recap

- Pub/Sub reaches connected subscribers; Streams retain payloads subject to storage policy.
- The PEL tracks unsettled delivery, not whether the business effect committed.
- Continuous reclaim and atomic payload parking make retry and poison outcomes recoverable.

## Check yourself

**Q: A handler commits its database effect then crashes before XACK. What prevents a second effect on reclaim?**

<details><summary>Answer</summary>

A durable event-ID record committed atomically with the effect. PEL delivery count alone cannot prove business completion. The replacement reads that record, skips the duplicate effect and acknowledges.

</details>

**Q: XAUTOCLAIM returns no entries but a nonzero cursor. Has the scan finished?**

<details><summary>Answer</summary>

No. The scanned entries may not yet be idle, while eligible entries lie later. Preserve the returned cursor and continue until 0-0; repeatedly restarting at 0-0 can starve later work.

</details>

## Try it

Change the recovery fixture so a poison payload is parked, then trim the source before inspecting the parking stream.

Hint: Parking must contain the complete payload, not just source_id.

<details><summary>Worked solution</summary>

The parking record remains reconstructable and is present exactly once because the Lua operation records parking identity and acknowledgement together. The business effect ledger still has only the two successful events.

</details>
