# Operations package review — 2026-09-16

Scope: `infrastructure/kafka/operations/README.md` and operations notes `01`–`05` only. Read for prerequisite and path context: `infrastructure/kafka/README.md`, `fundamentals/05_replication_leaders_and_kraft.md`, `reliability/05_testing_kafka_services.md`, and `application_design/05_schema_registry_and_serialization.md`. Findings and executable-claim counts below concern only the assigned operations files.

Audience used: backend engineers comfortable with processes, network failures, and database transactions (`infrastructure/kafka/README.md:49,71,101-105`), but not assumed to have prior Kafka operations expertise. Version baseline: Apache Kafka 4.3.x and Python 3.11+ (`infrastructure/kafka/README.md:5-6`).

Research: COMPLETE for the scoped operational claims checked below. Current Apache documentation identifies the 4.3 line and an upgrade page updated for 4.3.1; sources and remaining limits are listed at the end.

## Per-note review

# operations/README.md (20 lines)
ORDERING: role index; n/a; payoff n/a. Lines 9-15 give a complete lookup map, and lines 17-20 state the milestone, managed-service stop point, and condition for continuing to administration.
EXPLANATION: n/a; teach-back n/a (pure section index). Its outcome labels are concrete enough to audit the linked owners.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The index identifies each note's role and outcome rather than pretending to teach the mechanisms itself (`README.md:9-20`).

# operations/01_security_and_multitenancy.md (86 lines)
ORDERING: role implementation; FAIL; payoff absent/86. The note moves promptly from the three security layers (`01:5-9`) to a TLS/SASL client configuration (`01:19-37`) and ACL mutations (`01:39-57`), but never composes a bounded producer-and-consumer run whose success and denied operations can actually be observed. The negative outcomes at `01:59-70` are assertions, not an executable implementation path.
EXPLANATION: PASS; teach-back PASS (missing: none for the connection/action intersection). Problem: an authenticated producer may still be over-privileged (`01:5-9`). Owned decisions: broker trust, authenticated identity, and principal/action/resource authorization (`01:7-9,28-36,39-63`). Actors: `orders-api`, `billing-worker`, and the authenticated administrator (`01:15-16,39-40`). Transition/result: allowed topic/group operations and two named denied operations (`01:59-63`). Misconception boundary: a TLS handshake does not prove authorization (`01:68-70`). First failure/boundary: wildcard ACL compromise and hard-isolation tenants (`01:77-82`).
Summary: 0 critical, 1 high, 1 med, 0 low

FIX-HIGH: The implementation promise cannot be completed from the note — add the smallest composed verification using bounded broker/admin-property/CA/credential inputs, one actual produce, one consumer using `billing-v1`, the two negative operations, and exact observed success/authorization-failure output. Keep the present safe TLS and environment-secret choices (`01:19-37`).

FIX-MED: Credential rotation is prescribed as “overlapping validity” at `01:17`, but the shown SCRAM identity at `01:28-36` gives no rotation procedure, overlap carrier, verification, or rollback. Show the applicable mechanism (for example, a second principal with temporarily duplicated least-privilege ACLs) and the old-credential rejection signal; do not leave readers to infer that replacing one SCRAM secret automatically creates overlap.

RELATED: Candidate coverage finding “security and multitenancy” below: admin/API isolation and hard resource isolation reach only explained/mentioned depth (`01:65-66,81-82`).

# operations/02_capacity_planning_and_performance.md (70 lines)
ORDERING: role decision guide; PASS; payoff begins at 7/70 and reaches a decision by line 26. A named workload supplies the sizing inputs (`02:7-21`), the dominant recovery constraint changes the recommendation from 5 to 15 partitions (`02:23-26`), and storage/network/failure checks follow rather than precede that decision (`02:28-37`).
EXPLANATION: PASS; teach-back PASS (missing: none). Problem: raw ingress sizing omits retention, replication, egress, and the slowest consumer (`02:7-11`). Owned decision/state: the measured envelope table (`02:13-21`). Actor: the engineer measures per-partition broker and handler limits and runs the load test (`02:43-54`). Transition/result: a one-hour burst plus a 30-minute catch-up objective changes required capacity to 15 partitions (`02:23-26`). Misconception boundary: healthy-broker-only, tiny-record, or one-group tests validate the wrong envelope (`02:34-37,50-54`). First failure: disk headroom disappears during recovery (`02:61-66`).
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: This is a faithful decision carrier rather than a knob catalogue. Its arithmetic is internally consistent: 72 GB/1,800 s = 40 MB/s catch-up, 60 MB/s including live traffic, 15 partitions at 4 MB/s; 36.288 TB replicated storage becomes about 47.2 TB with 30% headroom and about 22.5 TB provisioned per broker at a 70% ceiling (`02:23-32`).

