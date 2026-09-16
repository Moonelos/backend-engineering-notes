# Tiered Storage Changes What “Retained” Means

> **Who this is for**: operators deciding whether long replay windows belong on broker disks or an
> external storage tier. This note targets Apache Kafka 4.3.x in KRaft mode.

## Choose it for replay economics, not ordinary tail traffic

Kafka normally keeps every retained segment on broker-local disks. A one-year replay window then
sizes every broker for a year of replicated history even though most consumers read near the tail.
Tiered storage keeps recent segments locally and copies completed segments to external storage;
brokers can fetch old segments remotely when a replay needs them.

That trade is useful when retained history dominates local disk and remote replay can tolerate
higher, provider-dependent latency. It is a poor default when:

- nearly all retained data is frequently reread and predictable low latency matters more than disk cost;
- the topic is compacted—Kafka 4.3 tiered storage does not support compacted topics;
- no production-quality external storage plugin, support owner, durability contract, or restore drill exists; or
- remote request/egress cost and replay concurrency erase the local-disk saving.

Estimate both tiers before enabling it. For 10 MiB/s ingress, replication factor 3, 24 hours local,
and 30 days total, raw payload is about 844 GiB of logical local history, about 2.47 TiB across the
three local replicas, and 25.3 TiB of logical total history before compression and overhead. Size
the remote tier against the chosen plugin/provider's durability model rather than blindly applying
Kafka's local replication factor. Tiering reduces broker-disk history; it does not remove network,
index cache, active-segment, replication, metadata, or recovery headroom. Measure compressed bytes
and segment shape under the real workload rather than provisioning from the raw estimate.

## Kafka delegates remote object lifecycle to a plugin

Apache Kafka supplies the `RemoteStorageManager` interface but no production implementation. Every
broker loads an external implementation and its dependencies from
`remote.log.storage.manager.class.name` and `remote.log.storage.manager.class.path`. The plugin owns
copy, fetch, and deletion against the remote system; its credentials, retry behavior, encryption,
consistency, cost, and support lifecycle are part of the Kafka service contract.

Kafka also needs strongly consistent metadata describing remote segments. Its default
`RemoteLogMetadataManager` stores that state in the internal `__remote_log_metadata` topic. The
configured metadata listener must work from every broker, and that internal topic needs adequate
replication and minimum in-sync replicas. Do not treat the object bucket alone as a recoverable
backup: objects without consistent remote-segment metadata are not a proven Kafka restore. Keep
`remote.log.metadata.topic.retention.ms` longer than the maximum tiered-topic retention, as Kafka's
configuration reference requires, and prevent provider lifecycle rules from deleting objects before
Kafka's total retention does.

The causal path for one completed segment is:

```text
leader rolls local segment 42
  -> RemoteStorageManager copies segment + indexes to external storage
  -> remote-segment metadata becomes durable
  -> only then may local retention delete local segment 42
  -> an old-offset fetch consults metadata and reads segment 42 remotely
  -> total retention expires it and the plugin deletes the remote objects/metadata
```

The active segment remains local. `local.retention.*` controls when already copied segments may
leave broker disk; `retention.*` controls the whole local-plus-remote history. Copy is therefore a
durability gate, not merely an asynchronous cache fill.

## Configure brokers first, then one canary topic

Broker configuration is a rolling deployment because the feature is disabled by default:

```properties
remote.log.storage.system.enable=true
remote.log.storage.manager.class.name=com.example.kafka.storage.ProductionRemoteStorageManager
remote.log.storage.manager.class.path=/opt/kafka/plugins/remote-storage/*
remote.log.metadata.manager.listener.name=INTERNAL
remote.log.storage.manager.impl.prefix=rsm.config.
rsm.config.bucket=kafka-prod-eu-remote-log
```

The class name is deliberately a placeholder: select a maintained plugin and follow its exact
configuration. Validate artifact provenance and compatibility with Kafka 4.3, mount it identically
on every broker, scope bucket credentials to the required prefix/actions, encrypt in transit and at
rest, and keep secrets outside `server.properties`. A plugin initialization failure can terminate a
broker, so deploy broker by broker through the health gates in the
[upgrade runbook](04_deployment_upgrades_and_disaster_recovery.md).

Only after all brokers are healthy should one non-compacted, noncritical canary topic opt in:

```bash
kafka-configs.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --alter \
  --entity-type topics --entity-name replay-canary.v1 \
  --add-config 'remote.storage.enable=true,local.retention.ms=86400000,local.retention.bytes=107374182400,retention.ms=2592000000,retention.bytes=3221225472000'

kafka-configs.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --describe \
  --entity-type topics --entity-name replay-canary.v1
```

Here the canary targets one day or 100 GiB locally and 30 days or 3 TiB across both tiers; time and
size limits each act as a bound, so whichever makes a segment eligible first governs. Kafka requires
effective local limits to be no greater than total limits. An unset local value defaults to the
corresponding total retention and yields no intentional shorter local window.

