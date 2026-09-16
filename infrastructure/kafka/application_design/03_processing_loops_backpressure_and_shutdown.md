# Safe Consumers Bound Work Before They Commit Progress

> **Who this is for**: engineers turning a demo consumer into a long-running worker.

## The failure: polling outruns processing

A consumer fetches 500 records and launches 500 coroutines against a database pool of 20. Memory
grows, timeouts cascade, polling stalls, and the group reassigns the partition while old work still
runs. The fix is bounded in-flight work plus partition-aware commits.

---

## 1. Backpressure keeps fetched work within downstream capacity

Use a semaphore or bounded queue sized from the actual downstream bottleneck. Pause assigned
partitions when capacity is full and resume them after work completes, while continuing the client
heartbeats required by its protocol.

```text
poll → bounded queue (100) → workers (20) → database
          full: pause partitions       success: mark offset complete
```

Rate limits and concurrency limits solve different problems: a rate limit bounds work per time;
concurrency bounds simultaneous resource occupancy.

---

## 2. Parallel completion cannot commit through a gap

Offsets 10, 11, and 12 run concurrently. If 11 fails while 12 succeeds, committing 13 would skip 11
on restart. Track completed offsets and advance the commit frontier only through the highest
contiguous success—in this case, 11 until offset 11 succeeds.

For simpler correctness, process each partition sequentially and parallelize across partitions.
Add within-partition concurrency only when order is irrelevant and the commit-frontier complexity
is justified.

---

## 3. Shutdown is a protocol, not a signal handler

On termination: stop accepting new work, keep group membership alive if possible, finish within a
deadline, commit only contiguous successes, then close the consumer. If the deadline expires,
abandon unfinished work and rely on idempotent replay.

**Success signal:** terminate the worker during a controlled slow event; after restart, every
unfinished event reappears and no completed effect is missing. Low lag alone cannot prove this.

> **Key insight**: consumer concurrency is safe only when ownership, completion, and committed
> progress remain aligned at partition granularity.

---

## 4. Assemble the lifecycle in one bounded worker

This worker allows out-of-order completion but advances each partition's commit frontier only
through contiguous successes. Save it as `bounded_worker.py`; set `KAFKA_TOPIC` and `KAFKA_GROUP`
to test-specific values.

