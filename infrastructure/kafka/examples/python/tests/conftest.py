from __future__ import annotations

import time
import uuid

import pytest
from confluent_kafka.admin import AdminClient, NewTopic


@pytest.fixture
def topic_factory():
    created: list[str] = []

    def create(prefix: str) -> str:
        topic = f"{prefix}-{uuid.uuid4().hex[:10]}"
        admin = AdminClient({"bootstrap.servers": "localhost:9092"})
        future = admin.create_topics(
            [NewTopic(topic, num_partitions=1, replication_factor=1)]
        )[topic]
        future.result(15)
        created.append(topic)
        return topic

    return create


def wait_for_delivery(producer, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while producer.flush(0.1) and time.monotonic() < deadline:
        pass
    if producer.flush(0) != 0:
        raise TimeoutError("producer did not receive broker acknowledgment")
