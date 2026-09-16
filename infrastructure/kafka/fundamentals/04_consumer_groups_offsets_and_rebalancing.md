# Consumer Groups Coordinate Ownership and Progress

> **Question:** how do several consumer processes share partitions and resume safely after one
> disappears?

## A group turns partitions into units of work

The `orders` topic has three partitions. Billing runs two consumer processes with the same group ID,
`billing-v1`:

```text
TOPIC                         GROUP billing-v1

orders P0 ─────────────────► billing-A
orders P1 ─────────────────► billing-A
orders P2 ─────────────────► billing-B
```

The **group coordinator**, a broker-side component, maintains the membership and assignment. Inside
one conventional consumer group, each partition has at most one active owner. A consumer can own
several partitions; one partition is not split between several active consumers.

Add a third billing consumer and the coordinator can assign one partition to each. Add a fourth and
one consumer must remain idle because only three partitions exist.

Fraud detection uses a different group ID, `fraud-v1`:

```text
orders P0 ──┬──────────────► billing-v1 owner
            └──────────────► fraud-v1 owner
```

The groups do not steal records from each other. Each group gets its own assignment and committed
positions over the same retained partitions.

## Processing has four distinct steps

Follow billing-A handling offset `8` from P0:

```text
broker log         consumer process              external payment API       group state

[P0 offset 8] ──► 1. fetch
                  2. process ──────────────────► charge ord-42
                  3. receive success
                  4. commit next offset 9 ────────────────────────────────► P0 = 9
```

The external API knows whether the charge happened. Kafka knows only the group's committed next
offset. Those are separate systems, so there is a gap between the business effect and the commit.

### Crash after the effect but before the commit

```text
fetch offset 8 → charge succeeds → PROCESS CRASHES → commit 9 never happens
                                                │
replacement owner reads committed position 8 ◄─┘
                                                │
                                                └─► offset 8 runs again
```

This produces **at-least-once processing**: Kafka avoids silently skipping offset `8`, but the
business effect may be attempted again. Use a stable operation identity such as `charge:evt-108`
at a durable idempotency boundary so the second attempt returns the first result instead of charging
twice. The implementation belongs in
[Durable Consumer-Effect Idempotency](../reliability/02_durable_consumer_effect_idempotency.md).

### Commit before the effect creates the opposite failure

```text
fetch offset 8 → commit 9 → PROCESS CRASHES → charge never happens

replacement owner resumes at 9, so offset 8 is skipped
```

Committing early can trade duplicates for lost work. “The lag is zero” therefore does not prove
that the business effects completed.

> **The near-miss:** one partition owner at a time means exclusive ownership during an assignment.
> It does not mean one execution for all time.

## A rebalance changes ownership, not progress

A **rebalance** changes assignments when consumers join, leave, fail, or change subscriptions.
Suppose billing-A disappears:

```text
BEFORE                              AFTER

P0 → billing-A                      P0 → billing-B
P1 → billing-A       rebalance      P1 → billing-C
P2 → billing-B      ─────────►      P2 → billing-B

committed P0 = 9                    committed P0 = 9   unchanged
committed P1 = 14                   committed P1 = 14  unchanged
committed P2 = 21                   committed P2 = 21  unchanged
```

The coordinator moves partition ownership but does not invent progress. The new P0 owner resumes at
`9` because that is the group's last durable checkpoint for P0. Records fetched only into
billing-A's memory are fetched again when necessary.

This separation is the key to recovery:

- **assignment state** answers “who may read P0 now?”;
- **committed position** answers “where should that owner resume?”;
- **business-effect state** answers “did the downstream action already happen?”

Kafka coordinates the first two. The application must reconcile the third.

## Polling proves the owner is still making progress

A consumer polls for records, processes them, and polls again. If processing blocks longer than the
configured maximum interval, the group can treat that member as failed and reassign its partitions:

```text
t=0m   billing-A polls P0 offset 9 and starts a slow call
t=5m   maximum poll interval is exceeded
t=6m   rebalance assigns P0 to billing-B; billing-B resumes from committed position
t=8m   billing-A returns, but it no longer safely owns P0
```

A production loop must bound work, maintain polling, pause partitions when downstream capacity is
full, and stop committing after ownership is revoked. See
[Processing Loops, Backpressure, and Shutdown](../application_design/03_processing_loops_backpressure_and_shutdown.md)
for the implementation.

Kafka's newer consumer rebalance protocol changes assignment mechanics and callback behavior, but
not the beginner model above. Treat migration as an operational rollout using the
[consumer-protocol runbook](../operations/04_deployment_upgrades_and_disaster_recovery.md#change-consumer-protocols-as-a-separate-rollout).

## Lag is per group and partition

For P0:

```text
log end = 120
billing-v1 committed = 100
billing-v1 lag = 20

fraud-v1 committed = 117
fraud-v1 lag = 3
```

Topic traffic is shared, but backlog belongs to a group. Aggregate lag can also hide one hot
partition, so inspect the partition distribution when total lag rises.

## Check your model

P0 is committed at `12`. Its owner completes the external effect for offset `12` and crashes before
committing `13`. A rebalance assigns P0 to another process.

The new owner starts at `12`, because assignment changed but the committed position did not. The
effect is attempted again. A durable idempotency key can collapse the duplicate; starting at `13`
would risk hiding unfinished work.

Now change one condition: the old owner committed `13` before performing the effect. The new owner
starts at `13` and offset `12` is lost from the application's processing history. That is why commit
ordering is a correctness decision, not bookkeeping.

## Where this model stops

Groups recover from consumer-process failure because the broker log remains available. They do not
explain what happens when the broker storing a partition fails. Replication supplies that next
layer.

Conventional groups are also a poor fit when many workers must concurrently claim individual
records from one partition with per-record acknowledgment. Evaluate
[share groups](../ecosystem/03_share_groups_and_queue_semantics.md) or a work queue for that shape.

---

**Next:** [Replication Defines the Durability Contract](05_replication_leaders_and_kraft.md)