```python
import json
import os
import signal
import threading
import time
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass

from confluent_kafka import Consumer, TopicPartition

MAX_IN_FLIGHT = 100
RESUME_AT = 50
SHUTDOWN_SECONDS = 3
stop = threading.Event()


class OwnershipEnded(Exception):
    """The partition epoch ended before this task reached its effect."""


@dataclass
class Lease:
    topic: str
    partition: int
    generation: int
    cancelled: threading.Event


def handle(raw: bytes, lease: Lease) -> None:
    event = json.loads(raw)
    print("started", event["event_id"], "generation", lease.generation, flush=True)
    # Event.wait is a cancellable stand-in for work. A real handler must propagate this lease
    # to cancellable I/O and atomically fence its durable effect by partition generation.
    if lease.cancelled.wait(event.get("work_ms", 0) / 1000):
        raise OwnershipEnded
    if lease.cancelled.is_set():
        raise OwnershipEnded
    # A real effect must also deduplicate by event_id before replay is safe.
    print("effect", event["event_id"], "generation", lease.generation, flush=True)


class Frontier:
    def __init__(self) -> None:
        self.next_offset: dict[tuple[str, int], int] = {}
        self.done: dict[tuple[str, int], set[int]] = defaultdict(set)

    def observe(self, topic: str, partition: int, offset: int) -> None:
        self.next_offset.setdefault((topic, partition), offset)

    def complete(self, topic: str, partition: int, offset: int) -> None:
        self.done[(topic, partition)].add(offset)

    def committable(self, owned: set[tuple[str, int]]) -> list[TopicPartition]:
        result = []
        for key, frontier in list(self.next_offset.items()):
            if key not in owned:
                continue
            while frontier in self.done[key]:
                self.done[key].remove(frontier)
                frontier += 1
            if frontier != self.next_offset[key]:
                self.next_offset[key] = frontier
                result.append(TopicPartition(key[0], key[1], frontier))
        return result


consumer = Consumer({
    "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP", "localhost:9092"),
    "group.id": os.environ["KAFKA_GROUP"],
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
})
pool = ThreadPoolExecutor(max_workers=20)
frontier = Frontier()
pending: dict[tuple[str, int, int], tuple[Future, Lease]] = {}
owned: set[tuple[str, int]] = set()
generations: dict[tuple[str, int], int] = defaultdict(int)
paused = False
shutdown_deadline: float | None = None


def reap() -> None:
    for position, (future, lease) in list(pending.items()):
        if not future.done():
            continue
        del pending[position]
        topic, partition, offset = position
        key = (topic, partition)
        try:
            future.result()
        except OwnershipEnded:
            print("cancelled", topic, partition, offset, flush=True)
        except Exception as error:
            print("handler-failed", topic, partition, offset, repr(error), flush=True)
            stop.set()  # leave this offset and every later gap uncommitted for replay
        else:
            # Ignore a completion from an older assignment even if its Future finishes late.
            if key in owned and lease.generation == generations[key] and not lease.cancelled.is_set():
                frontier.complete(topic, partition, offset)
    offsets = frontier.committable(owned)
    if offsets:
        consumer.commit(offsets=offsets, asynchronous=False)
        print("committed", [(p.topic, p.partition, p.offset) for p in offsets], flush=True)


def drain(deadline: float) -> None:
    while pending and time.monotonic() < deadline:
        reap()
        time.sleep(0.05)
    reap()  # commit only completed offsets; unfinished futures remain behind the frontier


def on_assign(client, partitions) -> None:
    keys = {(p.topic, p.partition) for p in partitions}
    for key in keys:
        generations[key] += 1
        owned.add(key)
    print("assigned", sorted(keys), flush=True)


def fence(keys: set[tuple[str, int]]) -> None:
    for (topic, partition, _), (_, lease) in list(pending.items()):
        if (topic, partition) in keys:
            lease.cancelled.set()


def forget(keys: set[tuple[str, int]]) -> None:
    owned.difference_update(keys)
    for key in keys:
        frontier.next_offset.pop(key, None)
        frontier.done.pop(key, None)


def wait_until_fenced_work_stops(keys: set[tuple[str, int]], deadline: float) -> None:
    while any((t, p) in keys for t, p, _ in pending) and time.monotonic() < deadline:
        reap()
        time.sleep(0.01)
    reap()
    if any((t, p) in keys for t, p, _ in pending):
        # Returning would allow a new member to own the partition while this process still works.
        print("fatal-unfenced-work", sorted(keys), flush=True)
        os._exit(3)


def on_revoke(client, partitions) -> None:
    revoked = {(p.topic, p.partition) for p in partitions}
    fence(revoked)  # make queued/cancellable work fail before its effect
    deadline = shutdown_deadline or (time.monotonic() + SHUTDOWN_SECONDS)
    wait_until_fenced_work_stops(revoked, deadline)
    # on_revoke is the last point at which ownership is still usable. Effects reaped before this
    # callback were committed; fenced work is deliberately replayed. After forget(), no code can
    # form a commit for these partitions.
    forget(revoked)
    print("revoked", sorted(revoked), flush=True)


def on_lost(client, partitions) -> None:
    lost = {(p.topic, p.partition) for p in partitions}
    # Ownership may already belong to another member: remove it before reaping, so no commit is
    # attempted even for a Future that happened to finish at the same moment.
    forget(lost)
    fence(lost)
    stop.set()
    wait_until_fenced_work_stops(lost, time.monotonic() + SHUTDOWN_SECONDS)
    print("lost", sorted(lost), flush=True)


signal.signal(signal.SIGTERM, lambda *_: stop.set())
signal.signal(signal.SIGINT, lambda *_: stop.set())

try:
    consumer.subscribe(
        [os.environ["KAFKA_TOPIC"]],
        on_assign=on_assign,
        on_revoke=on_revoke,
        on_lost=on_lost,
    )
    while not stop.is_set():
        reap()
        assignment = consumer.assignment()
        if len(pending) >= MAX_IN_FLIGHT and not paused:
            consumer.pause(assignment)
            paused = True
        elif paused and len(pending) <= RESUME_AT:
            consumer.resume(assignment)
            paused = False

        message = consumer.poll(0.25)  # polling continues while partitions are paused
        if message is None:
            continue
        if message.error():
            raise RuntimeError(message.error())
        position = (message.topic(), message.partition(), message.offset())
        frontier.observe(*position)
        key = position[:2]
        cancelled = threading.Event()
        lease = Lease(*key, generations[key], cancelled)
        pending[position] = (pool.submit(handle, message.value(), lease), lease)
finally:
    shutdown_deadline = time.monotonic() + SHUTDOWN_SECONDS
    drain(shutdown_deadline)
    unfinished = len(pending)
    fence(set(owned))
    wait_until_fenced_work_stops(set(owned), time.monotonic() + SHUTDOWN_SECONDS)
    consumer.close()
    pool.shutdown(wait=False, cancel_futures=True)
    print("shutdown", "unfinished", unfinished, flush=True)
    if unfinished:
        os._exit(2)  # thread work cannot be force-cancelled; end the process at the deadline
```

The consumer alone calls client APIs; worker threads only perform the handler. Pause/resume bounds
memory, polling preserves membership, and `Frontier` refuses to commit through a failed or
unfinished offset. A normal revoke first fences that partition's tasks, waits for them to stop, and
only then returns ownership. `on_lost` removes ownership *before* it reaps, because the partition may
already have another owner and no commit is safe. `reap()` also checks both the current generation
and `owned`, so a late completion cannot commit after either callback.

The example's effect is a `print`, so its cancellation check is enough for the drill. A database or
remote API requires a stronger boundary: make the partition generation part of an atomic database
write, use a downstream fencing token, or isolate work in killable processes. A thread that is
already inside an unfenceable remote side effect cannot be made ownership-safe by a Python flag;
the hard exit prevents this worker from returning from a revoke while such work remains, but
idempotency is still required if the remote system may have accepted the request.

