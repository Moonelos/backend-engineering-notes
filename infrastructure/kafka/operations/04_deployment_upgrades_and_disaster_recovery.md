# Upgrade and Recovery Require Explicit Cutoffs

> **Who this is for**: teams choosing managed Kafka or owning cluster lifecycle.

## Separate a reversible binary rollout from metadata finalization

Kafka 4.3 runs only in KRaft mode. Before targeting 4.3, the cluster must already be in KRaft with
software and metadata versions at least 3.3; Apache recommends taking older KRaft clusters through
3.9 first. A ZooKeeper cluster must be migrated before this procedure.

A rolling upgrade owns two different states:

```text
old binaries + old metadata version
  -> mixed binaries + old metadata version       reversible one broker at a time
  -> all 4.3 binaries + old metadata version     last easy rollback point
  -> all 4.3 binaries + metadata.version 4.3     finalized; metadata downgrade unsupported
```

The feature level, not the last restarted process, is the compatibility cutoff. Inspect and record
it before changing anything:

```bash
kafka-features.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties describe
```

Also capture topic health, controller quorum health, active/fenced broker counts, offline and
under-replicated partitions, group stability, producer/consumer error rates, p99 request latency,
and a canary record round trip. Stop if the source→4.3 path is absent from the exact Apache upgrade
guide or if the maintenance window cannot tolerate a broker rollback.

## Upgrade one broker, then earn the next restart

For each broker, one at a time:

1. Prefer a broker without critical partition leaders or move leadership according to the platform
   procedure. Confirm the remaining replicas satisfy the service's durability policy.
2. Stop that broker cleanly, install the 4.3 binary/configuration, and restart it. Do not change the
   metadata version.
3. Wait for the broker to become active and unfenced. Require controller quorum health, zero offline
   partitions, and under-replicated partitions to return to the recorded baseline.
4. Require replica fetch lag to converge, disk not to approach its safety limit, request/error/GC
   metrics to match the baseline, affected groups to stabilize, and the canary produce/consume to
   succeed with expected authorization.
5. Only after the observation window passes may the next broker stop.

A restart command returning successfully is not a gate. The cluster must recover its data plane and
control plane between brokers. Pause the rollout if ISR does not recover, metadata lag grows,
controllers churn, client errors rise, or latency breaches the agreed bound.

Before finalization, a faulty 4.3 broker can be stopped and replaced with the recorded old binary and
config while the metadata feature remains old. Roll back one broker at a time through the same
health gates. If new application features already depend on 4.3 behavior, roll those applications
back before brokers; binary compatibility does not make an application dependency disappear.

When every broker runs 4.3 and the full observation window passes, inspect state again and make the
cutoff a separate approved change:

```bash
kafka-features.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties describe

kafka-features.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties upgrade --release-version 4.3

kafka-features.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties describe
```

The last output must show `metadata.version` at the 4.3 feature level. Kafka 4.3 contains metadata
changes, so Apache explicitly does **not** support downgrading cluster metadata from it. After this
command, “put the old binaries back” is not a valid rollback plan; recovery is forward repair or
restore into a compatible cluster from tested backups. Never finalize merely to make the dashboard
look uniform.

These constraints and the command are from the Apache Kafka 4.3
[upgrade guide](https://kafka.apache.org/43/getting-started/upgrade/).

## Regional recovery is a different state transition

A provider may own broker replacement, patching, and control-plane durability. Your team still owns
topics, keys, schemas, ACLs, quotas, client compatibility, lag, replay, and downstream idempotency.
State the recovery-time objective (RTO), recovery-point objective (RPO), regional failure model, and
who can declare failover before choosing topology.

MirrorMaker or provider replication copies records asynchronously. Consumer offsets, topic configs,
ACLs, schemas, and external effects need explicit treatment. Suppose `eu-primary` replicates to
`eu-replica`, billing checkpoints are copied every 30 seconds, schemas retain their identifiers, and
the payment provider deduplicates by `event_id`:

```text
10:00:00 primary orders offset=1200; replica offset=1198; copied group offset=1195
10:00:05 primary region is lost
10:00:20 operator freezes producers and declares failover
10:00:35 schema/ACL/config checks pass; consumers resume at copied offset=1195
          1195..1198 may run again; 1199..1200 are absent
10:01:10 producers switch to replica; first accepted write proves recovery
```

The measured RPO is two missing records, not the 30-second checkpoint interval. The RTO is 65
seconds from loss to first accepted write. Replaying 1195–1198 is expected; downstream idempotency
must collapse those duplicates.

On failback, stop writes, replicate the replica's new tail to the repaired primary, verify schemas,
ACLs, topic configs, and offsets, then move producers before consumers. Running both sides writable
creates two histories no offset translation can safely order.

**Success signal:** a game day restores declared event flows within RTO, measures actual RPO, and
proves idempotent resume. A replicated topic count alone is insufficient. Use the process boundaries
in [Testing Kafka Services](../reliability/05_testing_kafka_services.md).

## What breaks, and when not to self-host

⚠️ An untested restore commonly discovers missing schemas, ACLs, offsets, or credentials only after
the records have been copied. Restore and verify the
[schema registry](../application_design/05_schema_registry_and_serialization.md) before consumers.

Do not self-host when no team owns 24/7 storage, quorum, upgrade, certificate, and restore duties.

---

**Next**: [Configuration and Topic Administration](05_configuration_and_topic_administration.md)
