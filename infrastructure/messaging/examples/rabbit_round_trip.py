"""Disposable localhost RabbitMQ 4.x + Pika 1.x round trip."""
import json
import os
import sqlite3
import pika

connection = pika.BlockingConnection(pika.ConnectionParameters(
    "127.0.0.1", port=int(os.environ.get("RABBITMQ_PORT", "5672")), heartbeat=30,
))
try:
    channel = connection.channel()
    queue = "notes.documents.parse"
    channel.queue_declare(queue=queue, durable=True, arguments={"x-queue-type": "quorum"})
    channel.confirm_delivery()
    channel.basic_publish(
        exchange="", routing_key=queue, mandatory=True,
        body=json.dumps({"event_id": "e42", "tenant_id": 7, "document_id": 42}),
        properties=pika.BasicProperties(content_type="application/json", delivery_mode=2, message_id="e42"),
    )
    print("confirmed e42")
    method, properties, body = channel.basic_get(queue=queue, auto_ack=False)
    if method is None:
        raise RuntimeError("No delivery available; check for another consumer")
    payload = json.loads(body)
    if payload != {"event_id": "e42", "tenant_id": 7, "document_id": 42}:
        raise ValueError("Unexpected lab envelope; leaving delivery unacknowledged")
    db = sqlite3.connect(":memory:")
    try:
        db.executescript("CREATE TABLE inbox (event_id TEXT PRIMARY KEY); CREATE TABLE results (tenant_id INT, document_id INT, PRIMARY KEY(tenant_id, document_id));")
        with db:
            inserted = db.execute("INSERT OR IGNORE INTO inbox VALUES (?)", (payload["event_id"],)).rowcount
            if inserted:
                db.execute("INSERT INTO results VALUES (?, ?)", (payload["tenant_id"], payload["document_id"]))
        channel.basic_ack(delivery_tag=method.delivery_tag)
        print("effect committed; delivery acknowledged")
    finally:
        db.close()
finally:
    connection.close()
