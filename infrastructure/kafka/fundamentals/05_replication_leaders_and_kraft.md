# Replication Separates an Acknowledged Write from a Durable Write

> **Who this is for**: engineers deciding which broker failures Kafka should survive.

## One acknowledged record, two outcomes

A partition leader accepts offset 51. With replication factor one, its disk failure loses the only
copy. With three replicas, `acks=all`, and `min.insync.replicas=2`, the broker first checks that at
least two replicas are in sync, then waits for every replica currently in that set to acknowledge.

---

## 1. Leaders serialize writes while followers copy the log

Each partition has one leader handling reads and writes and zero or more follower replicas. The
**in-sync replica set (ISR)** contains replicas sufficiently caught up for normal safe leadership.
Replication factor describes desired copies; ISR describes currently healthy copies.

```text
producer → broker 1: P2 leader, offset 51
                 ├→ broker 2: P2 follower (ISR)
                 └→ broker 3: P2 follower (ISR)
```

If broker 1 fails while followers remain in the ISR, the controller elects one of them. Kafka 4.3
also tracks **eligible leader replicas (ELR)**: replicas outside the current ISR that remain safe
because strict minimum-ISR rules prevented the high watermark from advancing past them. ELR is
enabled by default on new clusters since Kafka 4.1.

The election order makes the safety boundary concrete:

```text
ISR={2,3}, ELR={}   → elect broker 2 or 3
ISR={}, ELR={2}     → broker 2 is unfenced, so elect broker 2 safely
ISR={}, ELR={}      → no ordinary safe candidate; last-known-leader fallback is separate
```

The KRaft controller chooses from a non-empty ISR first, then an unfenced ELR. Only the configured
unclean-election fallback may then select the unfenced last known leader; that branch can lose data.
Availability during an election may pause; durability depends on what was safely replicated before
acknowledgment. [Kafka's ELR guide](https://kafka.apache.org/43/operations/eligible-leader-replicas/)
explains the feature and its upgrade boundary.

---

## 2. Three settings form one durability contract

`replication.factor=3` requests three copies. `min.insync.replicas=2` is the admission floor: the
broker rejects an `acks=all` write if fewer than two replicas are in the ISR. After admission,
`acks=all` waits for the full current ISR, not merely the configured minimum. Configuring only one
of the three does not express the full contract.

```text
RF=3, ISR={1,2,3}, minISR=2, acks=all
  → admit the write; wait for brokers 1, 2, and 3

RF=3, ISR={1}, minISR=2, acks=all
  → reject the write; wait for nobody
  → producer sees NotEnoughReplicas or NotEnoughReplicasAfterAppend
```

The second trace can fail before append or after the ISR shrinks during append, hence the two error
names. Either way, writes fail rather than pretend to meet the durability contract. This is a
deliberate availability-for-consistency trade. The
[producer `acks` reference](https://kafka.apache.org/43/generated/producer_config.html) and
[`min.insync.replicas` reference](https://kafka.apache.org/43/configuration/topic-configs/)
specify these two independent decisions.

---

## 3. KRaft protects cluster metadata, not event payloads

**KRaft** is Kafka's Raft-based metadata quorum. Controllers agree on topics, partition leadership,
and cluster configuration; brokers store partition data. Kafka 4.x does not use ZooKeeper; Kafka
4.0 was the [first ZooKeeper-free major release](https://kafka.apache.org/blog/2025/03/18/apache-kafka-4.0.0-release-announcement/).

Losing controller quorum prevents metadata changes and leader elections even if broker disks still
contain data. Losing partition replicas threatens event data even if the controllers are healthy.
Monitor these planes separately.

> **The near-miss**: a controller is not a database replica for topic contents. It coordinates
> metadata; partition replicas carry the events.

---

## 4. Success and failure signals

**Success signal:** topic description shows the intended replication factor and ISR count, and a
controlled broker stop elects a new leader while acknowledged records remain readable. A green
broker process count alone is a silent failure because partitions can be under-replicated.

⚠️ Do not confuse safe ELR election with unclean election. Enabling unclean leader election can
restore availability by electing a replica that is not known safe, losing acknowledged records.
Treat it as an explicit data-loss policy, not a generic recovery switch.

> **Key insight**: durability is an end-to-end acknowledgment policy across producer settings,
> replica health, and broker admission—not a property implied by “Kafka is replicated.”

---

## 5. When not to self-manage this layer

Do not self-host Kafka solely to avoid a service fee when the team cannot staff quorum, disk,
upgrade, security, and restore operations. A managed service can move those mechanics to a provider;
it does not remove application-level key, schema, offset, or idempotency decisions.

---

**Next**: [Application Design](../application_design/README.md)
