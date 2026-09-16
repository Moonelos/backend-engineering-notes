# Consumer Groups Trade Partition Ownership for Parallel Work

> **Who this is for**: engineers scaling consumers or diagnosing duplicate work and lag spikes.

## A fourth consumer does not make three partitions faster

With three partitions and four consumers in group `billing-v1`, three consumers own one partition
each and one is idle. A conventional consumer-group partition has one active owner at a time:

```text
orders P0 → billing-1
orders P1 → billing-2
orders P2 → billing-3
             billing-4 (idle)
```

---

## 1. Group identity creates an independent subscription

Consumers sharing a `group.id` divide partitions. A different group reads the same retained records
from its own positions. Use `billing-v1` and `fraud-v1` for independent applications; do not give
unrelated services the same group merely because they consume the same topic.

The **group coordinator** is the broker-side actor that tracks membership, drives assignment, and
stores or serves the group's committed offsets. The group's committed offset is a recovery
checkpoint, usually the next record to read. It is not the consumer's live in-memory position and
can lag behind work already fetched.

---

## 2. Rebalancing moves ownership and exposes unsafe processing

Membership or subscription changes cause the coordinator to change partition assignment. For
example, when `billing-2` leaves, the coordinator removes it from the membership, assigns P1 to
`billing-1`, and tells the new owner to resume from P1's stored checkpoint. Assignment ownership
changes; the checkpoint does not advance merely because the member left.

A slow consumer can therefore lose ownership while still processing a record. If it performs an
external effect and fails before its offset is safely committed, the new owner processes that
record again.

```text
C1 reads offset 8 → charges card → rebalance/crash → no commit
C2 owns partition → reads offset 8 → charge attempted again
```

The local safety bridge is **idempotency**: both attempts send the stable operation identity
`charge:event-evt-101` to a durable payment provider or effect store. The first attempt records the
charge and its result. The retry makes a unique claim with the same identity, finds the stored
result, and returns it without applying a second charge. Only then does the consumer commit its
Kafka offset. A process-local set is insufficient because it disappears in the same crash that
caused the retry. [Durable Consumer-Effect Idempotency](../reliability/02_durable_consumer_effect_idempotency.md)
owns the full durable implementation. Thus “one owner at a time” is not “one execution ever.”

---

## 3. Polling is both data access and membership health

The consumer must poll often enough to remain healthy. Long record processing can exceed the
allowed poll interval, trigger reassignment, and amplify duplicates. Bound work per poll, pause
partitions while capacity is full, or separate polling from bounded workers without committing
past unfinished records.

The **consumer group protocol** is Kafka's GA broker-driven assignment protocol. In Kafka 4.3 it is
not yet the Java client's default: set the effective client property `group.protocol=consumer`.
Assignment strategy, heartbeat interval, and session timeout then move to broker-side settings;
client properties `partition.assignment.strategy`, `heartbeat.interval.ms`, and
`session.timeout.ms`, plus `enforceRebalance(...)`, no longer apply. A client may request a
broker-provided assignor with `group.remote.assignor`; otherwise the coordinator chooses from the
broker's `group.consumer.assignors` (whose first/default entry is `uniform`).

The callback contract is incremental too. With a `ConsumerRebalanceListener`,
`onPartitionsRevoked` runs only when this member actually has a non-empty set to revoke;
`onPartitionsAssigned` still runs once when an assignment change completes, even for an empty set;
and `onPartitionsLost` means another member may already own the partitions, so committing from it
is unsafe. Audit callback code that assumes every rebalance revokes everything.

This is the smallest migration trace:

```text
classic:  partition.assignment.strategy=CooperativeStickyAssignor
rollout:  group.protocol=consumer; group.remote.assignor=uniform
observe:  coordinator reports Consumer group; P0/P1/P2 each have one owner
rollback: replace members with group.protocol=classic
          → group becomes Classic when the last Consumer-protocol member leaves
```

An online rolling migration works only when the classic assignor does not embed custom metadata and
the broker permits the direction. Otherwise stop every member, let the group become empty, and
restart all members with the new protocol. Test rollback before finalizing the cluster upgrade:
once a group has used the new protocol, the cluster cannot be downgraded below Kafka 3.4.1. The
[Kafka 4.3 protocol guide](https://kafka.apache.org/43/operations/consumer-rebalance-protocol/)
documents the live migration constraints and effective settings.

---

## 4. The observable signals tell different stories

- Rising lag with stable membership means processing capacity is below arrival rate.
- Repeated assignment changes indicate churn or poll stalls.
- Many duplicates around rebalances indicate non-idempotent effects or unsafe commits.
- Idle consumers with lag mean skew, blocked processing, or more consumers than partitions.

**Success signal:** an assignment inspection accounts for every partition exactly once within the
group, and a controlled consumer restart causes a bounded handoff without lost effects.

> **Key insight**: a consumer group coordinates partition ownership; correctness still depends on
> how application effects and offset checkpoints cross crashes.

---

## 5. What breaks, and when not to use conventional groups

⚠️ Auto-committing offsets can advance the checkpoint before slow business processing completes.
The symptom after a crash is missing effects even though consumer lag looked healthy.

Do not use conventional groups when many workers must concurrently process individual records from
the same partition with per-record acknowledgment. Evaluate [share groups](../ecosystem/03_share_groups_and_queue_semantics.md)
or a purpose-built work queue.

---

**Next**: [Replication, Leaders, and KRaft](05_replication_leaders_and_kraft.md)
