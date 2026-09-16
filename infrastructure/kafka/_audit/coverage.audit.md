# Disposable record round trip
Promised by: root and fundamentals entry-one runnable result.
Canonical owner: `fundamentals/01_first_event_round_trip.md`
Required: operationalized
Achieved: operationalized
TEACH-BACK: PASS; missing: none
ROLE: PASS; implementation matches disposable-local scope.
SIGNAL: path-promise
SOURCE: lines 5–87 and exact reproduction in `examples.audit.md`.

NO-ACTION: Setup, output, replay, failure tell, cleanup, and production boundary are present and reproduced.

# Retained log, partition, offset, and replay
Promised by: fundamentals and root exploration outcomes.
Canonical owner: `fundamentals/02_log_topics_partitions_and_offsets.md`
Required: demonstrated
Achieved: demonstrated
TEACH-BACK: PASS; missing: none after full note
ROLE: PASS; foundation carries the mechanism with named records and contrasts.
SIGNAL: path-promise
SOURCE: lines 5–88.

RELATED: The retained-read/next-offset opening is demonstrated; cleanup, lag operands and recovery are not thereby demonstrated. `lesson_quality.audit.md` LQ-F02 owns the developed-lesson repair across these later promises.

# Key routing and ordering
Promised by: fundamentals outcome and topic-design path.
Canonical owner: `fundamentals/03_partitioning_keys_and_ordering.md`
Required: demonstrated
Achieved: demonstrated
TEACH-BACK: PASS; missing: none
ROLE: PASS; deep dive follows the log baseline.
SIGNAL: canonical-owner
SOURCE: lines 5–77.

RELATED: The bad-key/good-key contrast demonstrates affinity; expansion risk is explained. Hotspot remedies, stable bucket routing/migration and application sequencing are stated rather than demonstrated. `lesson_quality.audit.md` LQ-F03 owns this full-scope instructional repair. Achieved level above applies to core routing only, not every recommended remedy.

# Consumer groups and rebalance ownership
Promised by: root exploration and fundamentals outcomes.
Canonical owner: `fundamentals/04_consumer_groups_offsets_and_rebalancing.md`
Required: demonstrated
Achieved: explained
TEACH-BACK: FAIL; missing: coordinator actor and local idempotency bridge
ROLE: PASS; appropriate deep dive, incomplete explanation.
SIGNAL: canonical-owner
SOURCE: lines 5–83; local corrections in `fundamentals.audit.md`.

RELATED: `lesson_quality.audit.md` LQ-F04 owns the group/checkpoint/ownership development; the missing consumer-protocol rollout is separately tracked below.

# Consumer protocol migration
Promised by: Kafka 4.3 current configuration at `fundamentals/04:52–57`.
Canonical owner: `fundamentals/04_consumer_groups_offsets_and_rebalancing.md`
Required: explained
Achieved: defined
TEACH-BACK: FAIL; missing: effective setting, changed callback/config contract, migration transition and rollback boundary
ROLE: PASS; current refinement follows classic groups.
SIGNAL: current-landscape
SOURCE: https://kafka.apache.org/43/operations/consumer-rebalance-protocol/ (checked 2026-09-16).

COVERAGE-MED: A production reader is told to roll out `group.protocol=consumer` but cannot predict which settings/callbacks stop applying or perform the online/offline migration — add one effective-config and assignment trace plus upgrade/downgrade constraints in note 04 or a real operations owner.

# Replication, acknowledgment, KRaft, and safe election
Promised by: fundamentals section outcome and root “storage, replication” claim.
Canonical owner: `fundamentals/05_replication_leaders_and_kraft.md`
Required: demonstrated
Achieved: defined
TEACH-BACK: FAIL; missing: correct acknowledgment and ELR election transitions
ROLE: PASS; deep dive is the right owner.
SIGNAL: current-landscape
SOURCE: https://kafka.apache.org/43/generated/producer_config.html and https://kafka.apache.org/43/operations/eligible-leader-replicas/ (checked 2026-09-16).

RELATED: `fundamentals.audit.md` owns the ambiguous acknowledgment rule; `lesson_quality.audit.md` LQ-F05 owns developed broker/controller failure reasoning. The source does not literally claim that only ISR members can ever lead.

COVERAGE-MED: For the declared Kafka 4.3 failure-model scope, add a bounded ELR continuation after the basic replication model: distinguish out-of-ISR from necessarily unsafe, then inspect the eligible set before considering unclean election. This is a missing current mechanism, not a falsely quoted exclusive-ISR claim.