These fields and limits come from Kafka 4.3's
[tiered-storage guide](https://kafka.apache.org/43/operations/tiered-storage/) and
[tiered-storage configuration reference](https://kafka.apache.org/43/configuration/tiered-storage-configs/).

## Prove copy, eviction, remote read, and remote delete

Use a disposable canary and shortened segment/retention settings only outside production. The
production acceptance drill should still exercise the following state transitions with normal
settings and provider-side evidence:

1. Produce uniquely identified records until at least two segments roll. Record earliest/latest
   offsets and object count/bytes.
2. Require remote copy bytes to rise, copy lag/backlog to return to baseline, copy errors to remain
   zero, and corresponding remote objects plus metadata to exist.
3. Wait until a copied segment leaves local disk under `local.retention.*`. Confirm local usage falls
   without the topic's log-start offset advancing past those records.
4. Consume the recorded old offset. Require the exact record, nonzero remote-fetch request/bytes,
   bounded remote-read latency, and zero remote-fetch errors.
5. In a disposable topic only, shorten total retention beyond that segment. Require log-start offset
   to advance and the plugin/provider's remote delete count or object inventory to shrink after the
   retention task runs.

Kafka 4.3 publishes per-topic `RemoteCopyBytesPerSec`, `RemoteCopyErrorsPerSec`,
`RemoteCopyLagBytes`, `RemoteCopyLagSegments`, `RemoteFetchBytesPerSec`,
`RemoteFetchRequestsPerSec`, `RemoteFetchErrorsPerSec`, `RemoteDeleteRequestsPerSec`,
`RemoteDeleteErrorsPerSec`, `RemoteDeleteLagBytes`, and `RemoteDeleteLagSegments`;
remote-reader queue/idle metrics expose read saturation. `RetentionSizeInPercent` tracks local plus
remote pressure against total bytes, while `LocalRetentionSizeInPercent` tracks broker-disk
pressure. Export plugin-specific retry age and object-store latency as well: an aggregate byte rate
alone cannot prove that the oldest outstanding copy or deletion is making progress.

## Capacity and replay now have two bottlenecks

Keep enough local disk for the active segment, the local window, replicas catching up, temporary
copy backlog, indexes/cache, and failure headroom. A remote outage prevents safe local eviction of
uncopied segments, so local disks must survive the declared outage plus incoming writes:

```text
emergency local bytes
  >= normal local window
   + compressed ingress/sec * tolerated remote outage sec * replication factor
   + rebalance/catch-up and safety margin
```

Remote replay capacity is separate. Bound concurrent backfills so remote reader queues, object-store
rate limits, broker network, and egress spend remain safe. A one-year retention promise is hollow if
restoring one day already violates the recovery-time objective. Load-test tail reads and old-offset
reads simultaneously; pass only when ordinary consumers remain within their latency/freshness
objectives and the replay finishes within its deadline.

## Failure signals must lead to different recovery actions

| Symptom | Likely boundary | Diagnose | Recovery and proof |
|---|---|---|---|
| remote copy bytes stop; copy errors/backlog age rise | plugin credentials, endpoint, quota, or remote outage | correlate plugin logs, provider errors, token expiry, and network; check every broker | restore access or provider capacity; verify oldest backlog age falls and new segments copy before local disk reaches the stop-write bound |
| broker disks grow while remote objects exist | metadata publication or local-retention mismatch | inspect `__remote_log_metadata` health and effective local/total configs | repair metadata quorum/config; verify copied segments become locally eligible and disk pressure falls |
| old reads slow; reader queue rises | remote read concurrency, cache, or object-store latency | compare fetch errors/latency, queue size, cache hit behavior, and provider throttling | cap replay concurrency or add reader/provider capacity; verify tail SLO and replay deadline together |
| remote fetch returns errors for a known retained offset | missing/corrupt object, metadata mismatch, key/permission failure | identify exact topic-partition/base offset and compare metadata with provider inventory | restore object/key/access using the plugin procedure; replay that offset and verify its checksum/business identity |
| deletes stop; total retention pressure exceeds 100% | remote deletion/metadata task or legal-hold conflict | compare log-start offset, delete errors, inventory age, and hold policy | repair delete permission/task or revise retention explicitly; verify expired objects disappear without deleting retained offsets |
| broker will not start after plugin rollout | classpath, binary compatibility, or plugin initialization | inspect startup exception and compare artifact/config across brokers | restore the previous broker binary/plugin/config at the pre-topic-enable gate; restart one broker and pass cluster health before proceeding |

Do not delete remote objects manually to relieve cost or pressure. That bypasses Kafka metadata and
turns a later replay into corruption or missing data.

## Disablement has two materially different meanings

To stop new copies but preserve existing remote segments for reads, keep remote storage enabled and
set `remote.log.copy.disable=true`. Kafka 4.3 also requires local retention to equal total retention,
or use `-2` to inherit it, because the former short local window no longer has new remote copies:

```bash
kafka-configs.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --alter \
  --entity-type topics --entity-name replay-canary.v1 \
  --add-config 'remote.storage.enable=true,remote.log.copy.disable=true,local.retention.ms=-2,local.retention.bytes=-2'
```

Verify new segments remain local, old remote reads still work, and projected local capacity covers
total retention. Rollback is to restore the recorded local limits and set copy-disable false, then
prove backlog catch-up before shrinking local retention again.

Completely disabling a topic and deleting all remote logs is destructive:

```bash
kafka-configs.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --alter \
  --entity-type topics --entity-name replay-canary.v1 \
  --add-config 'remote.storage.enable=false,remote.log.delete.on.disable=true'
```

Use that only after a tested backup or after accepting loss of remote-only history. Verify remote
objects and metadata are deleted and the remaining local log-start offset matches the declared
replay boundary. There is no switch that recreates deleted remote history.

Finally, broker-level `remote.log.storage.system.enable=false` is not a shortcut. Kafka requires all
tiered topics to be disabled/deleted first and otherwise fails broker startup. Inventory topic
configs, prove none has `remote.storage.enable=true`, retain the plugin until cleanup is verified,
then roll the broker setting off one broker at a time.

> **Decision checkpoint:** if a 90-day replay replaces the 30-day requirement, local disk need not
> triple when local retention stays one day, but remote capacity/cost does and the 90-day record must
> be recoverable within the replay objective. If that remote-read proof or plugin ownership is
> missing, buy broker disk or shorten retention rather than claiming the longer recovery contract.

---

**Next**: [Ecosystem and Decisions](../ecosystem/README.md)
