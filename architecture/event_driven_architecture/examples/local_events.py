"""Local callbacks demonstrate coupling and failure; they provide no persistence."""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class InvestigationCompleted:
    investigation_id: str
    version: int
    evidence_count: int


@dataclass
class Investigation:
    investigation_id: str
    evidence_count: int
    status: str = "running"
    version: int = 0

    def complete(self) -> InvestigationCompleted:
        if self.status != "running":
            raise ValueError("only a running investigation can complete")
        if self.evidence_count < 1:
            raise ValueError("completion requires evidence")
        self.status = "completed"
        self.version += 1
        return InvestigationCompleted(
            self.investigation_id, self.version, self.evidence_count
        )


Handler = Callable[[InvestigationCompleted], None]


def dispatch(event: InvestigationCompleted, handlers: tuple[Handler, ...]) -> None:
    """Run callbacks in declared order; propagate the first failure."""
    for handler in handlers:
        handler(event)


def baseline() -> None:
    audit: list[tuple[str, int]] = []
    summaries: dict[str, int] = {}

    def record_audit(event: InvestigationCompleted) -> None:
        audit.append((event.investigation_id, event.version))

    def update_summary(event: InvestigationCompleted) -> None:
        summaries[event.investigation_id] = event.evidence_count

    investigation = Investigation("I-42", evidence_count=2)
    event = investigation.complete()
    dispatch(event, (record_audit, update_summary))
    assert investigation.status == "completed"
    assert audit == [("I-42", 1)]
    assert summaries == {"I-42": 2}
    print("I-42 completed version=1 audit=1 summary=2")


def failure_probe() -> None:
    audit: list[tuple[str, int]] = []
    summaries: dict[str, int] = {}

    def record_audit(event: InvestigationCompleted) -> None:
        audit.append((event.investigation_id, event.version))

    def fail_notification(event: InvestigationCompleted) -> None:
        raise RuntimeError("notification unavailable")

    def update_summary(event: InvestigationCompleted) -> None:
        summaries[event.investigation_id] = event.evidence_count

    investigation = Investigation("I-42", evidence_count=2)
    event = investigation.complete()
    handlers = (record_audit, fail_notification, update_summary)
    for attempt in (1, 2):
        try:
            dispatch(event, handlers)
        except RuntimeError as error:
            assert str(error) == "notification unavailable"
        else:
            raise AssertionError("the failing handler must propagate")
        assert len(audit) == attempt
        assert summaries == {}
        assert investigation.status == "completed"
        print(
            f"attempt={attempt} completed=True audit={len(audit)} "
            f"summary=False error=notification unavailable"
        )
    try:
        investigation.complete()
    except ValueError as error:
        assert str(error) == "only a running investigation can complete"
    else:
        raise AssertionError("completion itself must not be repeated")


def dispatch_collecting_failures(
    event: InvestigationCompleted, handlers: tuple[Handler, ...]
) -> list[tuple[str, Exception]]:
    """An explicit alternative policy for independent local callbacks."""
    failures: list[tuple[str, Exception]] = []
    for handler in handlers:
        try:
            handler(event)
        except Exception as error:
            failures.append((handler.__name__, error))
    return failures


def exercise_probe() -> None:
    calls: list[str] = []

    def audit(event: InvestigationCompleted) -> None:
        calls.append("audit")

    def notify(event: InvestigationCompleted) -> None:
        raise RuntimeError("notification unavailable")

    def summary(event: InvestigationCompleted) -> None:
        calls.append("summary")

    failures = dispatch_collecting_failures(
        Investigation("I-42", evidence_count=2).complete(), (audit, notify, summary)
    )
    assert calls == ["audit", "summary"]
    assert len(failures) == 1 and failures[0][0] == "notify"
    assert isinstance(failures[0][1], RuntimeError)
    print("continued=audit,summary failed=notify retry_record=False")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--failure", action="store_true")
    mode.add_argument("--exercise", action="store_true")
    args = parser.parse_args()
    if args.failure:
        failure_probe()
    elif args.exercise:
        exercise_probe()
    else:
        baseline()
