# Replication Defines the Durability Contract

> **Question:** when a producer receives success, which broker failures can the record survive?

## A partition can have copies on several brokers

Consider partition P2 of `orders` with replication factor `3`:

```text
producer ─────────────► broker 1: P2 LEADER [offset 51]
                                  │
                                  ├── replicate ──► broker 2: P2 FOLLOWER [offset 51]
                                  │
                                  └── replicate ──► broker 3: P2 FOLLOWER [offset 51]
```

The **replication factor (RF)** is the desired number of partition copies. One replica is the
**leader**: producers send writes to it, and consumers fetch from it. Followers copy the leader's
log so another broker can take over.

Three configured replicas do not imply that all three are currently caught up. Kafka tracks an
**in-sync replica set (ISR)**—the replicas sufficiently caught up to participate in the normal
durability contract and safe leader election:

```text
replicas = {1, 2, 3}     desired placement
ISR      = {1, 2}        current caught-up set; broker 3 is behind
```

RF describes topology. ISR describes current health.

## Admission and acknowledgment are separate decisions

Suppose the topic uses `min.insync.replicas=2` and the producer uses `acks=all`.

First, the leader asks whether the current ISR is large enough to admit the write. Then, if admitted,
`acks=all` waits for every replica currently in the ISR.

### All three replicas are in sync

```text
configuration: RF=3, ISR={1,2,3}, minISR=2, acks=all

1. admit?      ISR size 3 >= 2                         yes
2. append      broker 1 writes offset 51
3. replicate   broker 2 writes 51; broker 3 writes 51
4. acknowledge all current ISR replicas have 51       producer sees success
```

### One follower falls behind

```text
configuration: RF=3, ISR={1,2}, minISR=2, acks=all

1. admit?      ISR size 2 >= 2                         yes
2. append      broker 1 writes offset 52
3. replicate   broker 2 writes 52
4. acknowledge both current ISR replicas have 52      producer sees success
```

Kafka does not wait for broker 3 because it is no longer in the ISR. It does wait for two replicas,
not because `minISR=2` means “wait for two,” but because the current ISR happens to contain two.

### The ISR falls below the minimum

```text
configuration: RF=3, ISR={1}, minISR=2, acks=all

1. admit?      ISR size 1 < 2                          no
2. result      write rejected; producer sees a replica error
```

Kafka chooses write unavailability over claiming the configured durability level. Depending on
when ISR state changes, the producer can see `NotEnoughReplicas` or
`NotEnoughReplicasAfterAppend` and must treat the outcome as a failed/uncertain attempt according to
its retry and idempotency policy.

## Read the durability matrix

| ISR | Producer setting | Result | Meaning |
|---|---|---|---|
| `{1,2,3}` | `acks=all`, `minISR=2` | accept; wait for 1, 2, and 3 | all current ISR copies confirm |
| `{1,2}` | `acks=all`, `minISR=2` | accept; wait for 1 and 2 | durability reduced but policy still met |
| `{1}` | `acks=all`, `minISR=2` | reject | policy refuses a single-copy success |
| `{1}` | `acks=1` | leader acknowledgment can succeed | durability is weaker, and the consumer-visible committed boundary cannot advance while ISR remains below `minISR` |

The [producer `acks` configuration](https://kafka.apache.org/43/configuration/producer-configs/#producerconfigs_acks)
and [topic `min.insync.replicas` configuration](https://kafka.apache.org/43/configuration/topic-configs/#topicconfigs_min.insync.replicas)
define these two halves of the contract.

> **The near-miss:** replication factor is not the number of replicas that acknowledged this write.
> Combine RF, current ISR, `min.insync.replicas`, and producer `acks` before stating a durability
> claim.

## Safe leader election preserves the acknowledged prefix

Return to the healthy trace where brokers 1, 2, and 3 stored offset `51` before success. Broker 1
then fails:

```text
before failure                           after election

leader 1:   [ ... 51 ]   X               broker 2: LEADER [ ... 51 ]
follower 2: [ ... 51 ]   ─────────►      broker 3: ISR    [ ... 51 ]
follower 3: [ ... 51 ]
```

The controller can elect a caught-up replica, and the acknowledged record remains readable after a
short availability pause. If Kafka instead elects a replica not known to contain the committed
prefix, availability may return by losing acknowledged data. That is why unclean election is an
explicit data-loss policy, not a generic recovery switch.

Advanced Eligible Leader Replica (ELR) behavior refines candidate selection when the normal ISR is
empty. It depends on high-watermark and feature-version state and belongs in the
[cluster lifecycle runbook](../operations/04_deployment_upgrades_and_disaster_recovery.md#upgrade-eligible-leader-replicas-as-a-separate-feature),
not in the first replication model.

## KRaft manages metadata; brokers carry event bytes

Kafka also needs agreement about topic definitions, registered brokers, and which replica is leader.
The **KRaft metadata quorum** is the controller group that maintains that cluster metadata:

```text
CONTROL PLANE                              DATA PLANE

KRaft controllers                         brokers
├── topic orders exists                   ├── P2 record bytes
├── P2 replicas are {1,2,3}               ├── follower fetch
└── broker 1 leads P2                     └── producer/consumer traffic
```

Controllers decide and record who leads P2; they are not extra copies of P2's events. Losing
controller quorum blocks metadata changes and leader elections. Losing enough partition replicas
threatens the records themselves. Operations monitors and recovers those planes separately.

## Assemble the complete record path

The five Fundamentals chapters now fit into one causal sequence:

```text
1. producer creates record(key=ord-42, value=evt-151)
2. key bytes + partitioner choose orders/P2
3. P2 leader appends offset 51
4. followers in the ISR copy offset 51
5. acknowledgment policy is satisfied; producer receives success
6. group coordinator assigns P2 to billing-B
7. billing-B fetches offset 51 and performs its effect
8. billing-v1 commits next offset 52
9. retention keeps or later removes the record independently of that commit
```

Every step changes a different piece of state. That is the practical Kafka mental model:

- the key influences partition placement;
- the partition log owns the record and offset;
- replicas determine the broker-failure contract;
- the group assignment chooses the current reader;
- the committed offset stores that group's recovery position;
- the application owns the external side effect.

## Check your model

Given `RF=3`, `ISR={1,2}`, `minISR=2`, and `acks=all`:

1. The next write is admitted and waits for brokers 1 and 2.
2. If broker 2 leaves the ISR before the following write, ISR becomes `{1}`.
3. The following write is rejected because ISR size `1` is below `minISR=2`.

Changing only `acks` to `1` is not recovery. The producer may receive a leader-only acknowledgment,
but the record has fewer surviving copies and consumer-visible progress remains blocked while the
ISR is below `minISR`. Restoring an in-sync replica is what repairs the missing durability and
visibility.

## Where Fundamentals stops

You can now reason about where a record is stored, ordered, copied, read, and resumed. Building a
service still requires schema evolution, producer/consumer configuration, retries, shutdown,
idempotent effects, security, capacity, and observability.

Do not self-host Kafka merely to avoid a service fee if no team can own quorum, disks, upgrades,
security, and restore testing. A managed service can own cluster mechanics; it does not choose your
keys, event contracts, commit boundaries, or side-effect guarantees.

---

**Next:** [Application Design](../application_design/README.md)
