import sqlite3


def initialize(path: str) -> None:
    with sqlite3.connect(path) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS effects (
                   event_id TEXT PRIMARY KEY,
                   result TEXT NOT NULL
               )"""
        )


def apply_once(path: str, event_id: str, result: str) -> tuple[str, bool]:
    """Return (durable result, created_now) for one stable event identity."""
    with sqlite3.connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT result FROM effects WHERE event_id = ?", (event_id,)
        ).fetchone()
        if existing is not None:
            return str(existing[0]), False
        db.execute(
            "INSERT INTO effects(event_id, result) VALUES (?, ?)",
            (event_id, result),
        )
        return result, True
