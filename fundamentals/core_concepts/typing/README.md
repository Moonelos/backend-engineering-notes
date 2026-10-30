# Python typing

**Prerequisites:** Basic functions/classes and annotations such as `name: str`. A checker and a runtime validator act on contracts at different times.

## Reading order

| Lesson | Outcome |
|---|---|
| [Type-checking workflow](typing_workflow.md) | Run a check, interpret a diagnostic and own configuration |
| [Typing](typing.md) | Choose unions, TypedDict, generics, protocols and narrowing |

## First result and stop point

Run the checker and change one argument to observe a diagnostic. Stop after basic annotations and unions if those cover your API. Return to advanced callable/generic contracts when needed. [Pydantic](../data_models/pydantic/README.md) owns runtime validation.

[Back to Core Python Concepts](../README.md)
