# Dataclass, Pydantic Dataclass, or BaseModel?

> **Who this is for**: Python backend engineers choosing the object that should own an internal
> value, validated input, or serialized API boundary.

Prerequisites: [dataclasses](dataclasses.md) and [Pydantic models](pydantic/README.md).
Use this decision guide after learning their construction and ownership behavior.

Choose a standard `@dataclass` for trusted in-process values, a Pydantic dataclass when an existing
dataclass-shaped API needs construction validation, and `BaseModel` when validation, serialization,
JSON Schema, aliases, and framework integration are part of the type's job.

> **Key insight**: Type annotations describe intended fields; the constructor and APIs around those
> fields determine whether the object is merely convenient Python state or a runtime boundary.

---

## 1. The same annotation produces three different contracts

Suppose an HTTP payload contains `{"quantity": "3"}`. The annotation `quantity: int` alone does not
decide whether the string is rejected, retained, or parsed.

```python
from dataclasses import dataclass

from pydantic import BaseModel
from pydantic.dataclasses import dataclass as pydantic_dataclass


@dataclass
class InternalLine:
    quantity: int


@pydantic_dataclass
class ValidatedLine:
    quantity: int


class BoundaryLine(BaseModel):
    quantity: int


print(type(InternalLine(quantity="3").quantity).__name__)   # str
print(type(ValidatedLine(quantity="3").quantity).__name__)  # int
print(BoundaryLine.model_validate({"quantity": "3"}).model_dump())
# {'quantity': 3}
```

The standard dataclass generates methods such as `__init__`, `__repr__`, and equality; it does not
enforce annotations. Both Pydantic forms validate normal construction. `BaseModel` also exposes the
model-oriented validation, serialization, and schema surface used by FastAPI.

**Success signal:** the three output lines are `str`, `int`, and `{'quantity': 3}`. If importing
`pydantic.dataclasses` fails, install Pydantic v2 before comparing the runtime contracts.

---

## 2. Choose by ownership, not by which syntax is shortest

| Need | Standard `@dataclass` | Pydantic dataclass | `BaseModel` |
|------|-----------------------|--------------------|-------------|
| Generated init/repr/equality | Yes | Yes | Model equivalents |
| Normal-construction validation | No | Yes | Yes |
| `model_validate` / `model_dump` | No | No; use `TypeAdapter` | Yes |
| JSON Schema | No | Through `TypeAdapter` | `model_json_schema()` |
| Pydantic validators/config | No | Supported, with dataclass-shaped ergonomics | Full/default surface |
| Best default | Trusted domain/value objects | Dataclass-compatible validated components | API/config/message boundaries |

A Pydantic `TypeAdapter` supplies serialization and schema operations for a Pydantic dataclass:

```python
from pydantic import TypeAdapter

adapter = TypeAdapter(ValidatedLine)
line = adapter.validate_python({"quantity": "3"})
print(adapter.dump_python(line))       # {'quantity': 3}
print(adapter.json_schema()["type"])  # object
```

> **Core:** choose the representation that owns the boundary. Do not add Pydantic to an internal
> object solely because its annotations look similar to an API schema.

---

## 3. Validation does not make a mutable object permanently valid

By default, Pydantic validates construction, not every later assignment. The following silently
changes a previously valid value unless assignment validation or immutability is configured:

```python
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Line(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    quantity: int = Field(ge=1)


line = Line(quantity=3)
try:
    line.quantity = 0
except ValidationError:
    print("rejected")
# rejected
```

Use `frozen=True` when replacement is clearer than mutation. Also remember that
`model_copy(update=...)` trusts its update mapping; reconstruct through `model_validate` when the
update is untrusted. The canonical Pydantic mechanics live in
[Pydantic models and fields](pydantic/01_models_and_fields.md).

---

## 4. What breaks first, and when not to use each

⚠️ A standard dataclass at an untrusted boundary accepts the wrong runtime types; the failure appears
later in business code rather than at construction.

⚠️ A Pydantic dataclass looks like a `BaseModel` but does not provide `model_dump()` or
`model_json_schema()` on the instance/class; use `TypeAdapter` or choose `BaseModel`.

Do not use `BaseModel` as an Object-Relational Mapper (ORM) entity merely to avoid defining a
separate schema. Persistence identity, lazy loading, and transaction state belong to the ORM. Do not
use a Pydantic dataclass when callers specifically depend on the `BaseModel` API. Do not add runtime
validation to objects whose inputs are already trusted and whose construction cost is hot without
measuring the trade-off.

> **Production:** define explicit models at trust boundaries, keep secret fields out of repr/dumps,
> decide assignment policy, and test rejected payloads—not only successful construction.

---

## Newer immutable mappings and sentinels

Python 3.15 adds `frozendict` and `sentinel` (GA; checked 2026-10-30). A frozen mapping prevents entry replacement, not mutation of objects it references; hashability also depends on its contents. A named sentinel can distinguish absence from `None` with clearer representation and typing than a bare `object()`. Keep the existing baseline on older interpreters. [Release notes](https://docs.python.org/3.15/whatsnew/3.15.html).

## Check the decision

An internal component expects a dataclass-shaped object. Its inputs now come from an untrusted
message, and the component does not need model methods or HTTP serialization. Which options keep
the boundary explicit without forcing it to adopt `BaseModel`?

<details><summary>Reasoned answer</summary>

A Pydantic dataclass can validate construction while retaining a dataclass-shaped interface.
Alternatively, validate the message with a `TypeAdapter` and construct/use an ordinary dataclass
behind that boundary. The plain dataclass constructor still does not validate by itself. Choose
`BaseModel` when its model API, serialization and schema surface are part of the component's job,
rather than because every annotated object must inherit from it.

</details>

**Next**: [FastAPI integration](../../fastapi/03_pydantic.md) for HTTP-specific behavior, or
[schema compatibility](../../data_validation/README.md) when models outlive a deployment.