RELATED: Candidate coverage finding “capacity validation” below: the envelope is demonstrated, while the referenced test-harness owner describes where load tests fit but does not supply this production-shaped load test (`02:50-54`; `reliability/05_testing_kafka_services.md:36,82,86-88`).

# operations/03_observability_and_incident_response.md (93 lines)
ORDERING: role implementation; FAIL; payoff absent/93. The Prometheus rule artifact starts at line 32 and parses as YAML, but the note supplies no rule-validation command, installation/reload step, metric fixture, slow-handler injection, or observed firing output. The claimed implementation result at `03:75-77` therefore cannot be run from the note.
EXPLANATION: FAIL; teach-back PASS for correlated freshness diagnosis (missing: none), but the implementation scope is incomplete. Problem: lag has several distinct causes (`03:5-9`). Owned decision: combined lag/age and replica/disk alert predicates (`03:32-62`). Actors: exporter/application, Prometheus, and first responder (`03:27-30,64-73`). Transition/result: slow processing produces old records plus backlog and a labeled page (`03:64-76`). Misconception boundary: a green broker dashboard can hide a stopped consumer (`03:75-77`). First failure: a missing age series suppresses the joined alert (`03:67-68`). However, the promised coordinator/controller-health detection appears only in the triage list (`03:9,20`) and has no signal, rule, symptom-to-check mapping, or recovery.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: Assemble the monitoring implementation — include exact rule validation/reload steps, bounded fixture or injection inputs, observed pending/firing labels, and the separate `absent()` rule already required by `03:67-68`. This fixes the silent-green path and makes the success claim at `03:75-77` reproducible.

RELATED: Candidate coverage finding “broker/controller/coordinator incident detection” below owns the absent coordinator/controller mechanism rather than duplicating its severity here.

# operations/04_deployment_upgrades_and_disaster_recovery.md (73 lines)
ORDERING: role deep dive; PASS; payoff 5/73. The opening names the regional-failure constraint and the RTO/RPO/authority decisions before topology (`04:5-9`). The cross-cluster trace begins at line 30 and makes duplicate and missing ranges visible by line 46.
EXPLANATION: FAIL; teach-back FAIL (missing: upgrade-owned state, upgrade transition/result, rollback boundary, first upgrade failure). The disaster-recovery mechanism itself passes: copied records are insufficient (`04:24-28`), named primary/replica/checkpoint states transition through failure (`04:30-46`), dual-writable histories are ruled out (`04:48-51`), and a game day supplies the success boundary (`04:53-56`). In contrast, upgrades receive only “check supported paths, protocol compatibility, client versions, and feature gates” (`04:18-20`). Nothing shows which state changes when Kafka 4.3's metadata version is finalized, how rolling verification gates that action, or when rollback ceases to be possible.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: Candidate coverage finding “Kafka 4.3 rolling upgrades” below. Apache's 4.3 upgrade guide says to upgrade brokers one at a time, verify cluster behavior before `kafka-features.sh ... upgrade --release-version 4.3`, and states that metadata downgrade is not supported across the 4.3 metadata change. This is the central missing production mechanism, not a stale contradiction in the existing prose.

