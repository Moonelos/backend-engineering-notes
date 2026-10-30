"""SQLite durable pending inbox; a separate worker polls pending rows."""
import hashlib
import sqlite3


def initialize(path):
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS inbox (provider TEXT, event_id TEXT, "
                           "digest TEXT NOT NULL, body BLOB NOT NULL, state TEXT NOT NULL, "
                           "PRIMARY KEY(provider,event_id))")


def admit(path, provider, event_id, raw_body, *, before_commit=lambda: None):
    body_hash = hashlib.sha256(raw_body).hexdigest()
    with sqlite3.connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute("SELECT digest FROM inbox WHERE provider=? AND event_id=?",
                                      (provider, event_id)).fetchone()
        if existing:
            if existing[0] != body_hash:
                raise ValueError("authenticated event ID reused with different body")
            return False
        connection.execute("INSERT INTO inbox VALUES (?, ?, ?, ?, 'pending')",
                           (provider, event_id, body_hash, raw_body))
        before_commit()
    # Returning true means commit succeeded. No enqueue gap exists: this row is work.
    return True
