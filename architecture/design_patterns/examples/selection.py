"""Local, dependency-free retrieval strategies. Run from the repository root."""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass

Retrieve = Callable[[str], tuple[str, ...]]
Factory = Callable[[], Retrieve]


@dataclass(frozen=True)
class Document:
    document_id: str
    text: str


DOCUMENTS = (
    Document("D-1", "refund policy"),
    Document("D-2", "refund delay"),
    Document("D-3", "delay reporting"),
)


def match_any(query: str) -> tuple[str, ...]:
    words = frozenset(query.casefold().split())
    return tuple(
        document.document_id
        for document in DOCUMENTS
        if words.intersection(document.text.casefold().split())
    )


def match_all(query: str) -> tuple[str, ...]:
    words = frozenset(query.casefold().split())
    return tuple(
        document.document_id
        for document in DOCUMENTS
        if words and words.issubset(document.text.casefold().split())
    )


@dataclass(frozen=True)
class LimitedMatches:
    retrieve: Retrieve
    limit: int

    def __post_init__(self) -> None:
        if type(self.limit) is not int or not 1 <= self.limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")

    def __call__(self, query: str) -> tuple[str, ...]:
        return self.retrieve(query)[: self.limit]


def build_retriever(mode: str, *, limit: int = 1) -> Retrieve:
    # Local registry: values are factories, not already-constructed resources.
    factories: dict[str, Factory] = {
        "any": lambda: match_any,
        "all": lambda: match_all,
        "first": lambda: LimitedMatches(retrieve=match_any, limit=limit),
    }
    try:
        factory = factories[mode]
    except KeyError:
        raise ValueError("mode must be one of: all, any, first") from None
    return factory()


def investigate(
    investigation_id: str, query: str, *, retrieve: Retrieve
) -> tuple[str, tuple[str, ...]]:
    if not investigation_id.strip() or not query.strip():
        raise ValueError("investigation_id and query must be nonempty")
    return investigation_id, retrieve(query)


def demo() -> None:
    for mode in ("any", "all", "first"):
        retrieve = build_retriever(mode, limit=1)
        investigation_id, evidence_ids = investigate(
            "I-42", "refund delay", retrieve=retrieve
        )
        print(f"{mode}: {investigation_id} -> {', '.join(evidence_ids)}")


def check_contracts() -> None:
    any_match = build_retriever("any")
    all_match = build_retriever("all")
    first_match = build_retriever("first", limit=1)
    assert any_match("refund delay") == ("D-1", "D-2", "D-3")
    assert all_match("refund delay") == ("D-2",)
    assert first_match("refund delay") == ("D-1",)
    for retrieve in (any_match, all_match, first_match):
        assert retrieve("unmatched") == ()
        assert retrieve("REFUND") == retrieve("refund")
        before = investigate("I-42", "refund", retrieve=retrieve)
        investigate("I-43", "reporting", retrieve=retrieve)
        assert before == investigate("I-42", "refund", retrieve=retrieve)
        assert type(before[1]) is tuple
        assert len(before[1]) == len(set(before[1]))

    try:
        build_retriever("typo")
    except ValueError as error:
        assert str(error) == "mode must be one of: all, any, first"
        print(f"unknown mode rejected: {error}")
    else:
        raise AssertionError("unknown mode was accepted")

    for limit in (0, -1, 101, True, 1.5):
        try:
            build_retriever("first", limit=limit)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid limit accepted: {limit!r}")
    print("invalid limits rejected")

    calls: list[str] = []

    def record_call(query: str) -> tuple[str, ...]:
        calls.append(query)
        return ()

    for investigation_id, query in (("", "refund"), ("I-42", " ")):
        try:
            investigate(investigation_id, query, retrieve=record_call)
        except ValueError:
            pass
        else:
            raise AssertionError("empty input was accepted")
    assert calls == [], "invalid input reached retrieval"
    print("empty input rejected before retrieval")
    print("strategy contracts and request isolation verified")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify local behavior contracts")
    args = parser.parse_args()
    if args.check:
        check_contracts()
    else:
        demo()
