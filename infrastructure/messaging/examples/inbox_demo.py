"""Local atomic inbox/effect demonstration; no network or persistent files."""
import sqlite3

conn = sqlite3.connect(":memory:")
conn.executescript("""
CREATE TABLE inbox (consumer TEXT, event_id TEXT, PRIMARY KEY (consumer, event_id));
CREATE TABLE results (document_id INTEGER PRIMARY KEY, status TEXT NOT NULL);
""")

def apply(event_id: str, document_id: int, fail: bool = False) -> str:
    with conn:
        inserted = conn.execute(
            "INSERT OR IGNORE INTO inbox VALUES (?, ?)", ("search-v1", event_id)
        ).rowcount
        if not inserted:
            return "duplicate"
        if fail:
            raise RuntimeError("simulated effect failure")
        conn.execute(
            "INSERT INTO results VALUES (?, 'ready') ON CONFLICT(document_id) "
            "DO UPDATE SET status = excluded.status", (document_id,)
        )
    return "applied"

first = apply("e42", 42)
second = apply("e42", 42)
try:
    apply("e43", 42, fail=True)
except RuntimeError:
    pass
assert conn.execute("SELECT count(*) FROM inbox WHERE event_id='e43'").fetchone()[0] == 0
retry = apply("e43", 42)
status, count = conn.execute("SELECT status, count(*) FROM results").fetchone()
assert (first, second, retry, status, count) == ("applied", "duplicate", "applied", "ready", 1)
print(first, second, retry, f"result={status}", f"count={count}")
conn.close()
