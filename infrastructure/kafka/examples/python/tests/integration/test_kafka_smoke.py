import json
import time
import uuid

import pytest
from confluent_kafka import Consumer, Producer

from tests.conftest import wait_for_delivery


pytestmark = pytest.mark.integration


def test_real_broker_round_trip(topic_factory):
    topic = topic_factory("notes-smoke")
    payload = {"event_id": "evt-101", "order_id": "ord-42"}
    producer = Producer({"bootstrap.servers": "localhost:9092"})
    producer.produce(topic, key="ord-42", value=json.dumps(payload))
    wait_for_delivery(producer)
    consumer = Consumer(
        {
            "bootstrap.servers": "localhost:9092",
            "group.id": f"notes-smoke-{uuid.uuid4().hex}",
            "auto.offset.reset": "earliest",
        }
    )
    consumer.subscribe([topic])
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            message = consumer.poll(0.25)
            if message is None:
                continue
            if message.error():
                raise RuntimeError(message.error())
            assert message.key() == b"ord-42"
            assert json.loads(message.value()) == payload
            assert (message.partition(), message.offset()) == (0, 0)
            return
        pytest.fail("record not consumed within 10 seconds")
    finally:
        consumer.close()
