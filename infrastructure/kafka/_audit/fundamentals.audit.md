# fundamentals/README.md (37 lines)
ORDERING: role reference/navigation; n/a; payoff n/a; lines 9–29 name a route, outcomes, stop point, and continuation.
EXPLANATION: n/a; teach-back n/a (missing: none); index, not a teaching chapter.
LESSON: n/a; navigation role; the linked lessons are assessed individually in lesson_quality.audit.md.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The index provides an intelligible route and explicit Docker/shell prerequisites. Its no-prior-Kafka promise is the standard applied to its chapters, not proof that they meet it.

# fundamentals/01_first_event_round_trip.md (91 lines)
ORDERING: role implementation; PASS; payoff 31/91; the commands and success signal precede deeper discussion; required setup is bounded.
EXPLANATION: PASS; teach-back PASS (missing: none); lines 7–31 give broker, producer, consumer, named record and output; 38–66 explain repeat consumption and record coordinates; 70–85 explain disposable storage and scope boundaries.
LESSON: PASS; lesson_quality.audit.md LQ-F01; the repeated read develops the narrow first-result promise. Execution status is reported separately.
Summary: 0 critical, 0 high, 1 med, 0 low

FIX-MED: F-CLI — Line 26 uses deprecated formatter `--property` options. Kafka 4.3.1 source still accepts them but marks them for removal and names `--formatter-property` as the replacement; update both flags and reproduce output. This is a compatibility correction, not evidence the present round trip is broken. [Apache Kafka 4.3.1 ConsoleConsumerOptions](https://raw.githubusercontent.com/apache/kafka/4.3.1/tools/src/main/java/org/apache/kafka/tools/consumer/ConsoleConsumerOptions.java), checked 2026-09-16. Historical execution evidence remains in examples.audit.md; this refresh did not rerun Docker.

# fundamentals/02_log_topics_partitions_and_offsets.md (93 lines)
ORDERING: role foundation; FAIL; payoff 17/93 for the narrow commit/non-deletion distinction, but lines 7–17 require a group checkpoint before establishing independent reader identity; later cleanup, lag, and expiry arrive as separate compressed fragments.
EXPLANATION: FAIL; teach-back PASS for retained log, per-partition address and next checkpoint; FAIL across the full scope (missing: developed cleanup/lag/recovery reasoning). Lines 50–61 show latest-value removal, but tombstones remain undefined; 67–69 give a lag formula without connecting it to the opening's state; 82–84 introduce reset choices without tracing their consequences.
LESSON: FAIL; lesson_quality.audit.md LQ-F02 owns the recurring explanatory defect and proposed reconstruction.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: lesson_quality.audit.md LQ-F02. The former first-use group finding is absorbed into the larger lesson repair; a glossary insertion alone would leave its later promises underdeveloped.

# fundamentals/03_partitioning_keys_and_ordering.md (81 lines)
ORDERING: role first-time routing lesson with production extensions; FAIL; payoff 9/81 and routing trace 15–22 are useful, but 27–30 requires cross-client compatibility before developing key choice, and 54–77 offers migration and causality remedies without teaching or explicitly deferring them.
EXPLANATION: FAIL; teach-back PASS for key affinity and per-partition ordering; FAIL for the full decision promise (missing: logical-bucket indirection, migration handoff, and choosing remedies for skew versus causal order). A demonstrated hash-to-partition trace does not demonstrate the later advice.
LESSON: FAIL; lesson_quality.audit.md LQ-F03 provides the scope development map and rewrite plan.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: lesson_quality.audit.md LQ-F03. Retain the good bad-key/good-key example; do not treat each later warning as an independently completed lesson.

# fundamentals/04_consumer_groups_offsets_and_rebalancing.md (87 lines)
ORDERING: role first-time group/coordination lesson with production extensions; FAIL; payoff 15/87 supports the scaling ceiling, but ownership, durable progress, revocation and bounded workers are introduced before a continuous handoff model is built.
EXPLANATION: FAIL; teach-back PASS for partition assignment ceiling and duplicate-effect crash trace; FAIL for coordination and safe handoff (missing: coordinating actor, saved-versus-live progress through reassignment, and mechanism supporting idempotency/bounded worker prescriptions).
LESSON: FAIL; lesson_quality.audit.md LQ-F04 owns the explanatory and editorial repair.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: lesson_quality.audit.md LQ-F04 absorbs the former separate coordinator and idempotency bridge findings into one developed handoff lesson.
RELATED: coverage.audit.md, Consumer protocol migration. Lines 52–57 point to operations/05 for a rollout check that is absent. Keep this omission coverage-owned rather than counting it again locally. [Kafka 4.3 consumer rebalance protocol](https://kafka.apache.org/43/operations/consumer-rebalance-protocol/), checked 2026-09-16, confirms that server availability does not imply the client selected the protocol.

# fundamentals/05_replication_leaders_and_kraft.md (78 lines)
ORDERING: role first-time replication/failure lesson; FAIL; payoff 9/78 offers a useful failure question, but begins with three configuration concepts before the reader has a replica-state model; the later quorum section states consequences without developing the independent failure timelines.
EXPLANATION: FAIL; teach-back FAIL (missing: correct acknowledgment wait/admission distinction and developed failure transitions); lines 43–52 successfully distinguish metadata from payload ownership, but that local success does not fulfill the complete failure-prediction promise.
LESSON: FAIL; lesson_quality.audit.md LQ-F05 owns the multi-state teaching repair; the incorrect acknowledgment explanation is separately corrected below.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: F-ACK — Lines 32–34 describe `acks=all` as waiting for the minimum-replica rule, leaving the reader with the wrong threshold model. The minimum ISR is the admission/durability floor, while `acks=all` waits for the current full ISR: with ISR={1,2,3} and minISR=2, broker 3 still matters until it leaves ISR; with ISR={1} the floor rejects the write. Explain both transitions and failure responses. [Producer configuration](https://kafka.apache.org/43/configuration/producer-configs/) and [topic configuration](https://kafka.apache.org/43/configuration/topic-configs/), checked 2026-09-16.
RELATED: lesson_quality.audit.md LQ-F05. Correcting the threshold sentence is necessary but does not by itself develop the failure lesson.
RELATED: coverage.audit.md, Replication, acknowledgment, KRaft, and safe election. The previous report overstated lines 15–26 as explicitly claiming that only ISR can lead: the prose says “eligible follower,” leaving eligibility unexplained. Kafka 4.3 current election coverage must include ELR (enabled by default on new clusters since 4.1), with an ISR-empty/ELR-present contrast. Treat this as missing coverage, not a quote of a nonexistent exclusive claim. [Eligible Leader Replicas](https://kafka.apache.org/43/operations/eligible-leader-replicas/), checked 2026-09-16.
