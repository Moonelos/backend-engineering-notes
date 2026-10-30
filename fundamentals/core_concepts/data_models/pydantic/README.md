# Pydantic models

Pydantic v2 parses and validates input, builds Python objects and serializes selected output.
These capabilities are useful without FastAPI.

Prerequisites: [classes](../../objects/classes_and_methods.md), [dataclasses](../dataclasses.md)
and basic annotations such as `list[str]` and `str | None`. The
[typing guide](../../typing/README.md) explains unfamiliar annotations.

## Reading order

| Lesson | Outcome |
|---|---|
| [Models and fields](01_models_and_fields.md) | Construct a model; distinguish required, nullable and default values |
| [Validation](02_validation.md) | Trace coercion, validators, nested inputs and unions |
| [Serialization and schema](03_serialization_and_schema.md) | Control output shape, aliases, serializers and JSON Schema |

**First result:** valid input becomes a model and invalid input raises a structured error.
**Stop after entry 1** for simple boundaries. Continue through entry 3 when parsing and output
shape differ. Then compare carriers in [Data model choices](../data_model_choices.md).

[FastAPI integration](../../../fastapi/03_pydantic.md) owns HTTP request bodies, response models,
validation responses and partial updates. [Configuration](../../runtime/configuration.md) owns
pydantic-settings and startup configuration.

[Back to Data models](../README.md)
