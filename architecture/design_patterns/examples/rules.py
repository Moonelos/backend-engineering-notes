"""Pure review specifications, table transitions, and an equivalent State-object alternative."""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from typing import NoReturn


@dataclass(frozen=True)
class ReviewFacts:
    evidence_ids: tuple[str, ...]
    confidence: int

    def __post_init__(self) -> None:
        if type(self.confidence) is not int or not 0 <= self.confidence <= 100:
            raise ValueError("confidence must be an integer between 0 and 100")


Rule = Callable[[ReviewFacts], bool]


def has_evidence(facts: ReviewFacts) -> bool:
    return bool(facts.evidence_ids)


@dataclass(frozen=True)
class ConfidenceAtLeast:
    minimum: int

    def __post_init__(self) -> None:
        if type(self.minimum) is not int or not 0 <= self.minimum <= 100:
            raise ValueError("minimum must be an integer between 0 and 100")

    def __call__(self, facts: ReviewFacts) -> bool:
        return facts.confidence >= self.minimum


@dataclass(frozen=True)
class AllOf:
    rules: tuple[Rule, ...]

    def __call__(self, facts: ReviewFacts) -> bool:
        return all(rule(facts) for rule in self.rules)


class Status(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class Event(Enum):
    START = "start"
    COMPLETE = "complete"
    CANCEL = "cancel"


class TransitionRejected(ValueError):
    pass


@dataclass(frozen=True)
class Investigation:
    investigation_id: str
    status: Status
    facts: ReviewFacts


TARGETS = {
    (Status.PENDING, Event.START): Status.RUNNING,
    (Status.PENDING, Event.CANCEL): Status.CANCELLED,
    (Status.RUNNING, Event.COMPLETE): Status.COMPLETED,
    (Status.RUNNING, Event.CANCEL): Status.CANCELLED,
}


def reject(status: Status, event: Event) -> NoReturn:
    raise TransitionRejected(f"{event.value} is illegal from {status.value}")


def require_completion(facts: ReviewFacts, rule: Rule) -> None:
    if not rule(facts):
        raise TransitionRejected("completion requirements not satisfied")


def transition(current: Investigation, event: Event, *, rule: Rule) -> Investigation:
    target = TARGETS.get((current.status, event))
    if target is None:
        reject(current.status, event)
    if event is Event.COMPLETE:
        require_completion(current.facts, rule)
    return replace(current, status=target)


class State:
    """Alternative model: keep behavior in the active state object."""
    status: Status

    def on(self, event: Event, facts: ReviewFacts, rule: Rule) -> State:
        reject(self.status, event)

    def guidance(self) -> str:
        raise NotImplementedError


class PendingState(State):
    status = Status.PENDING

    def on(self, event: Event, facts: ReviewFacts, rule: Rule) -> State:
        if event is Event.START:
            return RunningState()
        if event is Event.CANCEL:
            return CancelledState()
        return super().on(event, facts, rule)

    def guidance(self) -> str:
        return "Start evidence review or cancel."


class RunningState(State):
    status = Status.RUNNING

    def on(self, event: Event, facts: ReviewFacts, rule: Rule) -> State:
        if event is Event.COMPLETE:
            require_completion(facts, rule)
            return CompletedState()
        if event is Event.CANCEL:
            return CancelledState()
        return super().on(event, facts, rule)

    def guidance(self) -> str:
        return "Collect evidence, complete review or cancel."


class CompletedState(State):
    status = Status.COMPLETED

    def guidance(self) -> str:
        return "Read the completed review."


class CancelledState(State):
    status = Status.CANCELLED

    def guidance(self) -> str:
        return "No further work is permitted."


@dataclass
class InvestigationWithState:
    investigation_id: str
    facts: ReviewFacts
    state: State

    def handle(self, event: Event, *, rule: Rule) -> None:
        self.state = self.state.on(event, self.facts, rule)

    def guidance(self) -> str:
        return self.state.guidance()


def completion_rule() -> Rule:
    return AllOf((has_evidence, ConfidenceAtLeast(80)))


def demo() -> None:
    rule = completion_rule()
    facts = ReviewFacts(("D-2",), 90)
    print(f"eligible I-42: {rule(facts)}")
    pending = Investigation("I-42", Status.PENDING, facts)
    running = transition(pending, Event.START, rule=rule)
    completed = transition(running, Event.COMPLETE, rule=rule)
    print(f"table: {pending.status.value} -> {running.status.value} -> {completed.status.value}")
    cancelled = transition(running, Event.CANCEL, rule=rule)
    try:
        transition(cancelled, Event.COMPLETE, rule=rule)
    except TransitionRejected as error:
        print(f"table after cancel: {error}")

    model = InvestigationWithState("I-42", facts, PendingState())
    model.handle(Event.START, rule=rule)
    print("object running: " + model.guidance())
    model.handle(Event.CANCEL, rule=rule)
    print("object cancelled: " + model.guidance())
    try:
        model.handle(Event.COMPLETE, rule=rule)
    except TransitionRejected as error:
        print(f"object after cancel: {error}")


def check_contracts() -> None:
    rule = completion_rule()
    accepted = ReviewFacts(("D-2",), 90)
    assert rule(accepted)
    assert not rule(ReviewFacts((), 90))
    assert not rule(ReviewFacts(("D-2",), 79))
    assert rule(ReviewFacts(("D-2",), 80))
    before = accepted
    assert rule(accepted) and accepted == before
    called: list[str] = []

    def should_not_run(facts: ReviewFacts) -> bool:
        called.append("called")
        return True

    assert not AllOf((has_evidence, should_not_run))(ReviewFacts((), 90))
    assert called == []
    print("predicate boundaries, unchanged facts and short-circuit composition verified")

    factories = {
        Status.PENDING: PendingState,
        Status.RUNNING: RunningState,
        Status.COMPLETED: CompletedState,
        Status.CANCELLED: CancelledState,
    }
    for status, factory in factories.items():
        for event in Event:
            current = Investigation("I-42", status, accepted)
            model = InvestigationWithState("I-42", accepted, factory())
            if (status, event) in TARGETS:
                changed = transition(current, event, rule=rule)
                model.handle(event, rule=rule)
                assert model.state.status is changed.status
            else:
                for operation in (
                    lambda: transition(current, event, rule=rule),
                    lambda: model.handle(event, rule=rule),
                ):
                    try:
                        operation()
                    except TransitionRejected:
                        pass
                    else:
                        raise AssertionError(f"illegal transition accepted: {status}, {event}")
                assert model.state.status is status
    print("table and State objects agree on every status/event pair")

    low = ReviewFacts(("D-2",), 60)
    current = Investigation("I-42", Status.RUNNING, low)
    model = InvestigationWithState("I-42", low, RunningState())
    for operation in (
        lambda: transition(current, Event.COMPLETE, rule=rule),
        lambda: model.handle(Event.COMPLETE, rule=rule),
    ):
        try:
            operation()
        except TransitionRejected as error:
            assert str(error) == "completion requirements not satisfied"
        else:
            raise AssertionError("failed completion guard was bypassed")
    assert current.status is Status.RUNNING and model.state.status is Status.RUNNING
    model.handle(Event.CANCEL, rule=rule)
    try:
        model.handle(Event.COMPLETE, rule=lambda facts: True)
    except TransitionRejected:
        pass
    else:
        raise AssertionError("passing predicate reopened cancelled investigation")
    print("failed guard preserves state; passing predicate cannot override cancellation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check_contracts() if args.check else demo()
