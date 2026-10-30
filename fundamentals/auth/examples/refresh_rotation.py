"""Local SQLite demonstration of strict refresh-token reuse policy; no HTTP server."""
import hashlib
import secrets
import sqlite3
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier


class InvalidToken(Exception):
    pass


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def rotate(path, raw_token):
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    successor = None
    try:
        # SQLite's write lock serializes the demonstration. In PostgreSQL lock the
        # family row, then read/consume the token in that SAME transaction.
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT t.family, t.used, f.revoked, f.expires FROM tokens t "
            "JOIN families f ON f.id=t.family WHERE t.hash=?", (digest(raw_token),)
        ).fetchone()
        if row and not row[2] and row[3] > time.time():
            family, used, _, _ = row
            if used:
                connection.execute("UPDATE families SET revoked=1 WHERE id=?", (family,))
            else:
                successor = secrets.token_urlsafe(48)
                connection.execute("UPDATE tokens SET used=1 WHERE hash=?", (digest(raw_token),))
                connection.execute("INSERT INTO tokens VALUES (?, ?, 0)", (digest(successor), family))
        # Commit reuse revocation BEFORE raising; exception-driven rollback must
        # not resurrect the compromised family.
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
    if successor is None:
        raise InvalidToken("invalid, expired, or reused refresh token")
    return successor


def main():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "refresh.sqlite"
        original = secrets.token_urlsafe(48)
        with sqlite3.connect(path) as connection:
            connection.executescript(
                "CREATE TABLE families(id TEXT PRIMARY KEY, revoked INTEGER, expires REAL);"
                "CREATE TABLE tokens(hash TEXT PRIMARY KEY, family TEXT, used INTEGER);"
            )
            connection.execute("INSERT INTO families VALUES ('f1', 0, ?)", (time.time() + 3600,))
            connection.execute("INSERT INTO tokens VALUES (?, 'f1', 0)", (digest(original),))
        barrier = Barrier(2)

        def contender():
            barrier.wait()
            try:
                return rotate(path, original)
            except InvalidToken:
                return None

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: contender(), range(2)))
        assert sum(value is not None for value in results) == 1
        winner = next(value for value in results if value is not None)
        try:
            rotate(path, winner)
        except InvalidToken:
            pass
        else:
            raise AssertionError("reuse revocation did not survive transaction commit")
        with sqlite3.connect(path) as connection:
            assert connection.execute("SELECT count(*) FROM tokens").fetchone()[0] == 2
            assert connection.execute("SELECT revoked FROM families").fetchone()[0] == 1
        print("PASS: one concurrent successor; reuse revocation persists; successor rejected")


if __name__ == "__main__":
    main()
