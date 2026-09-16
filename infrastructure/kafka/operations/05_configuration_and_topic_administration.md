# Kafka Administration Needs a Bound, a Signal, and a Recovery Path

> **Who this is for**: engineers creating topics or changing Kafka policy in a shared cluster.

## Establish effective state before mutation

With authenticated settings in `admin.properties`, create an application-owned topic and inspect
what actually became effective:

```bash
kafka-topics.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --create \
  --topic orders.events.v1 --partitions 15 --replication-factor 3 \
  --config cleanup.policy=delete --config retention.ms=604800000 \
  --config min.insync.replicas=2

kafka-topics.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --describe --topic orders.events.v1

kafka-configs.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --entity-type topics \
  --entity-name orders.events.v1 --describe
```

The success signal is 15 partitions, replication factor 3, full in-sync replica (ISR) membership,
and explicit seven-day retention and minimum ISR 2. “Topic already exists” is not success: auto
creation may have installed unsafe defaults.

A topic override wins when present; otherwise the broker default becomes effective:

```text
broker default retention.ms=2592000000 (30 days)
topic override retention.ms=604800000   (7 days)
effective orders.events.v1 retention    = 7 days
delete topic override
effective orders.events.v1 retention    = 30 days
```

Record the explicit value and inherited fallback. Removing an override is a rollback only when the
fallback is known.

## Mutable retention has a symmetric rollback

```bash
kafka-configs.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --entity-type topics \
  --entity-name orders.events.v1 --alter \
  --add-config retention.ms=1209600000

kafka-configs.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --entity-type topics \
  --entity-name orders.events.v1 --describe
```

Publish a canary and watch disk growth and segment deletion for the agreed window. Roll back to the
recorded seven-day override with `--add-config retention.ms=604800000`; do not use
`--delete-config retention.ms` unless inheriting the broker default is intended. Check each broker
property's dynamic update mode in the Kafka 4.3
[broker configuration reference](https://kafka.apache.org/43/configuration/broker-configs/) before
assuming a restart is unnecessary.

## Partition expansion is irreversible in place

Expansion increases future parallelism; it does not redistribute old records, and default key
placement can change because the partition count changed. It can also expose an `auto.offset.reset`
`latest` discovery window to existing consumers. Bound the change to one topic, verify every
consumer is ready, and stop key-sensitive producers if a placement change would violate ordering.

```bash
kafka-topics.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --describe --topic orders.events.v1

kafka-topics.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --alter \
  --topic orders.events.v1 --partitions 18

kafka-topics.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --describe --topic orders.events.v1
```

Require `PartitionCount: 18`, leaders for partitions 15–17, full ISR, client metadata refresh,
stable consumer assignments, and a canary routed to each new partition. Watch lag and per-partition
traffic. Kafka cannot reduce the count. If clients fail, stop or roll back those clients and avoid
new partitions; durable recovery is a new topic with the original partitioning plus deliberate
dual-write/backfill and cutover. Never manually expand Kafka internal topics.

## Replica reassignment is reversible only with the saved assignment

Use an explicit plan so the blast radius is reviewable. This example moves only partition 0 and 1;
replace broker IDs only after confirming rack and disk capacity:

```json
{
  "version": 1,
  "partitions": [
    {"topic": "orders.events.v1", "partition": 0, "replicas": [2, 3, 4]},
    {"topic": "orders.events.v1", "partition": 1, "replicas": [3, 4, 5]}
  ]
}
```

Save it as `orders-reassignment.json`. Execute with throttles; the command prints the current
assignment—save that JSON as `orders-reassignment-before.json`, because it is the rollback plan.

```bash
kafka-reassign-partitions.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --execute \
  --reassignment-json-file orders-reassignment.json \
  --throttle 50000000 --replica-alter-log-dirs-throttle 100000000

kafka-reassign-partitions.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --verify \
  --reassignment-json-file orders-reassignment.json
```

During the move, require replica fetch lag to fall, disk to remain below the safety bound, client
latency/error objectives to hold, and no offline partitions. If lag is flat because incoming bytes
exceed 50 MB/s, pause other moves or rerun `--execute --additional` with a reviewed higher throttle.
If health degrades, execute the saved before-plan to move replicas back; this is another data move,
not an instant cancel. Completion means every partition reports completed, ISR equals the target
replicas, and `--verify` reports that broker/topic throttles were cleared. Describe configs to catch
forgotten throttles.

## Quotas need a canary identity and an observed throttle

Apply the narrow `(user, client-id)` override before a user-wide or default quota:

```bash
kafka-configs.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --alter \
  --add-config 'producer_byte_rate=1048576,consumer_byte_rate=2097152,request_percentage=50' \
  --entity-type users --entity-name orders-api \
  --entity-type clients --entity-name orders-api-quota-canary

kafka-configs.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --describe \
  --entity-type users --entity-name orders-api \
  --entity-type clients --entity-name orders-api-quota-canary
```

Run a bounded load from that client ID. Success is the described values plus nonzero client throttle
time near the limit while unrelated identities and business latency remain healthy. Too-low quotas
usually appear as latency, not rejected requests. Roll back the exact override:

```bash
kafka-configs.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --alter \
  --delete-config 'producer_byte_rate,consumer_byte_rate,request_percentage' \
  --entity-type users --entity-name orders-api \
  --entity-type clients --entity-name orders-api-quota-canary
```

Describe again; an empty narrow override means precedence returns to any user/client default, which
must also be known. The complete quota precedence and CLI forms are in Kafka 4.3's
[basic operations guide](https://kafka.apache.org/43/operations/basic-kafka-operations/).

## Deletion is a migration, not an undoable CLI convenience

Before deleting `orders.events.v1`, confirm it is application-owned and `delete.topic.enable` is
enabled. Freeze producers by deployment and ACL, wait for consumers to reach the chosen end offsets,
record configs/ACLs/partition assignment/group offsets, export schemas, and prove the backup by
restoring representative oldest and newest records to a disposable topic. Prefer retiring the name
for a full rollback window before deletion.

```bash
kafka-topics.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --describe --topic orders.events.v1

kafka-consumer-groups.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --describe --group billing-v1

kafka-topics.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --delete --topic orders.events.v1

kafka-topics.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --describe --topic orders.events.v1
```

Deletion is complete only when describe reports the topic absent, metadata no longer lists it, and
storage cleanup progresses. If the command returns but the topic persists, check controller health
and `delete.topic.enable`; do not repeatedly recreate the same name during deletion.

There is no undelete. Recovery recreates the recorded configuration/ACLs and restores records from
the tested backup; original partition offsets may not be preserved, so consumers need an explicit
reset or a new group after validation. If exact history or offsets matter, use a new topic and
controlled migration instead of deletion.

## Production boundary

Store desired topics, ACLs, quotas, and overrides in reviewed configuration, deny uncontrolled auto
creation, and reconcile drift. Keep emergency CLI access audited. The change record for every
procedure contains before/after describes, canary outcome, metric window, owner, and recovery command.

⚠️ Never delete, expand, or manually reassign Kafka internal topics such as
`__consumer_offsets`, `__transaction_state`, `__share_group_state`, or `__cluster_metadata`.

---

**Next**: [Tiered Storage](06_tiered_storage.md)
