# Topic Topology Is an Application Contract, Not Folder Organization

> **Who this is for**: engineers deciding topic boundaries, keys, partitions, and retention.

## Start from invariants, not naming aesthetics

For order lifecycle facts, a practical starting decision is one `orders.events.v1` topic keyed by
`order_id`, retained long enough for supported replay, with partitions sized for expected peak
consumer parallelism. Split it only when access, retention, ownership, or throughput requirements
actually differ.

---

## 1. A topic boundary changes operational policy

Events in one topic share major policy surfaces: authorization, retention/compaction, partition
count, quotas, and consumer discovery. Separate payments from public catalog events when access
control differs; do not create one topic per event type by reflex. The operational owner for
creation, effective overrides, quotas, and rollback is
[Configuration and Topic Administration](../operations/05_configuration_and_topic_administration.md).

---

## 2. Partition count sets parallelism and ongoing cost

More partitions permit more conventional consumers, but also increase metadata, open files,
replication traffic, rebalances, and recovery work. Size from peak bytes/second and handler capacity,
then include measured headroom. Increasing later can change key placement; decreasing requires a
new topic.

Make the arithmetic reviewable rather than choosing a round number. The `orders-api` team measures
these peak limits in a load test:

| Constraint | Peak workload | Measured safe capacity | Partitions required |
|---|---:|---:|---:|
| Broker path | 24 MiB/s | 8 MiB/s per partition | `ceil(24 / 8) = 3` |
| Consumer handler | 18,000 events/s | 3,000 events/s per partition | `ceil(18,000 / 3,000) = 6` |

The tighter constraint wins, so six is the minimum measured count. With 50% failure/burst headroom,
the team starts with nine partitions, then verifies that nine active consumers keep business
freshness within its service objective during the peak test. Starting with three because broker
throughput alone looks sufficient would cap handler throughput near 9,000 events/s and build lag at
roughly 9,000 events/s. If handler capacity later doubles to 6,000 events/s per partition, broker
throughput still requires three partitions; that changed input does *not* justify shrinking the
existing topic, because Kafka cannot decrease a topic's partition count. Keep nine or migrate to a
new topic when the ongoing cost is worth the disruption. Full cluster and failure-headroom sizing
belongs in [Capacity Planning](../operations/02_capacity_planning_and_performance.md).

## 3. Choose deletion for history and compaction for keyed state

`cleanup.policy=delete` answers “how long may this history remain?”: whole old log segments become
eligible after the configured time or size threshold. `cleanup.policy=compact` answers a different
question: “what is the latest known value for each key?” Compaction retains the latest value per
key but runs asynchronously, so duplicate older values may remain visible meanwhile; it is not a
uniqueness constraint.

For a rebuildable `customer-email-current` topic, the key is `customer_id` and the value is the
latest email:

```text
offset 40: key=c-7 value={"email":"old@example.com"}
offset 52: key=c-7 value={"email":"new@example.com"}
offset 61: key=c-7 value=null
```

After compaction, offset 52 supersedes offset 40. The null-valued record is a **tombstone**: it
eventually removes the key's prior value, and the tombstone itself becomes eligible for removal
after `delete.retention.ms`. Therefore a consumer rebuilding from offset 0 must finish before that
window can elapse, or it can miss a deletion and resurrect stale state in its materialized view.
Set the window from the slowest measured full rebuild plus failure headroom, and test a delete in a
rebuild drill.

Use `delete` for an immutable `orders.events.v1` audit/replay history. Use `compact` for the
current-email changelog. Use `delete,compact` only when both “latest value per key” and a maximum
history/storage window are deliberate requirements. Compaction requires a meaningful non-null key;
if records are unkeyed or every event in the history matters, it is the wrong cleanup model. These
behaviors and the per-topic controls are defined in Apache Kafka's
[topic configuration reference](https://kafka.apache.org/43/configuration/topic-configs/).

---

## 4. Ownership prevents incompatible producers

Assign a team to the topic and schema, restrict write ACLs, document the key and compatibility
policy, and disable uncontrolled automatic topic creation. A topic that “everyone can publish to”
eventually has no enforceable meaning.

| Decision | Default starting point | Change when |
|---|---|---|
| Key | Stable aggregate/entity ID | Ordering or skew requires another invariant |
| Cleanup | Time retention | Latest value per key is the intended model |
| Partitions | Measured peak plus headroom | Consumers or throughput exceed measured capacity |
| Naming | Domain + event family + contract generation | Platform convention mandates another form |

**Success signal:** a design review can state the owner, writer ACL, key invariant, replay window,
peak estimate, and migration plan. A topic name alone is not a design.

> **Key insight**: topic design packages application semantics with shared operational policy, so
> splitting or merging topics changes more than discoverability.

---

## 5. What breaks, and when not to share a topic

⚠️ Mixed sensitivity in one topic forces broad readers to receive restricted fields. Consumer-side
filtering is not authorization because the data has already crossed the boundary.

Do not share a topic when producers cannot agree on ownership, key semantics, compatibility, or
retention. Separate topics and integrate deliberately.

---

**Next**: [Schema Registry and Serialization](05_schema_registry_and_serialization.md)
