# ecosystem/README.md (18 lines)
ORDERING: role reference/navigation; n/a; payoff n/a; lines 9–17 map optional mechanisms and the stopping condition.
EXPLANATION: n/a; teach-back n/a (missing: none); index role.
LESSON: n/a; lesson_quality.audit.md LQ-E00 records role-appropriate scope.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The index exposes optional branches without promising a complete mechanism explanation itself.

# ecosystem/01_kafka_connect_and_data_integration.md (44 lines)
ORDERING: role decision guide; PASS; payoff 7/44; source/sink direction, worker responsibilities and initial connector-versus-code criterion appear first.
EXPLANATION: PASS; teach-back PASS (missing: none for the initial selection capability); lines 7–11 explain standard movement, 17–23 connect executable trust to task-level checks, and 36–40 explain sink duplicate and workflow boundaries.
LESSON: PASS; lesson_quality.audit.md LQ-E01 maps the bounded choice and distinguishes it from absent operationalized Connect coverage.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: Adequate initial decision guide; no invented requirement to configure a connector in this note.
RELATED: coverage.audit.md separately evaluates whether the wider production curriculum supplies connector setup, task inspection and checkpoint/restart verification.

# ecosystem/02_stream_processing.md (61 lines)
ORDERING: role foundation; PASS; payoff 13/61; begins with a named payment/window trace rather than engine taxonomy, although that trace contains a central time error.
EXPLANATION: FAIL; teach-back FAIL (missing: event-time progress that closes the window; state/input recovery alignment and keyed output interpretation); lines 13–27 use arrival alone to change acceptance and lines 31–54 compress recovery/join reasoning into prescriptions.
LESSON: FAIL; lesson_quality.audit.md LQ-E02 owns development of the later state/recovery/output promises independently of the local time correction.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: E02-TIME — Lines 13–14 give watermark10:06, yet 22 and 25–27 declare a record arriving at10:08 past a10:07 event-window close without showing event-time progress advancing. Arrival/wall-clock alone does not justify that result. Choose an engine's semantics, show the stream-time/watermark value at every decision and the input/progress event advancing it, and explain late handling under that policy. For Kafka Streams the relevant comparison is current stream time versus window end plus grace; Flink advances operator event time via watermarks. Do not blend these into a universal arrival deadline or imply every engine provides the same side-output behavior. Sources: https://kafka.apache.org/43/streams/core-concepts/ (Time and Windowing); https://nightlies.apache.org/flink/flink-docs-stable/docs/concepts/time/ (Watermarks and Lateness); checked 2026-09-16.
RELATED: lesson_quality.audit.md LQ-E02 owns the distinct structural development beyond the corrected time trace.

# ecosystem/03_share_groups_and_queue_semantics.md (56 lines)
ORDERING: role deep dive; PASS; payoff 19/56; conventional ownership contrast leads directly to a named per-record timeline.
EXPLANATION: FAIL; teach-back PASS for broker-level ownership transitions (missing: none in that conceptual trace); the Python applicability required to choose this feature is misleadingly underspecified at 31–36.
LESSON: PASS; lesson_quality.audit.md LQ-E03 finds the state transitions and ordering/duplicate boundaries developed; a targeted applicability correction is sufficient.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: E03-CLIENT — Lines 31 and 34–36 combine RENEW and broker production readiness with only a vague warning that non-Java coverage may lag. The maintained confluent-kafka-python share-consumer guide explicitly labels the feature Preview, not recommended for production, and states acquisition-lock renewal is unavailable. Name the actual Python-client status and missing renewal beside the trace, distinguish broker readiness from client readiness, and prevent this Python-focused reader from treating the renewal path as deployable with the installed client. Source: https://github.com/confluentinc/confluent-kafka-python/blob/master/docs/kip-932-share-consumer.md, Overview and Current Limitations; checked 2026-09-16. Broker-level conceptual usefulness is retained.

# ecosystem/04_when_to_use_kafka.md (56 lines)
ORDERING: role decision guide; PASS; payoff 7/56; three concrete need categories produce provisional starting choices before the wider comparison table.
EXPLANATION: PASS; teach-back PASS (missing: none for initial classification); lines 7–26 give requirements-to-choice relationships, 32–38 explain organizational responsibility, and 47–51 name the deletion misconception and simpler alternatives.
LESSON: PASS; lesson_quality.audit.md LQ-E04 distinguishes this bounded first decision from the deeper architecture-path model and implementation.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The initial classification and rejection boundary are coherent; the complete architecture path must still earn retained-log understanding before a final design decision.
RELATED: reader_paths.audit.md owns that complete path and its fundamental-storage prerequisites.
