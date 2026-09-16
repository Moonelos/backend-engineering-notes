# A Python Client Must Make Delivery and Shutdown Explicit

> **Who this is for**: Python developers with the local broker from the fundamentals quick start.

## Run one complete Python round trip

Prerequisites are Python 3.11+, `uv`, and the disposable broker from
[the first round trip](../fundamentals/01_first_event_round_trip.md), still running as
`kafka-notes`. Create the topic idempotently and verify the broker before writing code:

```bash
docker exec kafka-notes /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --create --if-not-exists \
  --topic orders --partitions 1 --replication-factor 1
docker exec kafka-notes /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 --describe --topic orders
```

The second command must print a line containing `Topic: orders`. `No such container:
kafka-notes` means the broker prerequisite is absent; return to the linked setup rather than
debugging the Python client.

Save the contract below as `order-created-v1.schema.json` in a new empty working directory. It is
the same v1 contract introduced in the previous lesson, included here so this round trip does not
depend on an undeclared Python module:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["event_id", "event_type", "schema_version", "occurred_at", "producer", "data"],
  "properties": {
    "event_id": {"type": "string", "minLength": 1},
    "event_type": {"const": "order.created"},
    "schema_version": {"type": "integer", "minimum": 1},
    "occurred_at": {"type": "string", "format": "date-time"},
    "producer": {"type": "string", "minLength": 1},
    "data": {
      "type": "object",
      "required": ["order_id", "currency", "total_minor"],
      "properties": {
        "order_id": {"type": "string", "minLength": 1},
        "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
        "total_minor": {"type": "integer", "minimum": 0}
      },
      "additionalProperties": true
    }
  },
  "additionalProperties": true
}
```

Save this as `kafka_round_trip.py` beside the schema:

```python
import json
import os
import time
from pathlib import Path

from confluent_kafka import Consumer, Producer
from jsonschema import Draft202012Validator, FormatChecker

schema = json.loads(Path(__file__).with_name("order-created-v1.schema.json").read_text())
validator = Draft202012Validator(schema, format_checker=FormatChecker())


def validate_event(event: dict) -> None:
    validator.validate(event)

delivery = {"ack": None, "error": None}


def delivered(error, message):
    delivery["error" if error else "ack"] = error or (message.partition(), message.offset())


producer = Producer({"bootstrap.servers": "localhost:9092"})
payload = {
    "event_id": "evt-101", "event_type": "order.created", "schema_version": 1,
    "occurred_at": "2026-09-04T09:15:00Z", "producer": "orders-api",
    "data": {"order_id": "ord-42", "currency": "EUR", "total_minor": 2590},
}
validate_event(payload)  # reject contract drift before it becomes retained data
producer.produce("orders", key="ord-42", value=json.dumps(payload), callback=delivered)
remaining = producer.flush(10)
if remaining or delivery["error"]:
    raise RuntimeError(f"broker delivery failed: remaining={remaining}, error={delivery['error']}")
if delivery["ack"] is None:
    raise RuntimeError("no delivery acknowledgment was observed")
print("delivered", *delivery["ack"])

consumer = Consumer({
    "bootstrap.servers": "localhost:9092",
    "group.id": os.environ["KAFKA_GROUP"],
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
})
deadline = time.monotonic() + 15
try:
    consumer.subscribe(["orders"])
    while time.monotonic() < deadline:
        message = consumer.poll(1.0)
        if message is None:
            continue
        if message.error():
            raise RuntimeError(f"broker/client error while polling: {message.error()}")
        event = json.loads(message.value())
        validate_event(event)  # consumers distrust retained bytes too
        print("consumed", message.partition(), message.offset(), event["data"]["order_id"])
        consumer.commit(message=message, asynchronous=False)
        break
    else:
        raise TimeoutError("no unread record arrived within 15s; check topic, group, and offsets")
finally:
    consumer.close()
```

Run it in an isolated environment; a fresh group makes the record unread by no previous run:

```bash
KAFKA_GROUP="notes-demo-$(date +%s)" \
  uv run --with confluent-kafka --with jsonschema python kafka_round_trip.py
```

**Success signal:** it prints `delivered <partition>
<offset>` from the broker acknowledgment followed by `consumed <partition> <offset> ord-42`.
Rerunning with a new timestamped group reads the retained records from the beginning; deliberately
reusing a group consumes only records after its committed position. A delivery failure names the
broker error; a poll failure names the client error; and no unread record exits after 15 seconds
with a topic/group/offset diagnostic instead of hanging. Stop the disposable broker with
`docker stop kafka-notes` only when you have finished the later live drills.

---

## 1. `produce` enqueues locally before the broker acknowledges

The producer batches asynchronously. A successful `produce()` call means the local client accepted
the record, not that Kafka stored it. `flush()` drives the callback in this short script, while the
callback supplies the broker acknowledgment or delivery error. A service should poll delivery
callbacks and flush during bounded shutdown rather than flush every record.

---

## 2. Commit only after the effect you are checkpointing

The example prints, then commits synchronously. Replace `print` with business processing and keep
the commit after success. This yields at-least-once processing: a crash after the effect but before
the commit repeats the event, so real effects need
[durable idempotency](../reliability/02_durable_consumer_effect_idempotency.md).

> **Production:** add authentication, contract validation, bounded polling, structured error
> handling, metrics, and lifecycle integration before putting this loop in a service.

---

## 3. Async frameworks do not make the native client async

`confluent-kafka` performs network I/O in native code but exposes polling and callbacks that need
deliberate lifecycle integration. Do not run an infinite consumer loop inside a FastAPI request.
Start a dedicated worker process or application-lifespan task, and ensure shutdown stops polling,
finishes bounded work, commits safe positions, and closes the consumer.

> **Key insight**: Kafka client calls often cross a local buffer before they cross the network, so
> API return values and delivery acknowledgment are different events.

---

## 4. What breaks, and when not to embed a consumer

⚠️ Exiting without draining delivery callbacks can lose records still buffered only in the producer
process. The tell is accepted application requests with no broker record and no delivery error log.

Do not embed a long-lived consumer in every web replica when web autoscaling should not change
consumer-group membership. Deploy a separate worker when scaling and failure domains differ.

---

**Next**: [Processing Loops, Backpressure, and Shutdown](03_processing_loops_backpressure_and_shutdown.md)
