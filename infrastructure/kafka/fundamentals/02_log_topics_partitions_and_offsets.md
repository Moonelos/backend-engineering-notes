# A Kafka Topic Is a Set of Retained Ordered Logs

> **Who this is for**: engineers who completed the first event round trip or need Kafka's storage model.

## Worked trace: two records, one durable position

Suppose `orders` has two partitions. Records with key `customer-7` land in partition 1:

```text
partition 0: [offset 0: customer-2/order-A]
partition 1: [offset 0: customer-7/order-B] [offset 1: customer-7/order-C]
                                                   ↑
consumer group billing-v1 next position:           1
```

A **consumer group** is a named logical subscription: its members share the work and its saved
position survives any one process. After billing processes order B and commits offset `1`, Kafka
retains B; the commit says “the next record this group should read is offset 1.” It is not an
acknowledgment that deletes B. [Consumer Groups](04_consumer_groups_offsets_and_rebalancing.md)
develops membership and recovery later.

---

## 1. A retained log solves independent reading and replay

If reading deleted data, analytics and fraud detection would race billing for the same event. A
Kafka **log** is an append-only sequence: producers append records, while retention—not consumption—
eventually removes them. Each consumer group owns an independent position.

> **The near-miss**: a Kafka topic looks like a queue because producers send and consumers receive.
> The analogy stops at deletion: ordinary consumer reads do not remove records.

---

## 2. Partitions create both parallelism and an ordering boundary

A topic is split into partitions so different brokers and consumers can work in parallel. Every
partition has its own offset sequence. Kafka orders records inside one partition, never across the
whole topic.

```text
P0: 0 → 1 → 2
P1: 0 → 1 → 2 → 3
```

There is no meaningful comparison between P0 offset 2 and P1 offset 2. If two events must preserve
relative order, they must use a key that routes them to the same partition.

---

## 3. Retention and compaction answer different cleanup questions

**Time/size retention** removes old log segments after a duration or byte limit. **Log compaction**
eventually preserves the latest value per key, plus tombstones long enough to propagate deletion.
Neither is immediate, record-by-record garbage collection.

For `customer-profile`, compaction can reduce:

```text
(c7,v1) (c9,v1) (c7,v2) → eventually (c9,v1) (c7,v2)
```

Compaction is suitable for rebuilding latest keyed state. It is not suitable when every historical
transition is part of the business record.

---

## 4. Lag measures distance, not elapsed time

**Consumer lag** is approximately `log-end-offset - committed-offset` per partition. Ten records of
lag could mean milliseconds or hours depending on arrival and processing rates. Monitor both lag
and the age of the oldest unprocessed event when latency matters.

**Success signal:** given any consumed record, you can name its `(topic, partition, offset)` and the
consumer group's next committed offset. If a dashboard shows only a topic-wide offset, the model is
silently hiding the partition dimension.

> **Key insight**: partitions are not merely a scaling knob; they define which events can be ordered
> together and the unit of ownership, recovery, and lag.

---

## 5. What breaks, and when not to use Kafka as storage

⚠️ A consumer that resumes from an offset already deleted by retention encounters an out-of-range
position and must follow its reset policy, potentially skipping to the end or replaying from the
earliest available record.

Do not treat Kafka as the only system of record for mutable entities requiring ad hoc queries,
constraints, or indefinite authoritative history. Use a database or object store for that job and
Kafka for the event flow or change log.

---

**Next**: [Partitioning, Keys, and Ordering](03_partitioning_keys_and_ordering.md)
