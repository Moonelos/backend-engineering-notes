from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid

import pytest
from confluent_kafka import Consumer, Producer, TopicPartition

from tests.conftest import wait_for_delivery


pytestmark = pytest.mark.integration


def test_restart_resolves_open_transaction_and_commits_once(topic_factory, tmp_path):
    source = topic_factory("notes-tx-input")
    output = topic_factory("notes-tx-output")
    group = f"notes-tx-{uuid.uuid4().hex}"
    producer = Producer({"bootstrap.servers": "localhost:9092"})
    producer.produce(source, key="ord-42", value=json.dumps({"event_id": "evt-101"}))
    wait_for_delivery(producer)
    env = os.environ | {
        "SOURCE_TOPIC": source,
        "OUTPUT_TOPIC": output,
        "KAFKA_GROUP": group,
        "TRANSACTIONAL_ID": f"billing-{uuid.uuid4().hex}",
        "FAULT_MARKER": str(tmp_path / "faulted"),
    }
    first = subprocess.run(
        [sys.executable, "-m", "kafka_notes.transaction_worker"],
        env=env,
        text=True,
        capture_output=True,
        timeout=50,
    )
    assert first.returncode == 86
    assert "OUTPUT_STAGED event_id=evt-101" in first.stdout
    second = subprocess.run(
        [sys.executable, "-m", "kafka_notes.transaction_worker"],
        env=env,
        text=True,
        capture_output=True,
        timeout=50,
    )
    assert second.returncode == 0, second.stderr
    assert "TRANSACTION_COMMITTED next_offset=1" in second.stdout
    position_reader = Consumer({"bootstrap.servers": "localhost:9092", "group.id": group})
    try:
        assert position_reader.committed([TopicPartition(source, 0)], timeout=10)[0].offset == 1
    finally:
        position_reader.close()
    consumer = Consumer(
        {
            "bootstrap.servers": "localhost:9092",
            "group.id": f"notes-output-{uuid.uuid4().hex}",
            "auto.offset.reset": "earliest",
            "isolation.level": "read_committed",
        }
    )
    consumer.subscribe([output])
    seen = []
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            message = consumer.poll(0.25)
            if message is not None and not message.error():
                seen.append(json.loads(message.value()))
                if len(seen) > 1:
                    break
    finally:
        consumer.close()
    assert seen == [{"event_id": "evt-101", "status": "charged"}]
