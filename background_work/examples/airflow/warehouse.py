"""Local effect fixture: deterministic partition replacement in a SQLite file."""
from datetime import date
import os
import sqlite3


def upsert_daily_orders(partition):
    date.fromisoformat(partition)  # Reject arbitrary keys before binding SQL.
    with sqlite3.connect(os.environ["WAREHOUSE_DB"]) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS partitions (day text PRIMARY KEY, orders integer NOT NULL)")
        conn.execute("INSERT INTO partitions VALUES (?,42) ON CONFLICT(day) DO UPDATE SET orders=excluded.orders",(partition,))


def partition_is_valid(partition):
    with sqlite3.connect(os.environ["WAREHOUSE_DB"]) as conn:
        return conn.execute("SELECT orders FROM partitions WHERE day=?",(partition,)).fetchone()==(42,)