# Event contracts and schema evolution
Promised by: application-design entry one.
Canonical owner: `application_design/01_event_contracts_and_schema_evolution.md`
Required: demonstrated
Achieved: explained
TEACH-BACK: FAIL across full evolution promise; missing: distinct old/new reader rules and worked deployment/semantic contrast; envelope validation is demonstrated
ROLE: PASS; implementation opens with its artifact.
SIGNAL: path-promise
SOURCE: lines 5–158.

RELATED: LQ-A01 in lesson_quality.audit.md owns the undeveloped deployment/evolution explanation. examples.audit.md owns false-direction executable tests. The concrete envelope does not demonstrate every compatibility direction.

# Python delivery and checkpoint lifecycle
Promised by: application-design and root exploration paths.
Canonical owner: `application_design/02_python_producers_and_consumers.md`
Required: demonstrated
Achieved: demonstrated
TEACH-BACK: PASS; missing: none
ROLE: PASS; runnable-path role is structurally appropriate.
SIGNAL: path-promise
SOURCE: lines 5–114.

NO-ACTION: Enqueue/acknowledgment, effect/commit, bounded poll, and shutdown distinctions are explained; path assembly is separately broken.

# Backpressure, commit frontier, rebalance, and shutdown
Promised by: application-design runtime-lifecycle outcome.
Canonical owner: `application_design/03_processing_loops_backpressure_and_shutdown.md`
Required: operationalized
Achieved: demonstrated
TEACH-BACK: FAIL; missing: safe ownership-loss transition
ROLE: PASS; implementation is the correct owner.
SIGNAL: canonical-owner
SOURCE: lines 5–247 and `examples.audit.md`.

RELATED: `examples.audit.md` owns the unsafe executable ownership-loss path; correcting that path is prerequisite to operationalized status.

# Topic topology and cleanup
Promised by: `application_design/README.md` topic/topology outcome.
Canonical owner: `application_design/04_topic_and_partition_design.md`, with compaction foundation in `fundamentals/02` and sizing later in `operations/02`.
Required: demonstrated
Achieved: explained
TEACH-BACK: FAIL; missing: named sizing transition and operational compaction/tombstone decision
ROLE: PASS; decision-guide role is appropriate but too shallow.
SIGNAL: path-promise
SOURCE: `application_design/04:5–60`; https://kafka.apache.org/43/configuration/topic-configs/ (checked 2026-09-16).

RELATED: `lesson_quality.audit.md` LQ-A04 owns developing the topic decisions, sizing contrast and cleanup boundary. Bring the relevant part of operations/02 forward rather than duplicating a separate coverage severity.

# Schema Registry lifecycle
Promised by: application-design implementation outcome to register, evolve, and restore serialized contracts.
Canonical owner: `application_design/05_schema_registry_and_serialization.md`
Required: operationalized
Achieved: demonstrated
TEACH-BACK: FAIL; missing: serializer/deserializer and reproducible restore transitions
ROLE: PASS; implementation is the correct role.
SIGNAL: path-promise
SOURCE: lines 5–130; https://docs.confluent.io/platform/current/schema-registry/develop/api.html (checked 2026-09-16).

RELATED: `lesson_quality.audit.md` LQ-A05 owns the undeveloped wire-ID/reader-resolution/restore lifecycle and concrete refactor. Complete the client round trip and bounded restore demonstration as its acceptance evidence; the maturity shortfall is retained without a duplicate severity.

# Delivery semantics and consumer idempotency
Promised by: production-hardening and reliability entry-two boundary outcomes.
Canonical owner: `reliability/01_delivery_semantics.md` for semantics; consumer dedupe owner missing across `reliability/01–02`.
Required: demonstrated
Achieved: defined
TEACH-BACK: FAIL; missing: correct at-most-once transition and durable unique-claim/duplicate-result transition
ROLE: FAIL; no note owns consumer-effect idempotency beyond advice/table rows.
SIGNAL: path-promise
SOURCE: `reliability/01:5–42`, `02:5–30`.

COVERAGE-HIGH: A central production milestone asks readers to select and prove an idempotency boundary, yet no unique constraint/claim, existing-result lookup, repeated attempt, and post-effect offset trace exists — make one reliability note the canonical owner and demonstrate the full durable transition.

# Kafka producer idempotence and consume-transform-produce transactions
Promised by: reliability entry-two implementation milestone.
Canonical owner: `reliability/02_idempotence_transactions_and_exactly_once.md`
Required: operationalized
Achieved: demonstrated
TEACH-BACK: FAIL overall; missing: producer retry contrast, full config/recovery/abort/position-reset path, executable proof
ROLE: PASS; deep dive may own the advanced mechanism after delivery semantics.
SIGNAL: path-promise
SOURCE: lines 5–69; https://kafka.apache.org/43/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html (checked 2026-09-16).

