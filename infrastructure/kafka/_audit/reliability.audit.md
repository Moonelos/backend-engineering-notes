# reliability/README.md (31 lines)
ORDERING: role reference/navigation; n/a; payoff n/a; entries 2–3 promise an executable transaction and harness not supplied by their targets.
EXPLANATION: n/a; teach-back n/a (missing: none); navigation contract, not a lesson.
LESSON: n/a; LQ-R00 in lesson_quality.audit.md; index role.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: reader_paths.audit.md owns the false execution milestone; examples.audit.md owns the absent processor and test harness.

# reliability/01_delivery_semantics.md (46 lines)
ORDERING: role foundation; PASS; payoff 10/46; starts with the relevant crash comparison, although one branch is incorrect.
EXPLANATION: FAIL; teach-back FAIL (missing: valid at-most-once state transition); lines 8–9 do not consistently distinguish the record offset, next checkpoint, and completed durable effect.
LESSON: FAIL; LQ-R01 in lesson_quality.audit.md; the central comparison cannot teach the advertised loss window correctly.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: R-C01 — Line 8 shows `commit offset 8 → process 8 → crash = possible loss`. A committed next offset of 8 resumes at record 8, and a crash after a completed effect does not demonstrate omitted processing. Use explicit initial checkpoint 8, persist checkpoint 9, crash before the durable effect for record 8, restart at 9; contrast effect-first followed by a crash while checkpoint remains 8. This repairs the foundational loss/duplicate comparison. Primary evidence: https://kafka.apache.org/43/design/design/ (Message Delivery Semantics, checked 2026-09-16).
RELATED: coverage.audit.md owns durable consumer-effect idempotency depth; its absence is not counted again here.

# reliability/02_idempotence_transactions_and_exactly_once.md (73 lines)
ORDERING: role deep dive; PASS; payoff 45/73 for transaction state; the scope matrix orients the reader, although two mechanisms lack developed beginner owners.
EXPLANATION: FAIL; teach-back FAIL (missing: producer-retry state transition and consumer-effect atomic deduplication transition); Kafka output/input-offset atomicity is demonstrated at lines 33–54, but the other two scopes are summarized.
LESSON: FAIL; LQ-R02 in lesson_quality.audit.md; the reader cannot derive all three advertised boundaries from one developed transaction and two labels.
Summary: 0 critical, 0 high, 1 med, 0 low

FIX-MED: R-C02 — Lines 41–45 compress crash recovery directly into abort/restart. Explain that unresolved open transactions can hold back read_committed progress, including later records; name recovery by reinitialization with the same stable transactional.id (Python init_transactions), or timeout. A novice otherwise has no explanation for a healthy-looking broker whose reader stalls before recovery. Sources: https://kafka.apache.org/43/generated/consumer_config.html (isolation.level) and https://kafka.apache.org/43/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html (initTransactions), checked 2026-09-16.
RELATED: lesson_quality.audit.md LQ-R02 owns the chapter-wide instructional reconstruction; coverage.audit.md owns missing producer/consumer idempotency mechanisms; examples.audit.md owns the promised executable transaction.

# reliability/03_retries_dead_letters_and_replay.md (86 lines)
ORDERING: role implementation; FAIL; payoff absent/86; a useful envelope and policy precede a replay command, but the route lacks a composed retry/recovery implementation.
EXPLANATION: FAIL; teach-back FAIL (missing: delaying actor, persisted eligibility decision, source-to-retry checkpoint transition, replay effect transition); topic names and timestamps do not explain which process enforces delayed consumption.
LESSON: FAIL; LQ-R03 in lesson_quality.audit.md; the single event's route is shown, but transitions between its states and ordering trade-offs are not developed.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: lesson_quality.audit.md LQ-R03 owns the disconnected instructional route; coverage.audit.md owns scheduling/handoff and replay depth; examples.audit.md owns executable replay defects.

# reliability/04_transactional_outbox_and_cdc.md (114 lines)
ORDERING: role implementation; FAIL; payoff absent/114 for the promised assembled publication path; the local database transaction and relay crash trace are useful but no runnable database-to-Kafka composition follows.
EXPLANATION: FAIL; teach-back PASS for polling-outbox concept, FAIL for CDC (missing: CDC owned checkpoint and recovery transition); LESSON fails the undeveloped comparison despite the strong polling trace.
LESSON: FAIL; LQ-R04 in lesson_quality.audit.md; local outbox reasoning is developed, but the advertised polling/CDC decision is compressed into ownership labels.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: R-C04 — Lines 80–82 instruct the relay to key Kafka records by unique event_id. For ordered changes of one aggregate this can route consecutive events to different partitions, contrary to the earlier keys lesson. Use aggregate_id/order_id for routing and event_id for deduplication; explain that co-location is necessary but concurrent relays must also preserve aggregate publication order. Show two distinct event IDs for ord-42 with the same Kafka key. Primary evidence: https://debezium.io/documentation/reference/transformations/outbox-event-router.html (aggregateid event key and id duplicate identity, checked 2026-09-16).
RELATED: lesson_quality.audit.md LQ-R04 owns the comparison's explanatory repair; coverage.audit.md owns relay/CDC/reconciliation depth; examples.audit.md owns incomplete execution setup.

# reliability/05_testing_kafka_services.md (111 lines)
ORDERING: role implementation; FAIL; payoff absent/111; opening pytest command targets an absent file, then describes the test to be written.
EXPLANATION: PASS; teach-back PASS (missing: none for the test-design mechanism); lines 27–107 connect guarantee, falsifying environment, deterministic fault point, durable assertions, suite composition, and single-node limits.
LESSON: PASS; LQ-R05 in lesson_quality.audit.md; the instructional reasoning is developed even though the promised executable harness is missing.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: examples.audit.md owns the broken smoke command and absent crash harness; coverage.audit.md owns insufficient operationalized testing depth. Lesson PASS does not certify the runnable implementation promise.
