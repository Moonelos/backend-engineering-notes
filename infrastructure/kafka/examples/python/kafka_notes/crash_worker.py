from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from confluent_kafka import Consumer

from kafka_notes.effect_store import apply_once, initialize


def main() -> int:
    topic = os.environ["KAFKA_TOPIC"]
    group = os.environ["KAFKA_GROUP"]
    store = os.environ["EFFECT_DB"]
    fault_marker = Path(os.environ["FAULT_MARKER"])
    fault_stage = os.getenv("FAULT_STAGE", "after_effect")
    initialize(store)
    consumer = Consumer(
        {
            "bootstrap.servers": "localhost:9092",
            "group.id": group,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
            "session.timeout.ms": 6000,
        }
    )
    consumer.subscribe([topic])
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            message = consumer.poll(0.25)
            if message is None:
                continue
            if message.error():
                raise RuntimeError(message.error())
            event = json.loads(message.value())
            if fault_stage == "before_effect" and not fault_marker.exists():
                fault_marker.touch()
                print(f"FAULT_REACHED stage=before_effect event_id={event['event_id']}", flush=True)
                os._exit(86)
            result, created = apply_once(
                store, event["event_id"], f"charged:{event['order_id']}"
            )
            print(
                f"EFFECT event_id={event['event_id']} created={str(created).lower()} result={result}",
                flush=True,
            )
            if fault_stage == "after_effect" and not fault_marker.exists():
                fault_marker.touch()
                print(f"FAULT_REACHED stage=after_effect event_id={event['event_id']}", flush=True)
                os._exit(86)
            consumer.commit(message=message, asynchronous=False)
            print(f"COMMITTED next_offset={message.offset() + 1}", flush=True)
            if fault_stage == "after_commit" and not fault_marker.exists():
                fault_marker.touch()
                print(f"FAULT_REACHED stage=after_commit event_id={event['event_id']}", flush=True)
                os._exit(86)
            return 0
        raise TimeoutError("no input record within 30 seconds")
    finally:
        consumer.close()


if __name__ == "__main__":
    sys.exit(main())
