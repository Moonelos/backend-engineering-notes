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

## Stop the connector, commit another event, then resume from its position

Run the complete [CDC fixture](../examples/cdc/round_trip.py) from the repository root. It needs
Python 3.11+, Docker and image-download access; it creates a private Docker network with PostgreSQL
17, Kafka 4.3.2 and an archived Debezium Connect 3.3 lab image. No host ports, existing databases or
production credentials are used. These pins define a reproducible learning stack, not a current
production support recommendation.

```bash
python3 infrastructure/kafka/examples/cdc/round_trip.py
```

The fixture enables PostgreSQL logical WAL, creates an insert-only outbox, registers a `pgoutput`
connector with a named slot/publication, and maps events into a one-partition Kafka topic. The
`no_data` snapshot mode intentionally starts from new changes in this freshly empty fixture. An
existing production table needs a snapshot/reconciliation decision; skipping its old rows would
lose historical obligations.

The same order carries both transitions:

```mermaid
sequenceDiagram
    participant D as PostgreSQL outbox and WAL
    participant C as Debezium task
    participant K as Kafka orders.events
    D->>C: Commit evt-101, ord-42 version 1
    C->>K: Key ord-42, stable event ID
    Note over C: Persist source LSN; stop connector through Connect API
    D->>D: Commit evt-102, ord-42 version 2 while stopped
    Note over C: Resume task from stored source offset
    D->>C: Read retained WAL after saved LSN
    C->>K: Key ord-42, version 2
    Note over C: Source checkpoint advances
```

Require the final `PASS` line, both stable IDs in version order, the same `ord-42` key and an
advanced source checkpoint. The exact numeric LSN varies by database run; equality to a copied
number is not the test. A task that reports RUNNING but never advances fails the fixture's deadline.
The script removes its containers/network in `finally`; it does not delete the user's data.

This exercise stops and resumes the connector task, not the database. Replaying after an unclean
process death can duplicate already-published events; retain the consumer inbox from the preceding
lesson. A source checkpoint describes the connector's handoff, not every downstream effect. The
[Debezium PostgreSQL reference](https://debezium.io/documentation/reference/3.3/connectors/postgresql.html)
and [Event Router](https://debezium.io/documentation/reference/3.3/transformations/outbox-event-router.html)
explain the versioned slot and routing contracts (checked 2026-10-30).

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

## Recap

- The database commit makes the outbox insert visible in WAL.
- The connector resumes from its saved source position and may repeat publication after uncertainty.
- Retained WAL plus stable event identities make recovery inspectable; RUNNING alone does not.

## Check yourself

**Q: The saved checkpoint references WAL already removed. Is restarting a RUNNING task enough?**

<details><summary>Answer</summary>

No. The required change history is absent. Stop cleanup, select a supported re-snapshot/restore procedure and reconcile expected event IDs against destination IDs before resuming normal publication.

</details>

**Q: The outbox has two rows and the topic has two records. Does that alone prove delivery?**

<details><summary>Answer</summary>

No. They could be two copies of one event. Compare stable IDs, aggregate versions, key and source-position progress.

</details>

## Try it

Keep the fixture but add a third event while the connector is stopped. Fill the expected record-ID set and final ordering assertion.

Hint: A checkpoint integer is not an event count.

<details><summary>Worked solution</summary>

Expect IDs 101, 102 and the new third ID in commit order for ord-42. Require the checkpoint to advance and the consumer effect ledger to contain one application per event even if publication retries repeat an ID.

</details>


**Next**: [Testing Kafka Services](05_testing_kafka_services.md).