Use a fresh topic and group for this termination drill. Publish a slow record followed by a fast
record, start the worker with output redirected to `worker.log`, wait until `started evt-slow`
appears, then send `SIGTERM`:

```bash
export KAFKA_TOPIC="orders.worker-test-$RANDOM" KAFKA_GROUP="worker-test-$RANDOM"
docker exec kafka-notes /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --create --topic "$KAFKA_TOPIC" \
  --partitions 1 --replication-factor 1
printf '%s\n' \
  '{"event_id":"evt-slow","work_ms":10000}' \
  '{"event_id":"evt-fast","work_ms":0}' | \
  docker exec -i kafka-notes /opt/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server localhost:9092 --topic "$KAFKA_TOPIC"
uv run --with confluent-kafka python bounded_worker.py >worker.log 2>&1 & worker_pid=$!
until grep -q 'started evt-slow' worker.log; do kill -0 "$worker_pid"; sleep 0.1; done
kill -TERM "$worker_pid"
wait "$worker_pid" || test "$?" -eq 2
grep '^shutdown' worker.log
uv run --with confluent-kafka python bounded_worker.py >restart.log 2>&1 & restart_pid=$!
until grep -q '^effect evt-slow' restart.log && grep -q '^effect evt-fast' restart.log; do
  kill -0 "$restart_pid"; sleep 0.1
done
kill -TERM "$restart_pid"
wait "$restart_pid" || test "$?" -eq 2
grep '^effect' restart.log
```

**Success signal:** the first run prints `shutdown unfinished 1` or more after the three-second
deadline; the restart receives every offset at or after the first unfinished gap. An effect that
completed beyond that gap may repeat, so the real handler must deduplicate by `event_id`. If restart
begins after an unfinished offset, the frontier or commit call advanced too far.

> **Production:** add structured metrics, handler-specific retry policy, idempotent effects, and a
> test-controlled fault hook. The reusable crash harness is in
> [Testing Kafka Services](../reliability/05_testing_kafka_services.md).

### Force a rebalance and prove revoked work is fenced

The shutdown drill does not exercise ownership transfer. This live integration drill requires the
same disposable `kafka-notes` broker; it creates an isolated two-partition topic and group. Save the
following producer as `seed_rebalance.py` beside the worker:

```python
import json
import os
from confluent_kafka import Producer

producer = Producer({"bootstrap.servers": "localhost:9092"})
for partition in (0, 1):
    producer.produce(
        os.environ["KAFKA_TOPIC"],
        partition=partition,
        key=f"order-{partition}",
        value=json.dumps({"event_id": f"evt-p{partition}", "work_ms": 5000}),
    )
if producer.flush(10):
    raise RuntimeError("seed records were not acknowledged")
print("seeded partitions 0 and 1")
```

Run these commands from a shell with job control. The first consumer initially owns both
partitions; starting the second member forces one partition to move:

```bash
export KAFKA_TOPIC="orders.rebalance-$RANDOM" KAFKA_GROUP="rebalance-$RANDOM"
docker exec kafka-notes /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --create --topic "$KAFKA_TOPIC" \
  --partitions 2 --replication-factor 1
uv run --with confluent-kafka python seed_rebalance.py
uv run --with confluent-kafka python bounded_worker.py >worker-a.log 2>&1 & worker_a=$!
until [ "$(grep -c '^started evt-p' worker-a.log)" -ge 2 ]; do
  kill -0 "$worker_a"; sleep 0.1
done
uv run --with confluent-kafka python bounded_worker.py >worker-b.log 2>&1 & worker_b=$!
until grep -q '^revoked' worker-a.log && grep -q '^effect evt-p' worker-b.log; do
  kill -0 "$worker_a"; kill -0 "$worker_b"; sleep 0.1
done
kill -TERM "$worker_a" "$worker_b"
wait "$worker_a" || test "$?" -eq 2
wait "$worker_b" || test "$?" -eq 2
grep -E '^(revoked|cancelled|effect)' worker-a.log worker-b.log
```

**Success signal:** `worker-a.log` contains `revoked` and `cancelled` for work from its old
assignment; `worker-b.log` contains the moved partition's `effect`. Under the default eager
assignor, `worker-a` may receive one partition back and process it only after a new `assigned` line;
that is a new generation, not post-revoke work. A `lost` line is a different path: ownership was
already gone, so the worker fences and stops without committing. This drill was designed for a live
local broker; if that broker is unavailable, parsing the script is not evidence that the ownership
transition passed.

---

## 5. What breaks, and when not to parallelize

⚠️ Committing the largest completed offset silently skips earlier unfinished records. The symptom is
a business gap with a healthy committed lag metric.

Do not parallelize within a partition when processing order is part of the invariant. Increase
partitions with a correct key or optimize the handler before weakening ordering.

---

**Next**: [Topic and Partition Design](04_topic_and_partition_design.md)
