import sqlite3
from dataclasses import dataclass

from modular_app.conversations._schema import SCHEMA


class MissingConversation(Exception):
    pass


@dataclass(frozen=True)
class Answer:
    tenant: str
    request_id: str
    conversation_id: str
    prompt: str
    text: str


def install_schema(connection: sqlite3.Connection) -> None:
    """Bootstrap-only, fresh-database schema; not a migration runner."""
    connection.executescript(SCHEMA)


class Conversations:
    """Transaction-scoped facade; never commits on its own."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(self, tenant: str, conversation_id: str) -> None:
        self._connection.execute(
            "INSERT INTO conversations (tenant, conversation_id) VALUES (?, ?)",
            (tenant, conversation_id),
        )

    def require(self, tenant: str, conversation_id: str) -> None:
        row = self._connection.execute(
            "SELECT 1 FROM conversations WHERE tenant = ? AND conversation_id = ?",
            (tenant, conversation_id),
        ).fetchone()
        if row is None:
            raise MissingConversation("conversation unavailable")

    def find_answer(self, tenant: str, request_id: str) -> Answer | None:
        row = self._connection.execute(
            "SELECT tenant, request_id, conversation_id, prompt, answer "
            "FROM answers WHERE tenant = ? AND request_id = ?",
            (tenant, request_id),
        ).fetchone()
        return Answer(*row) if row else None

    def append(self, answer: Answer) -> None:
        self.require(answer.tenant, answer.conversation_id)
        self._connection.execute(
            "INSERT INTO answers (tenant, request_id, conversation_id, prompt, answer) "
            "VALUES (?, ?, ?, ?, ?)",
            (answer.tenant, answer.request_id, answer.conversation_id,
             answer.prompt, answer.text),
        )
