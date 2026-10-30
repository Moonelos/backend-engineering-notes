# Control flow and resource lifetimes

**Prerequisites:** Basic functions/classes, try syntax and annotations. [Functions and scope](../language/functions_and_scope.md) explains call lifetimes.

## Reading order

| Lesson | Outcome |
|---|---|
| [Exceptions](exceptions.md) | Follow propagation and choose recovery or translation |
| [Iterators and generators](iterators_and_generators.md) | Trace suspension, exhaustion and early cleanup |
| [Context managers](context_managers.md) | Own acquisition/cleanup and compose resources |

## First result and stop point

Predict which layer handles failure and which cleanup runs. Stop after exceptions for failure policy; continue before owning streams or setup/teardown. Async variants assume [event loops and tasks](../../concurrency/async/01_event_loop_and_tasks.md).

[Back to Core Python Concepts](../README.md)
