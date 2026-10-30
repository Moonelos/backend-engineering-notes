# Event-driven architecture

Represent facts, dispatch local reactions, separate read/write models and preserve delivery
obligations when work crosses a process boundary.

## Choose a reading path

**First local result:** [Local events and dispatch](02_local_events_and_dispatch.md) runs a small
Python dispatcher and makes handler ordering and failure visible. It assumes Python functions,
dataclasses and exceptions. Stop when an in-process notification is all the feature promises.

**Different read and write needs:** [CQRS with one database](03_cqrs_read_and_write_models.md)
runs separate write behavior and a dashboard query against SQLite. It introduces the needed SQL
and transaction vocabulary. CQRS is independently useful; a broker and event sourcing are optional.

**Durable integration:** read the existing [durable-task foundation](../../background_work/foundations/03_minimal_durable_task.md)
and [message contracts](../../infrastructure/messaging/05_message_contracts_and_outbox.md), then
[Events and projections](01_events_and_projections.md). This path adds committed publication,
consumer progress, lag and replay. The numbering of the existing chapter is preserved; choose
reading order by the outcome above.

## Contents

| Chapter | Outcome |
|---|---|
| [Local events and dispatch](02_local_events_and_dispatch.md) | Observer, domain facts, explicit subscribers and the gap between callbacks and durable delivery |
| [CQRS with one database](03_cqrs_read_and_write_models.md) | Different write/read models, invariant enforcement, query DTOs and the cost of asynchronous projections |
| [Events and projections](01_events_and_projections.md) | Integration contracts, choreography/orchestration, eventual consistency and replay |

Continue from [commands and application handlers](../design_patterns/04_commands_and_application_handlers.md)
when a requested operation needs independent reactions. The full [design-pattern path](../design_patterns/README.md)
places these decisions alongside dependency injection, wrappers and state modeling.
