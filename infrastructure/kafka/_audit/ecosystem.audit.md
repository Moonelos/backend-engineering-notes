# ecosystem/README.md (18 lines)
ORDERING: role reference/navigation; n/a; payoff n/a; lines 7–17 map four optional branches and a stop point.
EXPLANATION: n/a; teach-back n/a (missing: none); this is a short path index.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The index clearly marks optional ecosystem mechanisms and avoids forcing them into the baseline path.

# ecosystem/01_kafka_connect_and_data_integration.md (44 lines)
ORDERING: role decision guide; PASS; payoff 5/44; lines 7–11 name the decision, explain source/sink/CDC, and give the initial Connect-versus-code criterion.
EXPLANATION: PASS; teach-back PASS (missing: none); lines 15–30 identify worker-owned tasks/offsets, the plugin/API trust boundary, restart verification, schema coupling, and the misconception that configuration removes delivery responsibilities.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The note promises a choice rather than connector implementation and supplies enough criteria, failure evidence, and a boundary for that role.

# ecosystem/02_stream_processing.md (61 lines)
ORDERING: role foundation; PASS; payoff 5/61; the event-time window trace begins at line 13 and demonstrates on-time, late, restart, and dropped records before abstraction.
EXPLANATION: PASS; teach-back PASS (missing: none); lines 25–27 map timestamp and arrival changes to emitted corrections, and lines 31–57 explain owned state, recovery, key compatibility, and when batch or database computation is simpler.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The trace provides a faithful carrier and changed-input contrast for the note's decision-level foundation role.

# ecosystem/03_share_groups_and_queue_semantics.md (56 lines)
ORDERING: role deep dive; PASS; payoff 5/56; the partition-concurrency constraint and per-record state trace motivate the deeper mechanism immediately.
EXPLANATION: PASS; teach-back PASS (missing: none); lines 7–32 expose record ownership, acknowledgement transitions, timeout/redelivery, delivery count, and the ordering/idempotency boundary.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: Lines 34–36 call share groups production-ready and only say non-Java support “may lag,” but this Python-focused collection currently installs `confluent-kafka`; its 2.15.0 `ShareConsumer` is explicitly Preview, not recommended for production, and lacks `RENEW`, despite the note teaching `RENEW` at line 31. State the concrete Python-client status and limitations, separate broker GA from client readiness, and prevent Python readers from treating the shown renewal path as implementable. Evidence: https://github.com/confluentinc/confluent-kafka-python/blob/master/docs/kip-932-share-consumer.md (checked 2026-09-16).

# ecosystem/04_when_to_use_kafka.md (56 lines)
ORDERING: role decision guide; PASS; payoff 5/56; three named scenarios produce Kafka, queue, and RPC starting choices before the comparison table.
EXPLANATION: PASS; teach-back PASS (missing: none); lines 13–41 connect requirements and organizational state to the decision, while lines 45–51 expose the task-queue misconception and simpler-system boundary.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The note gives an actionable initial recommendation, criteria that change it, a review success signal, and an explicit rejection boundary.
