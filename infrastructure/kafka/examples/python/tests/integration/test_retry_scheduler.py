from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from confluent_kafka import Consumer, Producer, TopicPartition

from tests.conftest import wait_for_delivery


pytestmark = pytest.mark.integration


def test_scheduler_waits_and_handoff_survives_process_death(topic_factory, tmp_path):
    retry_topic = topic_factory("notes-retry")
    ready_topic = topic_factory("notes-ready")
    group = f"notes-retry-{uuid.uuid4().hex}"
    due = datetime.now(timezone.utc) + timedelta(seconds=8)
    envelope = {
        "event_id": "evt-101",
        "source": {"topic": "orders", "partition": 2, "offset": 8},
        "attempt": 1,
        "next_attempt_at": due.isoformat().replace("+00:00", "Z"),
    }
    producer = Producer({"bootstrap.servers": "localhost:9092"})
    producer.produce(retry_topic, key="ord-42", value=json.dumps(envelope))
    wait_for_delivery(producer)
    env = os.environ | {
        "RETRY_TOPIC": retry_topic,
        "READY_TOPIC": ready_topic,
        "KAFKA_GROUP": group,
        "TRANSACTIONAL_ID": f"retry-scheduler-{uuid.uuid4().hex}",
        "FAULT_MARKER": str(tmp_path / "faulted"),
    }
    started = time.monotonic()
    first = subprocess.run(
        [sys.executable, "-m", "kafka_notes.retry_scheduler"],
        env=env,
        text=True,
        capture_output=True,
        timeout=50,
    )
    assert first.returncode == 86
    assert "WAITING delay_ms=" in first.stdout
    assert "FAULT_REACHED event_id=evt-101" in first.stdout
    assert time.monotonic() - started >= 6
    second = subprocess.run(
        [sys.executable, "-m", "kafka_notes.retry_scheduler"],
        env=env,
        text=True,
        capture_output=True,
        timeout=50,
    )
    assert second.returncode == 0, second.stderr
    assert "RETRY_COMMITTED next_offset=1" in second.stdout

    position_reader = Consumer({"bootstrap.servers": "localhost:9092", "group.id": group})
    try:
        assert position_reader.committed([TopicPartition(retry_topic, 0)], timeout=10)[0].offset == 1
    finally:
        position_reader.close()

    consumer = Consumer(
        {
            "bootstrap.servers": "localhost:9092",
            "group.id": f"notes-ready-{uuid.uuid4().hex}",
            "auto.offset.reset": "earliest",
            "isolation.level": "read_committed",
        }
    )
    consumer.subscribe([ready_topic])
    seen = []
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            message = consumer.poll(0.25)
            if message is not None and not message.error():
                seen.append((message.key().decode(), json.loads(message.value())))
                if len(seen) > 1:
                    break
    finally:
        consumer.close()
    assert seen == [("ord-42", envelope)]
