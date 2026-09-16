# Event Contracts Must Outlive Any One Deployment

> **Who this is for**: engineers designing payloads shared by independently deployed services.

## A minimal event with identity and meaning

```json
{
  "event_id": "evt-101",
  "event_type": "order.created",
  "schema_version": 1,
  "occurred_at": "2026-09-04T09:15:00Z",
  "producer": "orders-api",
  "data": {"order_id": "ord-42", "currency": "EUR", "total_minor": 2590}
}
```

Validate this envelope at the producer boundary and again at the consumer boundary. `event_id`
supports deduplication, `event_type` selects behavior, and `schema_version` makes interpretation
explicit. Money uses minor units so binary floating point cannot change the amount.

Save this minimal complete contract as `order-created-v1.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://contracts.example.com/order-created-v1.schema.json",
  "type": "object",
  "required": ["event_id", "event_type", "schema_version", "occurred_at", "producer", "data"],
  "properties": {
    "event_id": {"type": "string", "minLength": 1},
    "event_type": {"const": "order.created"},
    "schema_version": {"type": "integer", "minimum": 1},
    "occurred_at": {"type": "string", "format": "date-time"},
    "producer": {"type": "string", "minLength": 1},
    "data": {
      "type": "object",
      "required": ["order_id", "currency", "total_minor"],
      "properties": {
        "order_id": {"type": "string", "minLength": 1},
        "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
        "total_minor": {"type": "integer", "minimum": 0}
      },
      "additionalProperties": true
    }
  },
  "additionalProperties": true
}
```

`additionalProperties` permits an old reader to ignore additive fields. `schema_version` remains a
positive integer rather than a v1 constant because an old reader that promises forward
compatibility must not reject a higher version number before it can ignore that version's additive
fields. Required fields and their meaning stay strict. Save the following as `event_contract.py`
beside the schema:

```python
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = json.loads(Path(__file__).with_name("order-created-v1.schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def validate_event(event: dict) -> None:
    VALIDATOR.validate(event)
```

Run this from the directory containing the two files; `--with` creates an isolated environment, so
it does not require a pre-existing `pyproject.toml`:

```bash
uv run --with jsonschema python -c 'from event_contract import validate_event; validate_event({"event_id":"evt-101","event_type":"order.created","schema_version":1,"occurred_at":"2026-09-04T09:15:00Z","producer":"orders-api","data":{"order_id":"ord-42","currency":"EUR","total_minor":2590}}); print("contract: valid")'
```

The success signal is `contract: valid`; a `jsonschema.exceptions.ValidationError` names the first
rejected path.

---

## 1. Independent deployment makes payload changes distributed changes

An in-process function signature changes atomically with its caller. An event may remain retained
while producers and consumers deploy days apart. Removing `currency` can therefore break replay
long after the producer that wrote the record has gone.

Prefer additive evolution: add optional fields with meaningful defaults, let consumers ignore
unknown fields, and keep the semantic meaning of existing fields stable.

---

## 2. Compatibility is about readers and writers

- **Backward compatibility**: the new reader accepts old data.
- **Forward compatibility**: the old reader accepts new data.
- **Full compatibility**: both directions hold across the supported window.

Changing `total_minor` from integer cents to a decimal major-unit string is not compatible merely
because JSON can represent both. The wire shape and business meaning changed.

Use JSON Schema, Avro, or Protobuf plus a schema registry when automated compatibility enforcement
is worth the platform cost. The registry checks structure; contract tests must still check meaning.

This executable compatibility test uses a different schema and validator for each reader. Save it
as `test_event_compatibility.py` beside `event_contract.py`:

```python
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator, ValidationError

V1_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "data"],
    "properties": {
        "schema_version": {"type": "integer", "minimum": 1},
        "data": {
            "type": "object",
            "required": ["order_id", "currency", "total_minor"],
            "properties": {
                "order_id": {"type": "string"},
                "currency": {"type": "string"},
                "total_minor": {"type": "integer", "minimum": 0},
            },
            "additionalProperties": True,
        },
    },
    "additionalProperties": True,
}
V2_SCHEMA = deepcopy(V1_SCHEMA)
V2_SCHEMA["properties"]["data"]["properties"]["coupon_code"] = {
    "type": ["string", "null"],
    "default": None,
}
V1_READER = Draft202012Validator(V1_SCHEMA)
V2_READER = Draft202012Validator(V2_SCHEMA)

V1 = {
    "event_id": "evt-101", "event_type": "order.created", "schema_version": 1,
    "occurred_at": "2026-09-04T09:15:00Z", "producer": "orders-api",
    "data": {"order_id": "ord-42", "currency": "EUR", "total_minor": 2590},
}


def test_backward_new_reader_accepts_retained_v1() -> None:
    V2_READER.validate(V1)


def test_forward_old_reader_accepts_v2_additive_field() -> None:
    v2 = deepcopy(V1)
    v2["schema_version"] = 2
    v2["data"]["coupon_code"] = "AUTUMN10"
    V1_READER.validate(v2)


def test_semantic_wire_break_is_rejected() -> None:
    broken = deepcopy(V1)
    broken["data"]["total_minor"] = "25.90"  # major-unit string changes shape and meaning
    with pytest.raises(ValidationError, match="not of type 'integer'"):
        V2_READER.validate(broken)
```

Run `uv run --with pytest --with jsonschema pytest -q test_event_compatibility.py`. The observable
result is `3 passed`. The first test is the backward direction (new reader, retained old data); the
second is the forward direction (old reader, newly written data). If the third test does not raise,
the v2 reader is not enforcing the money representation. This proves the supported examples, not
all possible payloads or semantic compatibility. A schema registry becomes the canonical shared
lifecycle when contracts span many clients; see
[Schema Registry and Serialization](05_schema_registry_and_serialization.md).

---

## 3. Events describe facts, not remote commands in disguise

`order.created` states a completed domain fact and can serve many consumers. `send-this-email-now`
targets one worker and behaves more like a command. Mixing the two makes ownership, retries, and
audit meaning unclear.

> **Key insight**: an event contract includes semantics and compatibility promises, not just a
> serializable payload.

---

## 4. What breaks, how to verify, and when not to evolve in place

**Success signal:** compatibility tests read representative retained v1 records with the v2
consumer and exercise v2 records against the oldest supported reader. Checking only schema-registry
acceptance silently misses changed business meaning.

⚠️ Reusing `event_type` while changing its meaning corrupts consumers without a parse error. Publish
a new event type or topic when the fact itself changes.

Do not put large blobs, secrets, or mutable database snapshots into every event. Store blobs in
object storage, publish a stable reference, and minimize personal data whose retention you cannot
later revoke cleanly.

---

**Next**: [Python Producers and Consumers](02_python_producers_and_consumers.md)
