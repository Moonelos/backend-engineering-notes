from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from confluent_kafka import Consumer, Producer, TopicPartition


def parse_due(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def main() -> int:
    retry_topic = os.environ["RETRY_TOPIC"]
    ready_topic = os.environ["READY_TOPIC"]
    group = os.environ["KAFKA_GROUP"]
    transactional_id = os.environ["TRANSACTIONAL_ID"]
    fault_marker = Path(os.environ["FAULT_MARKER"])
    consumer = Consumer(
        {
            "bootstrap.servers": "localhost:9092",
            "group.id": group,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            "isolation.level": "read_committed",
            "session.timeout.ms": 6000,
        }
    )
    producer = Producer(
        {
            "bootstrap.servers": "localhost:9092",
            "transactional.id": transactional_id,
            "transaction.timeout.ms": 10000,
        }
    )
    producer.init_transactions(20)
    consumer.subscribe([retry_topic])
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            message = consumer.poll(0.25)
            if message is None:
                continue
            if message.error():
                raise RuntimeError(message.error())
            envelope = json.loads(message.value())
            partition = TopicPartition(message.topic(), message.partition())
            due = parse_due(envelope["next_attempt_at"])
            remaining = (due - datetime.now(timezone.utc)).total_seconds()
            if remaining > 0:
                consumer.pause([partition])
                print(f"WAITING delay_ms={int(remaining * 1000)}", flush=True)
                while (remaining := (due - datetime.now(timezone.utc)).total_seconds()) > 0:
                    heartbeat = consumer.poll(min(0.25, remaining))
                    if heartbeat is not None and heartbeat.error():
                        raise RuntimeError(heartbeat.error())
                consumer.resume([partition])

            producer.begin_transaction()
            producer.produce(ready_topic, key=message.key(), value=message.value())
            producer.flush(10)
            print(f"RETRY_STAGED event_id={envelope['event_id']}", flush=True)
            if not fault_marker.exists():
                fault_marker.touch()
                print(f"FAULT_REACHED event_id={envelope['event_id']}", flush=True)
                os._exit(86)
            producer.send_offsets_to_transaction(
                [TopicPartition(message.topic(), message.partition(), message.offset() + 1)],
                consumer.consumer_group_metadata(),
                10,
            )
            producer.commit_transaction(20)
            print(f"RETRY_COMMITTED next_offset={message.offset() + 1}", flush=True)
            return 0
        raise TimeoutError("no retry record within 30 seconds")
    except BaseException:
        try:
            producer.abort_transaction(10)
        except Exception:
            pass
        raise
    finally:
        consumer.close()


if __name__ == "__main__":
    sys.exit(main())
