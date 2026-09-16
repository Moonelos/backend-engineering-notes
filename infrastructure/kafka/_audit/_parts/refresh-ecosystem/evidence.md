# Ecosystem audit refresh — 2026-09-16

Read all ecosystem01–04 and README in full, with root named paths and earlier fundamentals/application prose. Four teaching units: three LESSON PASS (01/03/04), one FAIL (02), zero unchecked; README n/a. Correctly scoped initial decision guides are not required to become operational tutorials. Their PASS does not establish production curriculum coverage.

Canonical systemic count: LQ-E02 one MED (state/input recovery, output updates and join-key development). Local counts: E02-TIME HIGH; E03-CLIENT HIGH. Other notes have no local severity. Existing share-consumer finding retained and reverified; old stream-processing NO-ACTION replaced.

## Primary research checked 2026-09-16

- https://kafka.apache.org/43/streams/core-concepts/ — inspected Time, Windowing and States. Kafka Streams event-time progression is data-driven; lateness uses current stream time compared with window end plus grace. This establishes why an arrival timestamp alone cannot justify the trace's late decision.
- https://nightlies.apache.org/flink/flink-docs-stable/docs/concepts/time/ — inspected event-time/watermarks/lateness. Watermarks advance operator event time; use explicit progress values if teaching Flink semantics. Do not transfer Kafka Streams grace terminology and generic side-output claims without naming the engine/policy.
- https://github.com/confluentinc/confluent-kafka-python/blob/master/docs/kip-932-share-consumer.md — inspected Overview and Current Limitations. Preview/nonproduction status and unavailable acquisition-lock renewal still substantiate the local Python readiness finding. This is a current client limitation, not a denial of broker availability.
- https://kafka.apache.org/43/kafka-connect/overview/ — inspected Connect's scalable source/sink integration scope. Supports treating 01 as a legitimate selection guide; does not prove checkpoint/restart behavior for an unspecified connector.

No services, share consumers, Connect workers or streaming engines were executed by this worker. Conceptual traces are not executable claims; the unchanged generic stop/restart success-signal claim stays NOT-RUN or narrower in examples according to the parent inventory.

## Path transfer handoff

- Connect selection: A database-log→warehouse flow with standard transformations versus a sequence that reserves inventory and compensates payment. PASS for initial selection from01:7–11,36–40: standard movement fits connector machinery, multi-step domain state needs an owned workflow. This is not a promise that every connector offers the same consistency guarantee.
- Stream time: Keep event-time progress at10:06 while wall-clock becomes10:08; event timestamp10:04 still belongs to the same window. FAIL: the published trace explicitly teaches arrival-only closure. E02-TIME is canonical; do not repeat severity in reader_paths.
- Stream output/recovery: Ask whether summing emitted30 and35 is correct, or whether restoring total30 while replaying the already included pay-2 preserves the count. Lesson lacks those interpreted state relationships; LQ-E02 owns the development plan. Do not silently import exactly-once engine internals from a future chapter.
- Share delivery: RELEASE versus lock expiry and a still-running effect. PASS conceptual prediction from03:19–32,48–52; client selection is separately FAIL because this Python implementation lacks the shown renewal and remains Preview.
- Architecture starting choice: Replace independent historical replay with immediate synchronous confirmation. PASS for provisional HTTP choice from04:7–9 and15–26. Full retained-log decision depth belongs to the next root architecture-path entry; do not mistake an initial selection guide for production architecture mastery.

Coverage handoff: preserve explained/demonstrated conceptual share state while marking Python operational readiness limitation; do not count a new missing mechanism merely because a supported broker feature is unavailable in the chosen client. Preserve existing recovery/join/state depth gaps if genuinely distinct from LQ-E02; cross-reference repeated structural development rather than double-count it. Connect implementation can be an independent researched-essential curriculum gap if the global production promise requires it; placement need not replace this useful decision guide.