RELATED: `examples.audit.md` transaction kill/restart owns the absent promised executable processor and configuration. LQ-R02 owns how its explanation connects the three protection boundaries. Keep the coverage shortfall visible without counting the same missing processor twice.

# Retry scheduling, DLT handoff, and controlled replay
Promised by: reliability recovery implementation outcome.
Canonical owner: `reliability/03_retries_dead_letters_and_replay.md`
Required: operationalized
Achieved: explained
TEACH-BACK: FAIL; missing: delaying actor/state, atomic/idempotent source handoff, runnable bounded replay
ROLE: PASS; implementation is the correct owner.
SIGNAL: path-promise
SOURCE: lines 5–82.

COVERAGE-HIGH: Topic names and `next_attempt_at` do not schedule delivery, and no crash-safe source→retry/DLT transition exists — show the scheduler/consumer state, transaction or dedupe boundary, and a reproduced one-record replay with preflight/rate/rollback controls.

# Transactional outbox, polling relay, and CDC
Promised by: reliability implementation outcome.
Canonical owner: `reliability/04_transactional_outbox_and_cdc.md`
Required: operationalized
Achieved: explained
TEACH-BACK: FAIL for CDC and duplicate collapse; missing: connector/log position/config, insert-only transition, relay reconciliation, durable consumer dedupe
ROLE: FAIL; one note conflates a mutable polling schema with CDC without operationalizing either full relay.
SIGNAL: path-promise
SOURCE: lines 5–110; https://debezium.io/documentation/reference/transformations/outbox-event-router.html (checked 2026-09-16).

COVERAGE-HIGH: Complete one polling relay (claim, acknowledge, mark, reconcile) and one clearly separated CDC/event-router path (insert-only row, connector position/config, retention/failure response), with aggregate key and consumer dedupe carriers.

# Kafka service test harness
Promised by: production-hardening test step and reliability implementation milestone.
Canonical owner: `reliability/05_testing_kafka_services.md`
Required: operationalized
Achieved: explained
TEACH-BACK: PASS conceptually; missing: executable fixtures and assertions
ROLE: PASS; implementation role is correct but unfulfilled.
SIGNAL: path-promise
SOURCE: lines 5–107 and `examples.audit.md`.

RELATED: `examples.audit.md` smoke/crash-harness findings own missing executable fixtures and assertions. LQ-R05 separately credits the developed conceptual test design. Operationalized coverage remains unmet; no duplicate severity here.

# Security and multitenancy
Promised by: operations implementation outcome and root production continuation.
Canonical owner: `operations/01_security_and_multitenancy.md`
Required: operationalized
Achieved: demonstrated
TEACH-BACK: PASS; missing: none conceptually
ROLE: PASS; implementation role lacks final composition.
SIGNAL: path-promise
SOURCE: lines 5–82.

COVERAGE-HIGH: Safe TLS/SCRAM and ACL artifacts exist, but no bounded allowed/denied run, revocation/rotation transition, or hard-isolation verification completes the production promise — compose the client/admin verification and rotation rollback.

# Capacity planning
Promised by: operations entry-two calculation outcome.
Canonical owner: `operations/02_capacity_planning_and_performance.md`
Required: demonstrated
Achieved: demonstrated
TEACH-BACK: PASS; missing: none
ROLE: PASS; decision guide uses a changed recovery constraint.
SIGNAL: path-promise
SOURCE: lines 5–66.

NO-ACTION: Named inputs, arithmetic, failure headroom, invalidating assumptions, and verification target support the promised decision.

# Observability and incident response
Promised by: operations implementation outcome.
Canonical owner: `operations/03_observability_and_incident_response.md`
Required: operationalized
Achieved: demonstrated
TEACH-BACK: PASS for lag/freshness and replica/disk; FAIL for coordinator/controller response
ROLE: PASS; implementation is the correct owner.
SIGNAL: path-promise
SOURCE: lines 5–89; https://kafka.apache.org/43/operations/monitoring/ (checked 2026-09-16).

COVERAGE-HIGH: The note cannot validate/reload/fire its rules, silently omits the required `absent()` rule, and only names coordinator/controller health — add executable alert validation/injection plus metric→diagnosis→recovery branches for those control-plane failures.

