# The Retained Log: Topics, Partitions, and Offsets

> **Question:** after a consumer reads a record, what remains in Kafka and what moves forward?

## Start with three order facts

The broker appends three records to one partition. An append adds to the end; it does not update an
earlier record in place:

```text
orders / partition 0

oldest                                                        newest
  │                                                              │
  ▼                                                              ▼
┌──────────────┬──────────────┬──────────────────┬─────────────────────┐
│ offset 0     │ offset 1     │ offset 2         │ next append offset  │
│ evt-101      │ evt-102      │ evt-103          │ 3                   │
│ order.created│ order.paid   │ order.packed     │                     │
└──────────────┴──────────────┴──────────────────┴─────────────────────┘
```

The broker chooses offsets `0`, `1`, and `2` as it appends. An offset is meaningful only together
with its topic and partition:

```text
(orders, partition 0, offset 2)  → evt-103
```

Partition 1 can also have an offset `2`. Therefore an offset is not an event ID, timestamp, or
position across the entire topic.

## Storage position and reader position are different state

Now two applications read the same partition:

```text
BROKER STATE — retained records

orders P0:  [0: created] [1: paid] [2: packed]       log end = 3
                 ▲                       ▲
                 │                       │
READER STATE     │                       │

fraud-v1 next = 1┘                       └─ billing-v1 next = 3
```

Read the picture from top to bottom:

1. The broker still stores all three records.
2. `billing-v1` has completed offsets `0` through `2`, so its next position is `3`.
3. `fraud-v1` has completed only offset `0`, so its next position is `1`.
4. Advancing either reader does not move or delete the boxes in the broker log.

A **consumer group** is a named logical reader. Kafka stores a committed next position for each
group and partition. The group name is what lets `billing-v1` resume at `3` after its process
restarts. Chapter 4 explains how processes inside a group share partitions.

> **Core model:** partitions own records; consumer groups own positions in those partitions.

## Three offset values answer different questions

The word “offset” appears in several related states. Keep the noun attached:

| Value | Owner | Meaning in the diagram |
|---|---|---|
| record offset | broker log | `evt-103` is stored at `2` |
| log-end offset | broker log | `3` is where the next append will go |
| committed offset | consumer group | `billing-v1` should resume at `3` |

Kafka commits the **next** offset, not the last completed one. If billing successfully processes
record `2`, committing `3` says “start with record 3 next time.” Confusing those two conventions
creates an off-by-one mental model even when the client API is working correctly.

## A new reader can replay retained history

Analytics joins tomorrow as a new group, `analytics-v1`. It has no saved position. If it chooses the
earliest retained position, it can read `0`, `1`, and `2` even though billing already processed
them:

```text
same broker log
     │
     ├── billing-v1   resumes at 3
     ├── fraud-v1     resumes at 1
     └── analytics-v1 starts at 0
```

This is why Kafka can rebuild a search index or projection from history. The live consumer does not
have to stop, and its committed position does not need to be rewound.

The analogy to a database transaction log is useful: both retain an ordered history that readers
can follow. The analogy stops at authority—Kafka is often a transport and replay source, not
automatically the authoritative database for mutable business entities.

## Retention decides how long replay remains possible

Records remain until the topic's cleanup policy removes them.

- **Time/size retention** deletes old log segments after an age or size boundary.
- **Compaction** eventually keeps the latest value for each key, useful for reconstructing current
  keyed state rather than every historical transition.

These policies change broker storage, not merely reader state. If retention removes offsets `0`
through `9` while a group is still committed at `5`, the group asks for data that no longer exists.
Its configured reset behavior may move it to the earliest remaining offset or to the end; neither
choice reconstructs the deleted history.

For a compacted topic, a key with a null value is a **tombstone**, a record that represents deletion.
Compaction is asynchronous, so old values and tombstones can remain visible for a while.

## Lag measures distance, not waiting time

With log end `120` and committed next offset `100`:

```text
lag = log-end offset - committed offset
    = 120 - 100
    = 20 records
```

Those 20 records might represent milliseconds during peak traffic or hours in a quiet topic.
Monitor record lag to measure backlog and event age to measure business staleness.

## Check your model

The log contains offsets `0` through `9`. Billing is committed at `10`. A new analytics group starts
at the earliest retained offset. Billing then commits `10` again.

What can analytics read?

It can still read `0` through `9`. Billing changed only billing's group position, and committing the
same position again changes no broker-log state. The answer changes only if retention or compaction
has removed some records.

## Where this model stops

One partition gives one ordered append sequence but only one unit of parallel work for a
conventional consumer group. Kafka scales a topic by using multiple partitions. That creates a new
design question: which records must remain in the same ordered sequence?

Do not use Kafka as the only system of record when the application needs arbitrary queries,
relational constraints, or indefinite authoritative history. Pair it with the database or object
store that owns those requirements.

---

**Next:** [Keys Define the Ordering Boundary](03_partitioning_keys_and_ordering.md)
