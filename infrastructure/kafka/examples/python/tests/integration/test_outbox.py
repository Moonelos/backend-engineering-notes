from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid

import psycopg
import pytest
from confluent_kafka import Consumer, Producer
from psycopg import sql

from kafka_notes.effect_store import apply_once, initialize
from tests.conftest import wait_for_delivery


pytestmark = pytest.mark.integration


class SimulatedRelayCrash(RuntimeError):
    pass


def create_order(conn, schema: str, event_id: str, *, fail_between_rows: bool = False):
    with conn.transaction():
        conn.execute(
            sql.SQL("INSERT INTO {}.orders(order_id, total_minor) VALUES (%s, %s)").format(
                sql.Identifier(schema)
            ),
            ("ord-42", 2590),
        )
        if fail_between_rows:
            raise RuntimeError("simulated failure between domain and outbox inserts")
        conn.execute(
            sql.SQL(
                """INSERT INTO {}.outbox_events
                   (event_id, aggregate_id, event_type, payload)
                   VALUES (%s, %s, %s, %s::jsonb)"""
            ).format(sql.Identifier(schema)),
            (
                event_id,
                "ord-42",
                "order.created",
                json.dumps({"event_id": event_id, "order_id": "ord-42"}),
            ),
        )


def relay_one(conn, schema: str, topic: str, *, crash_after_ack: bool) -> str:
    with conn.transaction():
        row = conn.execute(
            sql.SQL(
                """SELECT event_id, aggregate_id, payload
                   FROM {}.outbox_events
                   WHERE published_at IS NULL
                   ORDER BY created_at
                   FOR UPDATE SKIP LOCKED
                   LIMIT 1"""
            ).format(sql.Identifier(schema))
        ).fetchone()
        assert row is not None
        event_id, aggregate_id, payload = row
        producer = Producer({"bootstrap.servers": "localhost:9092"})
        producer.produce(topic, key=aggregate_id, value=json.dumps(payload))
        wait_for_delivery(producer)
        if crash_after_ack:
            raise SimulatedRelayCrash(event_id)
        conn.execute(
            sql.SQL("UPDATE {}.outbox_events SET published_at=now() WHERE event_id=%s").format(
                sql.Identifier(schema)
            ),
            (event_id,),
        )
        return str(event_id)


def test_polling_outbox_recovers_acknowledgment_crash(topic_factory, tmp_path):
    dsn = os.getenv("OUTBOX_DSN", "postgresql://postgres:postgres@localhost:55439/postgres")
    schema = f"notes_{uuid.uuid4().hex[:10]}"
    topic = topic_factory("notes-outbox")
    event_id = str(uuid.uuid4())
    conn = psycopg.connect(dsn)
    try:
        with conn.transaction():
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
            conn.execute(
                sql.SQL(
                    """CREATE TABLE {}.orders (
                           order_id text PRIMARY KEY,
                           total_minor bigint NOT NULL CHECK (total_minor >= 0)
                       );
                       CREATE TABLE {}.outbox_events (
                           event_id uuid PRIMARY KEY,
                           aggregate_id text NOT NULL,
                           event_type text NOT NULL,
                           payload jsonb NOT NULL,
                           created_at timestamptz NOT NULL DEFAULT now(),
                           published_at timestamptz
                       )"""
                ).format(sql.Identifier(schema), sql.Identifier(schema))
            )

        with pytest.raises(RuntimeError, match="between domain and outbox"):
            create_order(conn, schema, str(uuid.uuid4()), fail_between_rows=True)
        assert conn.execute(
            sql.SQL("SELECT count(*) FROM {}.orders").format(sql.Identifier(schema))
        ).fetchone() == (0,)

        create_order(conn, schema, event_id)
        counts = conn.execute(
            sql.SQL(
                """SELECT
                       (SELECT count(*) FROM {}.orders),
                       (SELECT count(*) FROM {}.outbox_events)"""
            ).format(sql.Identifier(schema), sql.Identifier(schema))
        ).fetchone()
        assert counts == (1, 1)

        with pytest.raises(SimulatedRelayCrash):
            relay_one(conn, schema, topic, crash_after_ack=True)
        assert conn.execute(
            sql.SQL("SELECT published_at IS NULL FROM {}.outbox_events").format(
                sql.Identifier(schema)
            )
        ).fetchone() == (True,)
        assert relay_one(conn, schema, topic, crash_after_ack=False) == event_id

        consumer = Consumer(
            {
                "bootstrap.servers": "localhost:9092",
                "group.id": f"notes-outbox-{uuid.uuid4().hex}",
                "auto.offset.reset": "earliest",
            }
        )
        consumer.subscribe([topic])
        records = []
        deadline = time.monotonic() + 10
        try:
            while len(records) < 2 and time.monotonic() < deadline:
                message = consumer.poll(0.25)
                if message is not None and not message.error():
                    records.append((message.key().decode(), json.loads(message.value())))
        finally:
            consumer.close()
        assert [key for key, _ in records] == ["ord-42", "ord-42"]
        assert [record["event_id"] for _, record in records] == [event_id, event_id]

        effect_db = str(tmp_path / "effects.sqlite")
        initialize(effect_db)
        assert apply_once(effect_db, event_id, "charged:ord-42")[1] is True
        assert apply_once(effect_db, event_id, "charged:ord-42")[1] is False
        with sqlite3.connect(effect_db) as effect_conn:
            assert effect_conn.execute("SELECT count(*) FROM effects").fetchone() == (1,)
    finally:
        conn.rollback()
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        conn.commit()
        conn.close()
