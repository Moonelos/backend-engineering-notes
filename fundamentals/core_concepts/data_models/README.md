# Python data models

**Prerequisites:** Read [classes](../objects/classes_and_methods.md) and [attribute access](../objects/attributes_and_introspection.md).

## Reading order

| Lesson | Outcome |
|---|---|
| [Dataclasses](dataclasses.md) | Generate methods while owning defaults, invariants and mutation |
| [Enums and named tuples](enums_and_named_tuples.md) | Choose symbolic values and tuple-compatible records |
| [Pydantic](pydantic/README.md) | Build a validation and serialization boundary without a web framework |
| [Data model choices](data_model_choices.md) | Compare dataclasses, Pydantic dataclasses and BaseModel |

## First result and stop point

Construct an order line and prove its default list is independent of another instance. Stop at dataclasses for trusted internal state. Continue into Pydantic for external input, then [FastAPI integration](../../fastapi/03_pydantic.md) for HTTP and [schema compatibility](../../data_validation/README.md) for persisted data.

[Back to Core Python Concepts](../README.md)