# Upgrades and regional disaster recovery
Promised by: operations deep-dive outcome and root lifecycle continuation.
Canonical owner: `operations/04_deployment_upgrades_and_disaster_recovery.md`
Required: operationalized
Achieved: demonstrated for DR; mentioned for upgrades
TEACH-BACK: FAIL for upgrades; missing: feature/metadata state transition, verification gates, abort/rollback cutoff
ROLE: PASS; the combined lifecycle boundary is coherent.
SIGNAL: current-landscape
SOURCE: lines 5–67; https://kafka.apache.org/43/getting-started/upgrade/ (checked 2026-09-16).

COVERAGE-HIGH: Regional RTO/RPO reasoning is strong, but the Kafka 4.3 upgrade promise is a checklist — add broker-by-broker health gates, feature/metadata finalization, explicit non-downgrade boundary, and abort/rollback procedure.

# Topic and configuration administration
Promised by: operations reference outcome.
Canonical owner: `operations/05_configuration_and_topic_administration.md`
Required: operationalized
Achieved: operationalized for retention; defined for expansion/reassignment/quotas/deletion
TEACH-BACK: PASS for override/rollback; FAIL for wider administration
ROLE: PASS; a reference may lead with the common implementation.
SIGNAL: path-promise
SOURCE: lines 5–104; https://kafka.apache.org/43/operations/basic-kafka-operations/ (checked 2026-09-16).

COVERAGE-HIGH: Operators can change retention but cannot plan/apply/verify/recover partition expansion, replica reassignment, quotas, or deletion from the canonical reference — add bounded carriers and completion/rollback signals for each destructive or asymmetric operation.

# Kafka Connect decision
Promised by: ecosystem integration outcome.
Canonical owner: `ecosystem/01_kafka_connect_and_data_integration.md`
Required: explained
Achieved: explained
TEACH-BACK: PASS; missing: none
ROLE: PASS; decision guide does not promise connector implementation.
SIGNAL: path-promise
SOURCE: lines 5–40; https://kafka.apache.org/43/apis/ (checked 2026-09-16).

NO-ACTION: Translation/checkpointing versus domain workflow, trust, restart evidence, and sink idempotency are sufficient for the promised choice.

# Stream processing state and time
Promised by: ecosystem foundation outcome.
Canonical owner: `ecosystem/02_stream_processing.md`
Required: demonstrated
Achieved: explained
TEACH-BACK: FAIL; missing: correct closing-clock progression and aligned recovery/input state
ROLE: PASS; foundation uses a faithful time/window/restart trace.
SIGNAL: path-promise
SOURCE: lines 5–57; https://kafka.apache.org/43/streams/developer-guide/dsl-api/ (checked 2026-09-16).

RELATED: The window/restart trace is concrete; current correctness and whole-lesson verdict are in ecosystem.audit.md and lesson_quality.audit.md. A named warning about repartitioning is not demonstration of repartitioning. This row must be read as core window/state coverage only, subject to the time-basis correction.

# Share groups and queue semantics
Promised by: ecosystem deep-dive outcome and architecture branch.
Canonical owner: `ecosystem/03_share_groups_and_queue_semantics.md`
Required: demonstrated
Achieved: demonstrated
TEACH-BACK: PASS; missing: none conceptually
ROLE: PASS; optional deep dive follows conventional groups.
SIGNAL: current-landscape
SOURCE: lines 5–52; Apache 4.2 release and Python client sources in `curriculum.audit.md`.

RELATED: `ecosystem.audit.md` owns the stale Python-client production/`RENEW` applicability warning.

# Kafka adoption decision
Promised by: root architecture-decision path.
Canonical owner: `ecosystem/04_when_to_use_kafka.md`
Required: demonstrated
Achieved: demonstrated
TEACH-BACK: PASS; missing: none
ROLE: PASS; named scenarios and cost criteria change the recommendation.
SIGNAL: path-promise
SOURCE: lines 5–51.

NO-ACTION: Kafka, queue, database, and RPC starting choices are tied to state/delivery requirements and a simplest-alternative record.

# Tiered storage
Promised by: independently required production storage/replay/capacity outcome for a Kafka 4.3 operations course.
Canonical owner: missing
Required: explained
Achieved: absent
TEACH-BACK: FAIL; missing: problem, owned local/remote state, plugin actor, upload/read/delete transitions, limits and failures
ROLE: FAIL; no owner.
SIGNAL: current-landscape
SOURCE: https://kafka.apache.org/43/operations/tiered-storage/ (checked 2026-09-16).

COVERAGE-MED: Long-retention capacity and replay advice assumes broker-local storage and never lets an operator choose or diagnose Kafka 4.3 tiered storage — teach when it changes the capacity model, the required external `RemoteStorageManager`, local-versus-total retention, remote-read/copy/delete signals, and recovery/disable boundaries.
