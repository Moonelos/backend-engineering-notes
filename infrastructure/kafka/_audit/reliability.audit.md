# reliability/README.md (31 lines)
ORDERING: role reference/navigation; n/a locally; payoff n/a; path sequence fails because entry 2 promises execution but points to a conceptual trace, while the outbox appears only at entry 4.
EXPLANATION: n/a; teach-back n/a (missing: none); this is a path contract.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `reader_paths.audit.md` owns the false entry-2 execution milestone; `examples.audit.md` owns the absent processor and test harness.

# reliability/01_delivery_semantics.md (46 lines)
ORDERING: role foundation; PASS; payoff 10/46; the crash comparison precedes mechanism and verification.
EXPLANATION: FAIL; teach-back FAIL (missing: accurate at-most-once transition/result and demonstrated idempotency transition); the at-least-once half and boundary are sound, but the loss trace is not.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: Line 8 places the at-most-once crash after `process 8`, which does not exhibit lost processing. Move the crash between committing past offset 8 and completing its durable effect, name what “process” means, and contrast it with the at-least-once crash after effect but before checkpoint. Source: https://kafka.apache.org/43/design/design/ (checked 2026-09-16).

RELATED: `coverage.audit.md` owns the missing durable consumer-effect idempotency mechanism.

# reliability/02_idempotence_transactions_and_exactly_once.md (73 lines)
ORDERING: role deep dive; PASS; payoff 5/73; the opening matrix immediately bounds three “once” scopes.
EXPLANATION: FAIL; teach-back FAIL (missing: producer-idempotence transition/contrast and consumer-idempotency owned state/transition); the Kafka transaction itself is demonstrated, but the other two title mechanisms are shallow.
Summary: 0 critical, 0 high, 1 med, 0 low

FIX-MED: Lines 41–45 omit the observable interval while an open transaction holds `read_committed` consumers at the last stable offset, and omit the recovery actor: restart with the same stable `transactional.id` plus `initTransactions()` resolves the prior instance, otherwise timeout does. Add that intermediate lag/timeout symptom and recovery transition. Sources: https://kafka.apache.org/43/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html and https://kafka.apache.org/43/generated/consumer_config.html (checked 2026-09-16).

RELATED: `coverage.audit.md` owns insufficient producer/consumer idempotency and transaction operationalization; `examples.audit.md` owns the absent runnable transaction.

# reliability/03_retries_dead_letters_and_replay.md (86 lines)
ORDERING: role implementation; FAIL; payoff absent/86; policy/envelope artifacts are useful, but no retry consumer/scheduler, safe source handoff, DLT producer, or runnable recovery path exists.
EXPLANATION: FAIL; teach-back FAIL (missing: delaying actor/state, safe source-to-recovery handoff, executable replay transition); topic names and `next_attempt_at` do not cause delayed delivery.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `coverage.audit.md` owns retry scheduling, source-to-retry/DLT atomicity, and controlled replay depth; `examples.audit.md` owns the broken host-CLI replay pipeline.

# reliability/04_transactional_outbox_and_cdc.md (114 lines)
ORDERING: role implementation; FAIL; payoff absent/114; the database transaction is a strong artifact, but no runnable database setup or assembled polling/CDC publication path reaches Kafka.
EXPLANATION: FAIL; teach-back PASS for the polling-outbox concept but FAIL for CDC (missing: CDC actor, position/state, connector transition, failure and recovery); the note conflates two relay models.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: Lines 80–82 key Kafka records by unique `event_id`, so successive events for one order can land on different partitions and reorder, contradicting `fundamentals/03`. Use `aggregate_id`/`order_id` as the Kafka key and retain `event_id` for deduplication; demonstrate two aggregate events colocated. Debezium documents aggregate ID as the event key for ordering: https://debezium.io/documentation/reference/transformations/outbox-event-router.html (checked 2026-09-16).

RELATED: `coverage.audit.md` owns polling relay, CDC, reconciliation, and duplicate-collapse depth; `examples.audit.md` owns the incomplete database execution path.

# reliability/05_testing_kafka_services.md (111 lines)
ORDERING: role implementation; FAIL; payoff absent/111; the opening commands name a nonexistent test file and project, after which the note describes what the missing test should do.
EXPLANATION: PASS; teach-back PASS (missing: none for the testing principle); lines 27–107 clearly explain which environment can falsify each claim, deterministic process-kill synchronization, suite layering, cleanup, and one-node limits.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `examples.audit.md` owns the broken smoke command and absent crash harness; `coverage.audit.md` owns insufficient operational test depth.
