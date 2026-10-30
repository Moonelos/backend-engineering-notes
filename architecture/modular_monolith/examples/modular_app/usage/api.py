import sqlite3

from modular_app.usage._schema import SCHEMA


def install_schema(connection: sqlite3.Connection) -> None:
    """Bootstrap-only; the usage module owns this schema."""
    connection.executescript(SCHEMA)


class Usage:
    """Records accepted-answer units within the caller's transaction."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def record_answer(self, tenant: str, request_id: str) -> None:
        self._connection.execute(
            "INSERT INTO accepted_answers (tenant, request_id, units) VALUES (?, ?, 1)",
            (tenant, request_id),
        )

    def total(self, tenant: str) -> int:
        return self._connection.execute(
            "SELECT COALESCE(SUM(units), 0) FROM accepted_answers WHERE tenant = ?",
            (tenant,),
        ).fetchone()[0]
