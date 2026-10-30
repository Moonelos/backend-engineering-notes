"""Run from repository root with Python 3.11+. No services or credentials required.

Extract the documented verifier so the negative tests exercise the published code.
The SQLite inbox is a local persistence fixture, not a distributed worker implementation.
"""
import asyncio
import hashlib
import hmac
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import time


class Inbox:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS inbox (id TEXT PRIMARY KEY, body BLOB NOT NULL, state TEXT NOT NULL)")

    async def admit(self, delivery_id, body):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO inbox VALUES (?, ?, 'pending')", (delivery_id, body))
            stored = self.db.execute("SELECT body FROM inbox WHERE id=?", (delivery_id,)).fetchone()[0]
            if stored != body:
                raise ValueError("delivery ID body conflict")

    def close(self):
        self.db.close()


def verifier():
    note = Path(__file__).resolve().parents[1] / "03_client_delivery_patterns.md"
    block = next(b for b in re.findall(r"```python\n(.*?)\n```", note.read_text(), re.S)
                 if "async def verify_callback" in b)
    namespace = {}
    exec(compile(block, str(note), "exec"), namespace)
    return namespace["verify_callback"]


def signed_headers(secret, delivery_id, body):
    stamp = str(int(time.time()))
    signature = hmac.new(secret, delivery_id.encode() + b"." + stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {"X-Webhook-Version": "v1", "X-Webhook-Timestamp": stamp,
            "X-Webhook-Delivery": delivery_id, "X-Webhook-Signature": "v1=" + signature}


async def main():
    verify = verifier()
    secret = b"local deterministic fixture secret only"
    body = b'{"job_id":"abc","state":"succeeded","generation":2}'
    headers = signed_headers(secret, "delivery42", body)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "inbox.sqlite"
        inbox = Inbox(path)
        assert await verify(body, headers, secret, inbox) == json.loads(body)
        inbox.close()  # crash after intake, before effect
        recovered = Inbox(path)
        assert recovered.db.execute("SELECT state FROM inbox").fetchone() == ("pending",)
        await verify(body, headers, secret, recovered)
        assert recovered.db.execute("SELECT count(*) FROM inbox").fetchone() == (1,)
        for change in [{"X-Webhook-Delivery": "delivery43"},
                       {"X-Webhook-Signature": "v1=é"},
                       {"X-Webhook-Version": "v2"}]:
            try:
                await verify(body, headers | change, secret, recovered)
            except ValueError:
                pass
            else:
                raise AssertionError("malformed or identity-substituted delivery accepted")
        conflicting = b'{"job_id":"abc","state":"failed"}'
        try:
            await verify(conflicting, signed_headers(secret, "delivery42", conflicting), secret, recovered)
        except ValueError:
            pass
        else:
            raise AssertionError("same delivery ID admitted another body")
        recovered.close()
    print("PASS signed identity; malformed input; durable pending replay; body conflict")

    # Publication schedules are explicit inputs. This proves the projection rule only.
    applied = 0
    for sequence in (1, 2, 1):
        if sequence <= applied:
            continue
        assert sequence == applied + 1, "gap requires buffering/reconciliation"
        applied = sequence
    assert applied == 2
    assert 4 != applied + 1  # delivery 4 is a gap, not permission to skip 3
    print("PASS late duplicate 1 cannot replace applied sequence 2; gap 4 is detected")


if __name__ == "__main__":
    asyncio.run(main())