# operations/05_configuration_and_topic_administration.md (108 lines)
ORDERING: role reference with an implementation-led common path; PASS; payoff 5/108. The opening immediately scopes authenticated topic creation and effective-value inspection (`05:5-26`), then demonstrates override precedence before mutation (`05:30-49`). A dedicated contents map would improve lookup, but its absence is not a material barrier at this length.
EXPLANATION: FAIL; teach-back PASS for topic override/change/rollback (missing: none), but FAIL for the wider administration mechanisms. Problem: an accepted CLI response can conceal unsafe effective state (`05:22-24`). Owned state: explicit topic values and inherited fallback (`05:30-46`). Actor: authenticated administrator plus reviewed desired-state reconciliation (`05:7-8,85-86`). Transition/result: seven-day to fourteen-day retention with a recorded seven-day rollback (`05:53-67`). Misconception boundary: deleting an override is not restoration unless the inherited fallback is intended (`05:40-46,64-67`). First failure: under-replicated partitions or runaway disk growth make a completed command a failed rollout (`05:64-65,88-90`). Partition expansion, reassignment, quotas, and deletion, however, are only one-line rules (`05:76-83,94-104`); a reader cannot perform, verify, or recover those operations from this reference.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: Candidate coverage finding “topic administration beyond retention” below owns the underdeveloped operational mechanisms.

## Candidate mechanism coverage

These are inputs for the collection-wide coverage owner, not duplicate canonical findings.

| Mechanism | Required for operations promise | Achieved in assigned files | Evidence / missing depth |
|---|---|---|---|
| TLS/SASL identity plus ACL authorization | operationalized | demonstrated | Safe client config and ACL artifact plus positive/negative expected decisions (`01:19-70`), but no executable client verification, common authentication failure symptoms, revocation, or rollback. |
| Credential rotation | operationalized | mentioned | Overlapping validity is prescribed only (`01:17`); no state transition or recovery. |
| Multitenant admin/resource isolation | operationalized | explained | Admin/Connect surfaces and separate-cluster boundary are named (`01:65-66,81-82`), but quotas, admin ACLs, per-tenant keys, and isolation verification are not demonstrated. |
| Partition/storage/network/catch-up sizing | demonstrated | demonstrated | Named inputs, arithmetic, changed recovery constraint, failure-headroom checks (`02:7-37`). |
| Production-shaped capacity validation | operationalized | explained | Success criteria exist (`02:50-54`), but no runnable load/failure procedure or observed evidence. |
| Business freshness and consumer-lag alerting | operationalized | demonstrated | Faithful Prometheus artifact and missing-series diagnosis (`03:27-77`), but no validate/reload/injection evidence. |
| Replica/disk alerting | operationalized | demonstrated | Faithful combined rule and first checks (`03:50-73`), but no runnable validation or recovery completion criterion. |
| Controller/coordinator health and incident response | operationalized | mentioned | Named in correlation/triage (`03:9,20`) with no metric, alert, decision branch, recovery, or success signal. Apache monitoring documents controller and offline-partition metrics. |
| Kafka 4.3 rolling upgrade and rollback | operationalized | mentioned | Generic checklist only (`04:18-20`); no one-broker-at-a-time trace, health gate, metadata-version finalization, rollback cutoff, or abort procedure. |
| Regional failover/failback | operationalized | demonstrated | Named state trace, measured RPO/RTO, duplicate/loss ranges, split-history boundary, game-day criterion (`04:24-59`); provider/tool-specific execution remains deliberately abstract. |
| Topic creation and effective-config inspection | operationalized | demonstrated | Exact commands and effective-value checks (`05:5-26`), but no reproduced output or create rollback. |
| Retention alteration/rollback | operationalized | operationalized | Exact alteration, observation signals, explicit rollback value, inherited-fallback warning, and migration boundary (`05:53-72,88-104`). Live reproduction is separate from teaching depth. |
| Partition expansion, replica reassignment, quotas, deletion | operationalized | defined | Consequences and boundaries are useful (`05:76-104`), but no exact plan/apply/verify/rollback carriers. Apache's basic-operations guide supplies explicit generate/execute/verify reassignment and rollback-plan handling that the local reference does not teach. |

## Cross-topic and reader-path dependencies

