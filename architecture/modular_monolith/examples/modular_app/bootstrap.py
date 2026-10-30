import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from modular_app.conversations.api import Conversations, install_schema as install_conversations
from modular_app.usage.api import Usage, install_schema as install_usage
from modular_app.workflows.answer import WriteModules


class Database:
    """Composition root for a local SQLite demo; one connection per transaction."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        connection = self.connect()
        try:
            install_conversations(connection)
            install_usage(connection)
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[WriteModules]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield WriteModules(Conversations(connection), Usage(connection))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
