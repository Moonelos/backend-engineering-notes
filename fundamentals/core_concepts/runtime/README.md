# Application runtime

**Prerequisites:** Functions/classes, annotations, [exceptions](../control_flow/exceptions.md) and [context managers](../control_flow/context_managers.md). Async examples assume [event loops](../../concurrency/async/01_event_loop_and_tasks.md).

## Reading order

| Lesson | Outcome |
|---|---|
| [Configuration](configuration.md) | Validate startup settings and own secrets/cached settings |
| [Logging](logging/README.md) | Trace standard-library records and configure structured output |
| [Signals](signals.md) | Coordinate bounded shutdown with the process/server owner |

## First result and stop point

Load a validated settings object or configure an observable logging call. Stop when your process owns these boundaries correctly. Guides retain their platform requirements and production checks. Continue to [Concurrency](../../concurrency/README.md) and [deployment](../../../operations/deployment/README.md) when needed.

[Back to Core Python Concepts](../README.md)
