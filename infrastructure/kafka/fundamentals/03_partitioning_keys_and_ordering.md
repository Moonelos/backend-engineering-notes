# Keys Define the Ordering Boundary

> **Question:** when a topic has several partitions, which records must stay in the same sequence?

## More partitions create more independent logs

Imagine a production-shaped `orders` topic with three partitions:

```text
orders topic
├── P0: [0] [1] [2] ...
├── P1: [0] [1] [2] ...
└── P2: [0] [1] [2] ...
```

Each partition has its own offsets and append order. Different consumers can process P0, P1, and P2
at the same time. That parallelism is the reason to partition, but it also limits ordering: Kafka
does not create one order across all three logs.

Suppose three lifecycle records for `ord-42` are distributed without stable affinity:

```text
P0  [order.created]
P1  [order.cancelled] ───► consumer B finishes first
P2  [order.paid]      ───► consumer C finishes later
```

Nothing inside a partition is out of order. The producer placed related facts in different ordered
domains, so Kafka has no single sequence for `ord-42` to preserve.

## The key is the routing identity

For a keyed record, the producer client performs this decision before sending:

```text
business invariant       serialized key        partitioner       destination

one order stays ordered  "ord-42" as bytes  ─► choose among P0–P2 ─► P2
```

The **partitioner** is client logic that maps the serialized key and current topic metadata to a
partition. With a stable partition count, the same key bytes and compatible partitioner choose the
same partition:

```text
key=ord-42  order.created   ─┐
key=ord-42  order.paid      ├──► P2: [17 created] [18 paid] [19 cancelled]
key=ord-42  order.cancelled ─┘
```

Now one partition contains the order's lifecycle, so its consumer observes the broker's append
order `17 → 18 → 19`.

> **Exact guarantee:** Kafka orders records within a partition. A key is how the application chooses
> which records share that boundary.

Kafka does not infer real-world causality. If two independent services race to publish `paid` and
`cancelled`, the partition records whichever append reaches the leader first. A shared key gives one
observable Kafka order; it does not prove which business action happened first outside Kafka.

## Choose the key from the invariant

Ask: “Which records must one consumer observe in relative order?”

| Requirement | Starting key | Ordering boundary | Cost |
|---|---|---|---|
| One order lifecycle stays ordered | `order_id` | per order | a single large order cannot be split |
| One account ledger stays ordered | `account_id` | per account | a busy account can become hot |
| Independent telemetry samples | null or distribution key | no entity-order promise | maximum distribution |

Choose the smallest stable identity that contains the invariant. Keying by `customer_id` would
order all of one customer's orders together, but it would also serialize unrelated orders for a
high-volume customer.

A null key does not mean “random but permanently assigned.” Modern producers may keep a null-key
batch on one partition for efficiency and later choose another. Use a real key when stable affinity
matters.

## The bytes are part of the contract

Partitioners receive bytes, not the human-readable value shown in logs:

```text
producer A: UTF-8("ord-42")     = 6f72642d3432     ─► P2
producer B: UTF-8("ord-42")     = 6f72642d3432     ─► P2
producer C: UTF-8("v1:ord-42")  = 76313a6f72642d3432 ─► P0
```

Producer C changed the routing input even though a developer might describe all three keys as “the
order ID.” When several languages or client versions publish to one topic, test a fixture key and
verify the resulting partition before rollout.

## More partitions can change future placement

A partitioner chooses among the partitions visible at send time. If `orders` grows from three to
nine partitions, the mapping input changes:

```text
before expansion: key=ord-77 ─► P1   old history remains in P1
after expansion:  key=ord-77 ─► P6   new history begins in P6
```

Kafka does not move the old records to rebuild one lifetime sequence. If that split violates the
business invariant, expanding the topic is a migration, not an ordinary capacity toggle. The
application-design section develops the alternatives in
[Topic and Partition Design](../application_design/04_topic_and_partition_design.md).

## Hot partitions are a property of the key distribution

Ten evenly sized partitions do not guarantee even load. If one key carries half the traffic, its
partition can lag while the other nine remain mostly idle:

```text
P0  ████████████████████  key=celebrity-account
P1  ██
P2  ██
... ██
```

Splitting that key increases parallelism only by giving up its single-partition ordering. The
consumer then needs another way to protect concurrent state changes, such as versions or a database
transaction.

## Check your model

The order service publishes `order.created` and the warehouse publishes `order.packed`. They use the
same `order_id` text but different key serializers. Can Kafka promise per-order ordering?

Not yet. The producers must emit identical key bytes and use compatible partitioning behavior.
Service names, timestamps, or matching JSON fields do not affect placement unless they are actually
part of the serialized key used by the partitioner.

## Where this model stops

Choosing a partition says where records live. It does not say which process reads each partition,
where that process resumes after a crash, or whether an external effect runs twice. Those are
consumer-group responsibilities.

---

**Next:** [Consumer Groups Coordinate Ownership and Progress](04_consumer_groups_offsets_and_rebalancing.md)
