from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import uuid

import pytest
from confluent_kafka import Consumer, Producer, TopicPartition

from tests.conftest import wait_for_delivery


pytestmark = pytest.mark.integration


def committed_offset(group: str, topic: str) -> int:
    consumer = Consumer({"bootstrap.servers": "localhost:9092", "group.id": group})
    try:
        return consumer.committed([TopicPartition(topic, 0)], timeout=10)[0].offset
    finally:
        consumer.close()


@pytest.mark.parametrize("stage", ["before_effect", "after_effect", "after_commit"])
def test_effect_survives_process_death_without_duplication(topic_factory, tmp_path, stage):
    topic = topic_factory("notes-crash")
    group = f"notes-crash-{uuid.uuid4().hex}"
    producer = Producer({"bootstrap.servers": "localhost:9092"})
    producer.produce(
        topic,
        key="ord-42",
        value=json.dumps({"event_id": "evt-101", "order_id": "ord-42"}),
    )
    wait_for_delivery(producer)
    env = os.environ | {
        "KAFKA_TOPIC": topic,
        "KAFKA_GROUP": group,
        "EFFECT_DB": str(tmp_path / "effects.sqlite"),
        "FAULT_MARKER": str(tmp_path / "faulted"),
        "FAULT_STAGE": stage,
    }
    first = subprocess.run(
        [sys.executable, "-m", "kafka_notes.crash_worker"],
        env=env,
        text=True,
        capture_output=True,
        timeout=40,
    )
    assert first.returncode == 86
    assert f"FAULT_REACHED stage={stage} event_id=evt-101" in first.stdout
    if stage != "after_commit":
        second = subprocess.run(
            [sys.executable, "-m", "kafka_notes.crash_worker"],
            env=env,
            text=True,
            capture_output=True,
            timeout=40,
        )
        assert second.returncode == 0, second.stderr
        assert ("created=false" in second.stdout) is (stage == "after_effect")
        assert "COMMITTED next_offset=1" in second.stdout
    assert committed_offset(group, topic) == 1
    with sqlite3.connect(env["EFFECT_DB"]) as db:
        assert db.execute("SELECT count(*) FROM effects WHERE event_id='evt-101'").fetchone() == (1,)
