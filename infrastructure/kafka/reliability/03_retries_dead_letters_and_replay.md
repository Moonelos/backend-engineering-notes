# Recovery Paths Must Preserve the Evidence of Failure

> **Who this is for**: engineers handling transient failures and poison records.

## Retry by failure class, not by exception count

A timeout may succeed on retry; an invalid currency will not. Retry transient failures with bounded
backoff. Route a repeatedly unprocessable record to a **dead-letter topic (DLT)** with its original
topic, partition, offset, key, payload reference, error class, and attempt count.

```text
orders → handler → transactionally publish retry/DLT + commit source offset
                    ↓
              retry scheduler waits until next_attempt_at
                    ↓
              republish to ready topic → handler
```

Use one envelope through the whole path so recovery never loses provenance:

```json
{
  "event_id": "evt-101",
  "source": {"topic": "orders", "partition": 2, "offset": 8},
  "attempt": 1,
  "first_failed_at": "2026-09-10T09:00:00Z",
  "next_attempt_at": "2026-09-10T09:00:05Z",
  "error_class": "PaymentGatewayTimeout",
  "payload": {"order_id": "ord-42", "currency": "EUR", "total_minor": 2590}
}
```

Bound the policy: attempts 1–3 use delays of 5, 30, and 120 seconds; attempt 4 writes the envelope
to `orders.dlt` with `next_attempt_at=null`. The observable record path is:

```text
orders[2]@8 → retry.5s(attempt=1) → retry.30s(attempt=2)
            → retry.120s(attempt=3) → orders.dlt(attempt=4)
```

A topic name does not create a delay. The **retry scheduler** consumes the retry topic, owns each
record's `next_attempt_at` state, pauses that partition until the earliest due record, and republishes
due work to the ready topic. Because a partition is ordered, a far-future record at its head can
block later due records; bucketed delay topics limit that head-of-line cost but do not provide
per-record precision. For high precision or very long delays, store the schedule in a database or
purpose-built job system and publish only when due.

---

## 1. Retry topics trade ordering for availability

Moving offset 8 aside lets offset 9 proceed, so entity order can change. If order is required, block
the partition with bounded retries or isolate failing keys through another design.

The handoff must also survive a crash. With both source and retry/DLT inside Kafka, use one Kafka
transaction:

```text
begin transaction
produce retry envelope with key=ord-42
send source next offset 9 to transaction
commit transaction
```

Before commit, neither a `read_committed` retry consumer nor the source group's offset observes the
handoff. After commit, both become visible. If an external scheduler or store is used instead, give
the recovery envelope a stable identity such as `evt-101:attempt-1` and claim it durably so a crash
cannot create unbounded duplicates. Committing the source offset and then publishing loses the
recovery record; publishing and then committing without a transaction can duplicate it.

The checked-in scheduler implements the Kafka-only boundary with one in-flight record per
scheduler partition. It pauses that partition until `next_attempt_at` while continuing to poll for
group health, then transactionally publishes to the ready topic and commits the retry offset.
Start the disposable broker and, from `infrastructure/kafka/examples/python`, run:

```bash
uv sync --dev
uv run pytest -q tests/integration/test_retry_scheduler.py
```

[`retry_scheduler.py`](../examples/python/kafka_notes/retry_scheduler.py) first prints a positive
`WAITING delay_ms=...`. The test kills its first process after `RETRY_STAGED` but before transaction
commit, then restarts with the same `transactional.id`. **Success signal:** `1 passed`; the second
process prints `RETRY_COMMITTED next_offset=1`, and a `read_committed` consumer sees exactly one
ready record with key `ord-42`; the retry group's stored offset is exactly `1`. If the scheduler
publishes immediately, the due-time assertion fails; if source and destination are not atomic, the
output-count or committed-offset assertion fails.

This minimal scheduler deliberately serializes one partition. A production scheduler must bound
the number of paused partitions and buffered envelopes, expose oldest-due age, and prevent a single
far-future head record from exhausting assignment capacity. Use coarse delay buckets or an external
schedule store when that bound is too restrictive.

---

## 2. Replay is a production write operation

Replay with a new consumer group or explicit offsets only after checking retention, schema support,
downstream idempotency, rate limits, and expected volume. Record who initiated it and its bounds.

First seed one exact DLT record in the disposable broker:

```bash
docker exec kafka-notes /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --create --if-not-exists \
  --topic orders.dlt --partitions 1 --replication-factor 1
docker exec kafka-notes /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --create --if-not-exists \
  --topic orders.replay.reviewed --partitions 1 --replication-factor 1
printf '%s\t%s\n' 'ord-42' '{"event_id":"evt-101","source":{"topic":"orders","partition":2,"offset":8},"attempt":4}' | \
  docker exec -i kafka-notes /opt/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server localhost:9092 --topic orders.dlt \
    --reader-property parse.key=true --reader-property key.separator=$'\t'
```

After correcting the bad dependency or payload, replay only that audited slice into a staging topic.
Both command-line tools run inside the documented container:

```bash
docker exec kafka-notes /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders.dlt --partition 0 --offset 0 --max-messages 1 --timeout-ms 10000 \
  --formatter-property print.key=true --formatter-property key.separator=$'\t' \
  | docker exec -i kafka-notes /opt/kafka/bin/kafka-console-producer.sh \
      --bootstrap-server localhost:9092 --topic orders.replay.reviewed \
      --reader-property parse.key=true --reader-property key.separator=$'\t'

docker exec kafka-notes /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic orders.replay.reviewed \
  --from-beginning --max-messages 1 --timeout-ms 10000 \
  --formatter-property print.key=true --formatter-property key.separator=$'\t'
```

The replay bounds are DLT partition 0, DLT offset 0, and one record; the envelope independently
preserves source partition 2 and source offset 8. First inspect the console output in a
non-production drill because console key formatting must match the chosen producer properties.
**Success signal:** `orders.replay.reviewed` receives one record with `event_id=evt-101`, while the
idempotency store still reports one business effect. If more than one record moves, the replay was
not bounded as intended.

For the seeded drill, the final command prints key `ord-42` and an envelope containing
`"event_id":"evt-101"`. In an application replay, also query the durable idempotency store and
require one business effect. DLT depth alone silently hides events that lost their source identity.

> **Key insight**: a dead-letter topic is evidence and a recovery queue, not successful handling.

---

## 3. What breaks, and when not to retry

⚠️ Unbounded immediate retries can pin a partition and overload the dependency already failing.

Do not retry validation errors, authorization denials, or permanent missing resources without a
specific state change that could make the next attempt succeed.

---

**Next**: [Polling Transactional Outbox](04_transactional_outbox_and_cdc.md), then the separate
[CDC relay](06_cdc_outbox_relay.md) when database-log capture is justified.
