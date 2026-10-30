"""Offline contract simulation; no model, credentials, or network required."""
from dataclasses import dataclass
from enum import Enum
import json


class Status(Enum):
    COMPLETE = "complete"
    REFUSED = "refused"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class Result:
    status: Status
    text: str | None
    input_tokens: int
    output_tokens: int
    model_revision: str


def accept(result: Result, source: str) -> dict | None:
    if result.status is not Status.COMPLETE:
        return None
    if result.text is None:
        raise ValueError("missing result")
    data = json.loads(result.text)
    if not isinstance(data, dict) or set(data) != {"document_id", "title", "quote"}:
        raise ValueError("unexpected schema")
    if type(data["document_id"]) is not int or data["document_id"] != 42:
        raise ValueError("wrong document")
    if not isinstance(data["title"], str) or not 1 <= len(data["title"]) <= 100:
        raise ValueError("invalid title")
    if not isinstance(data["quote"], str) or not data["quote"] or data["quote"] not in source:
        raise ValueError("unsupported quote")
    return data


if __name__ == "__main__":
    source = "The retention period is 30 days."
    valid = Result(Status.COMPLETE, json.dumps({"document_id": 42,
        "title": "Retention", "quote": "30 days"}), 20, 12, "fake-v1")
    assert accept(valid, source)["document_id"] == 42
    print("accepted document=42")
    assert accept(Result(Status.REFUSED, None, 20, 0, "fake-v1"), source) is None
    print("refused: no write")
    assert accept(Result(Status.INCOMPLETE, '{"document_id":', 20, 4, "fake-v1"), source) is None
    print("incomplete: no write")
    try:
        accept(Result(Status.COMPLETE, valid.text.replace("30 days", "90 days"), 20, 12, "fake-v1"), source)
    except ValueError as error:
        assert str(error) == "unsupported quote"
        print("unsupported quote: rejected")
    else:
        raise AssertionError("unsupported quote accepted")
