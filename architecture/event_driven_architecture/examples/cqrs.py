"""Separate investigation write rules and dashboard reads in one local database."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import sqlite3
import sys
from collections.abc import Iterator


QUALIFYING_CONFIDENCE = 80
REQUIRED_SOURCES = 2


@dataclass(frozen=True)
class Evidence:
    source_id: str
    confidence: int

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("evidence requires a source id")
        if type(self.confidence) is not int or not 0 <= self.confidence <= 100:
            raise ValueError("confidence must be an integer from 0 to 100")


@dataclass
class Investigation:
    investigation_id: str
    title: str
    status: str
    version: int
    evidence: tuple[Evidence, ...]

    def complete(self) -> None:
        if self.status != "running":
            raise ValueError("only a running investigation can complete")
        if sum(item.confidence >= QUALIFYING_CONFIDENCE for item in self.evidence) < REQUIRED_SOURCES:
            raise ValueError("completion requires two sources with confidence >= 80")
        self.status = "completed"


@dataclass(frozen=True)
class InvestigationCard:
    investigation_id: str
    title: str
    status_label: str
    evidence_count: int
    qualified_count: int
    version: int


@contextmanager
def transaction(db: sqlite3.Connection) -> Iterator[None]:
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.execute("COMMIT")
    except BaseException:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise


def open_database() -> sqlite3.Connection:
    # Explicit SQL transactions; no reliance on implicit DB-API BEGIN behavior.
    options = {"autocommit": True} if sys.version_info >= (3, 12) else {}
    db = sqlite3.connect(":memory:", isolation_level=None, **options)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
        CREATE TABLE investigations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('running', 'completed')),
            version INTEGER NOT NULL CHECK (version >= 0)
        );
        CREATE TABLE evidence (
            investigation_id TEXT NOT NULL REFERENCES investigations(id),
            source_id TEXT NOT NULL,
            confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100),
            PRIMARY KEY (investigation_id, source_id)
        );
    """)
    with transaction(db):
        db.execute(
            "INSERT INTO investigations VALUES (?, ?, ?, ?)",
            ("I-42", "Investigate delayed shipments", "running", 0),
        )
        db.executemany(
            "INSERT INTO evidence VALUES (?, ?, ?)",
            [("I-42", "D-1", 90), ("I-42", "D-2", 50)],
        )
    return db


def load_investigation(db: sqlite3.Connection, investigation_id: str) -> Investigation:
    row = db.execute(
        "SELECT id, title, status, version FROM investigations WHERE id = ?",
        (investigation_id,),
    ).fetchone()
    if row is None:
        raise LookupError("investigation not found")
    evidence = tuple(
        Evidence(source_id, confidence)
        for source_id, confidence in db.execute(
            "SELECT source_id, confidence FROM evidence WHERE investigation_id = ?",
            (investigation_id,),
        )
    )
    return Investigation(*row, evidence=evidence)


def complete_investigation(db: sqlite3.Connection, investigation_id: str) -> None:
    with transaction(db):
        investigation = load_investigation(db, investigation_id)
        investigation.complete()
        changed = db.execute(
            """UPDATE investigations SET status = ?, version = version + 1
               WHERE id = ? AND version = ? AND status = 'running'""",
            (investigation.status, investigation_id, investigation.version),
        ).rowcount
        if changed != 1:
            raise RuntimeError("investigation changed; reload before deciding")


def add_evidence(
    db: sqlite3.Connection, investigation_id: str, evidence: Evidence
) -> None:
    with transaction(db):
        changed = db.execute(
            """UPDATE investigations SET version = version + 1
               WHERE id = ? AND status = 'running'""",
            (investigation_id,),
        ).rowcount
        if changed != 1:
            raise ValueError("evidence can be added only to a running investigation")
        db.execute(
            "INSERT INTO evidence VALUES (?, ?, ?)",
            (investigation_id, evidence.source_id, evidence.confidence),
        )


def get_card(db: sqlite3.Connection, investigation_id: str) -> InvestigationCard:
    row = db.execute(
        """SELECT i.id, i.title,
                  CASE i.status WHEN 'running' THEN 'In progress' ELSE 'Ready' END,
                  COUNT(e.source_id),
                  SUM(CASE WHEN e.confidence >= ? THEN 1 ELSE 0 END), i.version
           FROM investigations AS i
           LEFT JOIN evidence AS e ON e.investigation_id = i.id
           WHERE i.id = ?
           GROUP BY i.id, i.title, i.status, i.version""",
        (QUALIFYING_CONFIDENCE, investigation_id),
    ).fetchone()
    if row is None:
        raise LookupError("investigation not found")
    return InvestigationCard(*row)


def describe(card: InvestigationCard) -> str:
    return (
        f"{card.investigation_id} {card.status_label} "
        f"sources={card.evidence_count} qualified={card.qualified_count} "
        f"version={card.version}"
    )


def demo() -> None:
    db = open_database()
    try:
        initial = get_card(db, "I-42")
        print(describe(initial))
        try:
            complete_investigation(db, "I-42")
        except ValueError as error:
            print(f"rejected: {error}")
        else:
            raise AssertionError("two sources, only one qualified, cannot complete")
        assert get_card(db, "I-42") == initial
        add_evidence(db, "I-42", Evidence("D-3", 85))
        complete_investigation(db, "I-42")
        ready = get_card(db, "I-42")
        assert (ready.status_label, ready.evidence_count, ready.qualified_count) == (
            "Ready", 3, 2
        )
        assert ready.version == 2
        print(describe(ready))
        # A read DTO is a detached value, so the previously returned snapshot stays old.
        assert initial.status_label == "In progress"
        print(f"old_card={initial.status_label}; fresh_query={ready.status_label}")
    finally:
        db.close()


def exercise_probe() -> None:
    db = open_database()
    try:
        before = get_card(db, "I-42")
        try:
            add_evidence(db, "I-42", Evidence("D-1", 95))
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("duplicate evidence identity must be rejected")
        assert get_card(db, "I-42") == before
        add_evidence(db, "I-42", Evidence("D-3", 85))
        complete_investigation(db, "I-42")
        ready = get_card(db, "I-42")
        try:
            add_evidence(db, "I-42", Evidence("D-4", 99))
        except ValueError:
            pass
        else:
            raise AssertionError("completed evidence must remain closed")
        assert get_card(db, "I-42") == ready
        print("duplicate_rolled_back=True completed_write_rejected=True")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise", action="store_true")
    args = parser.parse_args()
    exercise_probe() if args.exercise else demo()