- The root production-hardening path reaches operations only after delivery semantics, transactions, and service testing (`infrastructure/kafka/README.md:69-83`). This ordering is sound: operations can assume an existing event flow and tested application recovery, but not prior cluster-operation expertise.
- Security's ACL policy depends on the topic/group vocabulary taught earlier. It does not require a later operations note, but its implementation result is not available by operations entry 1 because the client verification is absent.
- Capacity explicitly delegates test placement to `reliability/05_testing_kafka_services.md` (`02:50-54`). That prerequisite distinguishes load tests from mocks and says what distributions to use (`reliability/05:27-39,77-88`), but it does not provide the load generator or one-broker-loss harness. The operations result therefore remains conceptual rather than executable.
- `min.insync.replicas=2` in administration (`05:13-15`) relies on the earlier replication contract, which correctly composes replication factor, ISR, and `acks=all` (`fundamentals/05:30-37`). No ordering gap.
- Disaster recovery correctly depends on schema-registry restoration (`04:65-67`). The canonical schema note explains why IDs/mappings must be restored before consumers and gives a retained-record restore signal (`application_design/05:105-118`).
- The operations index claims a working result by entry 2 (`operations/README.md:17-18`). The capacity decision is supported, but “apply a least-privilege client/ACL policy” is not an executable result because entry 1 lacks a bounded positive/negative client run. Path execution payoff: FAIL at entry 1; understanding payoff: PASS by entry 2.
- Transfer probes: (1) a wildcard ACL causes an unrelated-topic write to succeed — PASS from `01:59-63,79-82`; inspect broader ACLs. (2) one hot key dominates after partition expansion — PASS from `02:34-37,65-66`; adding partitions does not split one key. (3) `orders_event_age_seconds` disappears — PASS from `03:64-68`; the `and` alert is suppressed and a separate absence alert is needed. (4) brokers run 4.3 and an operator wants to finalize then retain downgrade — FAIL from local prose; the metadata-version rollback cutoff is not taught. (5) deleting the seven-day override when the broker default is 30 days — PASS from `05:36-46`; effective retention becomes 30 days.

## Executable-claim inventory

Denominator: 6 executable claims/procedures. Conceptual arithmetic (`02:7-37`), triage diagrams (`03:15-21`), DR timelines (`04:34-51`), and configuration-precedence traces (`05:36-42`) are teaching carriers, not executable claims.

### operations/01_security_and_multitenancy.md:23-37 — Python producer configuration
Claim: copyable configuration that authenticates `orders-api` using SCRAM over verified TLS.
Status: PARTIAL.
Command: exact block parsed with Python `ast.parse`; runtime construction not attempted.
Environment: local Python 3; no `confluent_kafka` module, `KAFKA_ORDERS_API_PASSWORD`, `/etc/kafka/ca.pem`, DNS endpoint, or authorized broker supplied.
Observed: syntax PASS; `confluent_kafka` import unavailable. The block does not call `produce`, so even a successful constructor would not verify the stated write path.

### operations/01_security_and_multitenancy.md:42-57 — three ACL mutations
Claim: runnable admin commands applying writer, topic-reader, and group-reader ACLs.
Status: NOT-RUN.
Command: the three exact `kafka-acls.sh --bootstrap-server ... --command-config admin.properties --add ...` commands shown.
Environment: shell syntax checked locally; Kafka CLI, live broker, and `admin.properties` are unavailable. Commands mutate external cluster authorization state.
Observed: `bash -n` PASS. No cluster mutation was authorized or attempted.

### operations/01_security_and_multitenancy.md:63 — ACL diagnosis
Claim: inspect an unexpectedly broad policy with `kafka-acls.sh --list`.
Status: PARTIAL.
Command: `kafka-acls.sh --list`.
Environment: no Kafka CLI or live cluster.
Observed: inspection only. Unlike the mutation commands, this inline command omits `--bootstrap-server` and authenticated `--command-config`, so it is not a copyable diagnosis in the documented secured environment.

FIX-MED: Make the diagnosis command complete with the same bounded endpoint and authenticated admin configuration used above, and show the list row that reveals the wildcard/prefixed grant.

### operations/03_observability_and_incident_response.md:32-62 — Prometheus rules
Claim: executable thresholds for freshness and replica/disk risk.
Status: PARTIAL.
Command: exact YAML block parsed with Ruby/Psych; `promtool check rules <file>` was unavailable.
Environment: local YAML parser only; no Prometheus, exporter, rule file, metrics, or alert receiver.
Observed: YAML syntax PASS. PromQL parsing, vector matching against actual label sets, reload, and firing behavior remain unverified.

