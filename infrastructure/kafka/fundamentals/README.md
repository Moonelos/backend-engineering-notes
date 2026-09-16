# Kafka Fundamentals

> Learn Kafka by following one record through the system, then zooming in on the four decisions
> that determine its behavior: storage, routing, consumption, and durability.

## The map you will build

Start with this incomplete map. Each chapter makes one part precise:

```text
                         KAFKA CLUSTER

producer          topic partition               consumer group
   │                    │                              │
   │  record            │ ordered, retained log       │ fetch
   ├───────────────────►│                              │
   │                    │                              ▼
   │                    │                       consumer instance
   │                    │                              │
   │                    │◄─────────────────────────────┤ commit position
   │                    │
   │                    ├── leader replica
   │                    └── follower replicas
```

At the end, you should be able to narrate every arrow: who initiates it, which state changes, which
state does not change, and what happens when the actor fails halfway through.

## Reading path

| Step | Learner question | Outcome |
|---|---|---|
| [1. One record, end to end](01_first_event_round_trip.md) | What actually happens when a service sends a record? | Run the smallest complete round trip and identify every actor |
| [2. The retained log](02_log_topics_partitions_and_offsets.md) | Where does the record live after it is read? | Separate broker storage from each reader's position |
| [3. Keys and partitions](03_partitioning_keys_and_ordering.md) | Which records are ordered together? | Choose a key and state the exact ordering boundary |
| [4. Consumer groups](04_consumer_groups_offsets_and_rebalancing.md) | How do consumers share work and recover? | Trace ownership, commits, rebalances, duplicates, and lag |
| [5. Replication](05_replication_leaders_and_kraft.md) | When is a successful write durable? | Derive availability and durability from replicas, ISR, and acknowledgments |

The examples use an order domain, but they are not one continuously running physical cluster.
Chapter 1 uses a one-partition local topic so the first result is deterministic. Later chapters
introduce production-shaped, multi-partition scenarios explicitly and keep their layouts stable
inside each trace.

## What you need

- Basic programming concepts: a service can send and receive structured data.
- Ordinary shell and Docker usage for the runnable first chapter.
- No prior knowledge of messaging, distributed systems, replication, or Kafka.

## Where Fundamentals stops

Fundamentals explains the mechanics well enough to reason about a design. It does not yet teach
schemas, production client code, side-effect idempotency, security, sizing, or cluster operations.

- Continue to [Application Design](../application_design/README.md) to build a service.
- Continue to [Reliability](../reliability/README.md) before processing money, inventory,
  permissions, or another external side effect.
- Continue to [Operations](../operations/README.md) if your team owns the cluster.

