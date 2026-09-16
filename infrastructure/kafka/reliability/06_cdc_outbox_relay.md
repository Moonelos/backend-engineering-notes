# A CDC Relay Owns a Database-Log Position, Not Polling Locks

> **Who this is for**: teams choosing log-based change data capture (CDC) after understanding the
> transactional outbox.

## The actor and checkpoint change

A polling relay asks the table for unpublished rows and later mutates `published_at`. A CDC
connector reads the database transaction log, stores a log position, and emits an insert after the
database commit becomes visible. Mixing those models hides different failures.

```text
application transaction
  └─ INSERT outbox evt-101, aggregate_id=ord-42 ── COMMIT at database log position L42
                                                     ↓
Debezium connector checkpoint L41 → reads L42 → routes evt-101 to Kafka key ord-42 → checkpoint L42
```

The outbox table is insert-only for the connector path. Updating a row to “published” creates
another change event unless filters happen to suppress it, and deleting it too early can outrun a
lagging connector. Retention must exceed the maximum connector outage plus repair time.

## Route the outbox event explicitly

This explanatory connector fragment shows the load-bearing Debezium outbox Event Router settings;
the database connector's hostname, credentials, publication/slot, TLS, and Kafka worker security
remain deployment inputs and must not be copied from a note:

```json
{
  "transforms": "outbox",
  "transforms.outbox.type": "io.debezium.transforms.outbox.EventRouter",
  "transforms.outbox.table.field.event.id": "event_id",
  "transforms.outbox.table.field.event.key": "aggregate_id",
  "transforms.outbox.table.field.event.type": "event_type",
  "transforms.outbox.table.field.event.payload": "payload",
  "transforms.outbox.route.by.field": "event_type",
  "transforms.outbox.route.topic.replacement": "orders.events"
}
```

`aggregate_id=ord-42` becomes the Kafka record key, so `order.created` and `order.paid` for the same
order route together. `event_id` remains in the event/header for consumer deduplication. Verify this
with two inserted rows for `ord-42`: the destination records must share a partition and appear in
database commit order. A unique `event_id` key would not establish aggregate order.

## Operate the handoff by position and age

Observe four separate states:

| State | Healthy evidence | First failure signal | Recovery |
|---|---|---|---|
| Database log retention | connector's last position is still retained | requested log segment/WAL position is gone | restore/re-snapshot by an approved procedure; do not skip silently |
| Connector task | task running and position advancing | failed task or repeated restart | fix credentials/schema/plugin, then resume from stored position |
| Outbox age | oldest un-emitted insert stays within SLO | age grows while app commits continue | stop cleanup, restore connector progress, reconcile event IDs |
| Kafka destination | keyed records acknowledged | authorization, serialization, or broker errors | fix destination and resume; consumers still deduplicate |

Before changing the schema, test the connector against both old and new row shapes. Adding a
required field without coordinating the Event Router can strand the connector at the first new
record. Preserve the raw outbox row and connector logs until reconciliation proves every expected
`event_id` reached Kafka.

⚠️ If the source database deletes transaction logs before a stopped connector catches up, restart
cannot recover from its stored position. “Task is running” is not sufficient; position progress and
oldest-outbox age must both move.

Disable the connector only after recording its final position, stopping outbox cleanup, and choosing
who owns future publication. Re-enabling from an old position can replay records; starting from a new
position can lose them. In both cases, compare stable `event_id` sets before resuming cleanup.

Do not choose CDC merely to avoid writing a polling loop. It adds database-log permissions, retained
log capacity, connector state, plugin upgrades, and another recovery procedure. Choose it when its
throughput, low query load, or shared integration ownership earns those costs.

**Next**: [Testing Kafka Services](05_testing_kafka_services.md).