### operations/05_configuration_and_topic_administration.md:10-20 — create and describe topic
Claim: runnable creation plus effective-result inspection.
Status: NOT-RUN.
Command: exact `kafka-topics.sh ... --create` and `kafka-configs.sh ... --describe` commands shown.
Environment: shell syntax checked locally; Kafka CLIs, live three-broker cluster, and authenticated `admin.properties` are unavailable. Creation mutates external state.
Observed: `bash -n` PASS; no live execution.

### operations/05_configuration_and_topic_administration.md:57-67 — alter and rollback retention
Claim: runnable retention alteration followed by observation and exact rollback to `604800000`.
Status: NOT-RUN.
Command: exact displayed `kafka-configs.sh ... --alter --add-config retention.ms=1209600000`; rollback is described as the same command with `retention.ms=604800000`.
Environment: shell syntax checked locally; Kafka CLI/live cluster/admin configuration/canary publisher and observation window are unavailable. Alteration mutates external state.
Observed: displayed command `bash -n` PASS; no live alteration or rollback.

Execution summary: 0 VERIFIED, 0 BROKEN, 3 PARTIAL, 3 NOT-RUN, 0 EXCERPT. No safety-critical executable defect was found: TLS verification remains enabled, credentials come from the environment, payload/credential logging is explicitly prohibited, and destructive topic deletion is described but not presented as a casual copyable command (`01:17,28-36`; `03:23-25`; `05:82-83,99-104`).

## Primary-source checks and unresolved items

Checked 2026-09-16:

- Apache Kafka 4.3 Security Overview: https://kafka.apache.org/43/security/security-overview/ — confirms SASL/SCRAM, SSL encryption/authentication, and authorization as distinct security capabilities.
- Apache Kafka 4.3 Authorization and ACLs: https://kafka.apache.org/43/security/authorization-and-acls/ — used to bound ACL review; no contradiction found in the shown principal/action/resource grants.
- Apache Kafka 4.3 Monitoring: https://kafka.apache.org/43/operations/monitoring/ — confirms `UnderReplicatedPartitions`, controller activity, offline partitions, and replica lag as documented operational signals; supports the controller/coordinator coverage gap.
- Apache Kafka 4.3 Upgrading: https://kafka.apache.org/43/getting-started/upgrade/ — identifies 4.3.1, requires KRaft for 4.3, gives one-broker-at-a-time rolling procedure, defers metadata-version finalization until verification, and states the 4.3 metadata change prevents metadata downgrade. This is the strongest unresolved local teaching gap.
- Apache Kafka 4.3 KRaft operations: https://kafka.apache.org/43/operations/kraft/ — confirms the metadata quorum is an independently operated plane and that 3.9 is the last ZooKeeper-to-KRaft bridge release.
- Apache Kafka 4.3 cross-cluster mirroring: https://kafka.apache.org/43/operations/geo-replication-cross-cluster-data-mirroring/ — confirms MirrorMaker can replicate topics/configurations, consumer groups/offsets, and ACLs. Local `04:26-28` is accurate in saying these require explicit recovery treatment; it should not be read as saying MirrorMaker lacks every such capability.
- Apache Kafka 4.3 Basic Operations: https://kafka.apache.org/43/operations/basic-kafka-operations/ — confirms partition expansion can change default keyed placement, `--delete-config`, and generate/execute/verify reassignment with a saved rollback assignment.
- Apache Kafka 4.3 topic and broker configuration references: https://kafka.apache.org/43/configuration/topic-configs/ and https://kafka.apache.org/43/configuration/broker-configs/ — linked local URLs returned HTTP 200; broker properties expose per-property update modes such as read-only and cluster-wide.

Unresolved execution items: no Kafka CLI distribution, broker cluster, credentials, `admin.properties`, CA file, Prometheus/promtool, exporter metrics, alert receiver, load generator, or fault-injection environment was present. Consequently no live security, capacity, alert, upgrade, failover, reassignment, or retention mutation was attempted. The syntactic checks above do not establish runtime semantics or production safety.
