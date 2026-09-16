from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from confluent_kafka import Consumer, Producer, TopicPartition


def main() -> int:
    source = os.environ["SOURCE_TOPIC"]
    output = os.environ["OUTPUT_TOPIC"]
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
    consumer.subscribe([source])
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            message = consumer.poll(0.25)
            if message is None:
                continue
            if message.error():
                raise RuntimeError(message.error())
            event = json.loads(message.value())
            producer.begin_transaction()
            producer.produce(
                output,
                key=message.key(),
                value=json.dumps(
                    {"event_id": event["event_id"], "status": "charged"},
                    separators=(",", ":"),
                ),
            )
            producer.flush(10)
            print(f"OUTPUT_STAGED event_id={event['event_id']}", flush=True)
            if not fault_marker.exists():
                fault_marker.touch()
                print(f"FAULT_REACHED event_id={event['event_id']}", flush=True)
                os._exit(86)
            producer.send_offsets_to_transaction(
                [TopicPartition(message.topic(), message.partition(), message.offset() + 1)],
                consumer.consumer_group_metadata(),
                10,
            )
            producer.commit_transaction(20)
            print(f"TRANSACTION_COMMITTED next_offset={message.offset() + 1}", flush=True)
            return 0
        raise TimeoutError("no input record within 30 seconds")
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
