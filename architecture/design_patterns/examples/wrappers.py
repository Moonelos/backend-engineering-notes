"""Synchronous wrapper order and a local short-circuit chain, without external I/O."""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps


@dataclass(frozen=True)
class Request:
    investigation_id: str
    query: str
    preview: bool = False


@dataclass(frozen=True)
class Result:
    investigation_id: str
    status: str
    evidence_ids: tuple[str, ...] = ()


class Rejected(ValueError):
    pass


Action = Callable[[Request], Result]
Step = Callable[[Request], Result | None]


def instrument(label: str, trace: list[str]) -> Callable[[Action], Action]:
    def decorate(inner: Action) -> Action:
        @wraps(inner)
        def wrapped(request: Request) -> Result:
            trace.append(f"{label}:enter")
            try:
                result = inner(request)
            except Exception:
                trace.append(f"{label}:error")
                raise
            else:
                trace.append(f"{label}:success")
                return result
            finally:
                trace.append(f"{label}:exit")
        return wrapped
    return decorate


def make_action(trace: list[str]) -> Action:
    def investigate(request: Request) -> Result:
        trace.append("action")
        # Deterministic local fixture; no provider or database is contacted.
        evidence = ("D-2",) if request.query == "refund delay" else ()
        return Result(request.investigation_id, "completed", evidence)
    return investigate


def make_chain(action: Action, trace: list[str]) -> tuple[Step, ...]:
    def validate(request: Request) -> None:
        trace.append("validate")
        if not request.investigation_id.strip() or not request.query.strip():
            raise Rejected("investigation_id and query must be nonempty")
        return None

    def preview(request: Request) -> Result | None:
        trace.append("preview")
        if request.preview:
            return Result(request.investigation_id, "preview")
        return None

    return validate, preview, action


def dispatch(request: Request, steps: tuple[Step, ...]) -> Result:
    for step in steps:
        result = step(request)
        if result is not None:
            return result
    raise Rejected("no step handled the request")


def demo() -> None:
    trace: list[str] = []
    action = make_action(trace)
    wrapped = instrument("trace", trace)(instrument("metrics", trace)(action))
    result = wrapped(Request("I-42", "refund delay"))
    print(f"wrapped: {result.status} {result.investigation_id} -> {', '.join(result.evidence_ids)}")
    print(" | ".join(trace))

    trace.clear()
    chain = make_chain(action, trace)
    result = dispatch(Request("I-42", "refund delay", preview=True), chain)
    print(f"preview: {result.status} {result.investigation_id}")
    print("chain: " + " | ".join(trace))

    trace.clear()
    try:
        dispatch(Request("I-42", " ", preview=True), chain)
    except Rejected as error:
        print(f"rejected: {error}")
    print("chain: " + " | ".join(trace))


def check_contracts() -> None:
    trace: list[str] = []
    action = make_action(trace)
    wrapped = instrument("trace", trace)(instrument("metrics", trace)(action))
    assert wrapped.__name__ == "investigate"
    assert wrapped.__wrapped__.__wrapped__ is action
    result = wrapped(Request("I-42", "refund delay"))
    assert result.evidence_ids == ("D-2",)
    assert trace == ["trace:enter", "metrics:enter", "action", "metrics:success", "metrics:exit", "trace:success", "trace:exit"]
    trace.clear()
    swapped = instrument("metrics", trace)(instrument("trace", trace)(action))
    swapped(Request("I-42", "refund delay"))
    assert trace[:3] == ["metrics:enter", "trace:enter", "action"]
    assert trace[-2:] == ["metrics:success", "metrics:exit"]
    print("wrapper entry, reverse unwind, metadata and swapped order verified")

    trace.clear()
    failure = RuntimeError("local fixture failed")

    def fail(request: Request) -> Result:
        trace.append("action")
        raise failure

    failing = instrument("trace", trace)(instrument("metrics", trace)(fail))
    try:
        failing(Request("I-42", "refund delay"))
    except RuntimeError as error:
        assert error is failure
    else:
        raise AssertionError("exception was swallowed")
    assert trace == ["trace:enter", "metrics:enter", "action", "metrics:error", "metrics:exit", "trace:error", "trace:exit"]
    print("exception propagated after both cleanup paths")

    trace.clear()
    chain = make_chain(action, trace)
    assert dispatch(Request("I-42", "refund delay", preview=True), chain).status == "preview"
    assert trace == ["validate", "preview"]
    trace.clear()
    result = dispatch(Request("I-42", "unmatched"), chain)
    assert result.status == "completed" and result.evidence_ids == ()
    assert trace == ["validate", "preview", "action"]
    trace.clear()
    try:
        dispatch(Request("I-42", " ", preview=True), chain)
    except Rejected:
        pass
    else:
        raise AssertionError("preview bypassed validation")
    assert trace == ["validate"]
    try:
        dispatch(Request("I-42", "refund delay"), ())
    except Rejected as error:
        assert str(error) == "no step handled the request"
    else:
        raise AssertionError("unhandled request appeared successful")
    print("chain forwarding, handling, rejection and empty-result semantics verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    check_contracts() if args.check else demo()
