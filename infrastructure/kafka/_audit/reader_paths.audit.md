# README.md :: Explore Kafka with a runnable record
Outcome: Publish/consume `order.created`, explain retained topic/partition/offset state, then build a Python client.
Files: `fundamentals/01`, `02`, `03`, `04`, `application_design/02`, then revisits `application_design/01` and `04`.
EXECUTION PAYOFF: entry 1 (PASS; exact broker/topic/record path reproduced).
UNDERSTANDING PAYOFF: entry 2 (PASS; retained-record and offset trace supports the stated explanation).
TRANSFER: FAIL
Checkpoint: after fundamentals entry 2; later runtime assembly also checked.
Scenario: The group saved position 1, retained data now begins at 2, and the next append position is 5. Explain what an earliest versus latest reset can read, what was irretrievably lost, and why an offset distance is not elapsed age.
Reasoning: Earliest resumes available history at2; latest waits at5; neither reconstructs removed offset1. Numerical end and group position are independent of retained start and event age. The opening teaches a saved next position but the later sections do not develop those changing boundaries.
Evidence: fundamentals/02 §§3–5; LQ-F02 owns the missing worked reasoning. Successful early replay remains credited; the full promised storage/recovery model does not pass merely because that opening works.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: Entry 5 imports `event_contract`, but this route deliberately schedules the contract owner after the Python client (`README:57–58`); the runnable client therefore fails unless readers leave the route or invent the file. Move event contracts before the client or make the exploration client self-contained and explicitly revisit the contract-hardened variant later.

RELATED: `examples.audit.md` owns the exact broken client command; per-note/coverage reports own the failed idempotency transfer premise.

# README.md :: Production hardening
Outcome: Derive the real crash guarantee, select an idempotency boundary, implement the transaction trace, test crash windows, and operate the flow.
Files: `reliability/01`, `02`, `05`, `03`, then operations `01`–`03`.
EXECUTION PAYOFF: entry 2 (FAIL; note 02 contains a text trace, not the promised implementation).
UNDERSTANDING PAYOFF: entry 2 (FAIL; entry 1's at-most-once crash order is wrong and entry 2 never demonstrates consumer-effect idempotency).
TRANSFER: FAIL
Checkpoint: after entry 2.
Scenario: A transaction for input offset 8 remains open while a later record exists; predict what a `read_committed` consumer can return before timeout and how restart resolves it.
Reasoning: Correct reasoning requires last-stable-offset blocking and recovery by a restarted producer with the same stable transactional identity or coordinator timeout.
Evidence: `reliability/02:41–45` says only that the consumer sees no charge; the blocking interval and recovery actor are missing.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: The route labels entry 2 “Build: implement the transaction trace” and entry 3 “Test,” but entry 2 has no runnable processor and entry 3's harness is absent. Either supply/verify both artifacts before the milestone or change the promised outcome and labels to conceptual tracing; do not claim implementation and crash proof.

RELATED: `reliability.audit.md`, `coverage.audit.md`, and `examples.audit.md` own the underlying content and execution defects.

# README.md :: Architecture decision
Outcome: Classify the workload and reject at least one unsuitable infrastructure choice.
Files: `ecosystem/04`, `fundamentals/02`, then optional share-group/Connect/stream-processing branches.
EXECUTION PAYOFF: entry n/a (n/a; initial architecture decision path, no executable milestone; its conceptual choice is evaluated separately).
UNDERSTANDING PAYOFF: entry 2 (PASS; the retained-log state model explains when Kafka earns its cost).
TRANSFER: PASS
Checkpoint: after entry 2.
Scenario: A single worker pool needs per-job priority and delete-on-ack, while no independent reader needs replay.
Reasoning: Choose a work queue: the retained-log/replay model is not required, and the decision guide maps per-job acknowledgment/priorities to a queue.
Evidence: `ecosystem/04:5–26,45–51` and `fundamentals/02:21–28`.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The route produces a decision before optional ecosystem branches and supports the changed workload from already taught criteria.

# fundamentals/README.md :: Fundamentals reading order
Outcome: Produce/consume a record, explain its retained location/position, then harden the model with keys, groups, and replication.
Files: `fundamentals/01`–`05` in numeric order (entry 3 expands to three deep dives).
EXECUTION PAYOFF: entry 1 (PASS; reproduced).
UNDERSTANDING PAYOFF: entry 2 (PASS; named trace and replay model).
TRANSFER: FAIL
Checkpoint: after replication deep dive.
Scenario: RF=3, ISR has three members, `min.insync.replicas=2`, producer uses `acks=all`; predict acknowledgers, then predict election when ISR is empty but ELR is populated.
Reasoning: Separate minimum-ISR admission from the all-ISR acknowledgment condition, with a stable ISR for this probe. Safe election can include unfenced ELR when ISR is empty. The text needs explicit state transitions rather than conflating the threshold with the acknowledgment set.
Evidence: The local note's “wait for that rule” wording is ambiguous and no ELR continuation is supplied. See fundamentals.audit.md for the acknowledgment clarification, coverage.audit.md for absent ELR, and LQ-F05 for the developed failure model.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: fundamentals.audit.md owns acknowledgment precision; coverage.audit.md owns missing ELR; LQ-F02–F05 own the broader learning defects. The early executable and basic replay milestone still passes.

# application_design/README.md :: Contract-first application path
Outcome: Validate an event contract, publish/consume it from Python, then harden lifecycle/topology and optionally add registry enforcement.
Files: `application_design/01`–`05` in numeric order.
EXECUTION PAYOFF: entry 2 (FAIL; exact `uv add` commands have no project initialization, and broker setup is only an undeclared linked prerequisite).
UNDERSTANDING PAYOFF: entry 2 (PASS; contract boundary and enqueue/ack/commit mechanisms are explained).
TRANSFER: FAIL
Checkpoint: aggregate across both worker-completion probes below.
Scenario: offsets 10 and 12 finish while 11 is still running; decide the next committed offset and what a restart repeats.
Reasoning: The consecutive-offset sub-probe passes: commit only the highest contiguous completion frontier, so next offset remains 11; restart repeats 11 and may repeat later completed effects behind the gap, which must be idempotent.
Evidence: `application_design/03:29–37,41–51`.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: examples.audit.md owns missing runnable setup, quickstart/schema mismatch, ownership-loss behavior and the numeric-gap frontier defect. The text supports this consecutive-delivered-offset probe only.

## Checkpoint — out-of-order completion of delivered records
TRANSFER: PASS
Checkpoint: after application_design/03's contiguous completion explanation.
Scenario: Delivered offsets10,11,12 finish in order12,10 while11 remains running.
Reasoning: Completion of12 cannot skip the delivered unfinished11; after10 completes the safe next checkpoint is11, so restart may repeat the completed12 behind the gap.
Evidence: application_design/03 §§2–3 explicitly derives this distinction. This pass does not validate its implementation for absent offsets or ownership loss.

## Checkpoint — offsets absent from the delivered stream
TRANSFER: FAIL
Checkpoint: after application_design/03.
Scenario: Kafka delivers offsets10 and12, and both complete; offset11 was never delivered. Predict whether processing12 can advance safe progress.
Reasoning: Track completed delivered records and the next pending delivered position, not every integer. With no unfinished delivered record, progress must not stall forever at11.
Evidence: The actual Frontier algorithm waits for integer11; isolated execution returns11 then no update. KafkaConsumer4.3 explicitly permits nonconsecutive offsets. The note does not teach this distinction; examples.audit.md owns the reproduced defect.


# reliability/README.md :: Reliability reading order
Outcome: Classify crash semantics, implement transaction or outbox boundary, prove it, then recover via retry/replay.
Files: `reliability/01`, `02`, `05`, `03`, `04` as declared.
EXECUTION PAYOFF: entry 2 (FAIL; conceptual trace only).
UNDERSTANDING PAYOFF: entry 2 (FAIL; at-most-once trace and consumer dedupe premises are insufficient).
TRANSFER: FAIL
Checkpoint: after retry/replay entry.
Scenario: The worker publishes source offset 8 to `retry.5s` and crashes before committing source offset 9; predict what prevents duplicate retry records and what causes the five-second delay.
Reasoning: A safe design needs an atomic Kafka transaction or durable dedupe around recovery publication plus an explicit delaying actor/state; neither follows from a topic name.
Evidence: `reliability/03:5–36` names policy/envelope but supplies neither premise.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: The sequence says entry 2 may execute an outbox transaction although outbox is entry 5, and places the test entry before retry/outbox mechanisms it claims to prove. Route Kafka-only services through transaction→test and database services through outbox→test, then join at retry/replay.

RELATED: Coverage/examples reports own the missing mechanisms and artifacts.

# operations/README.md :: Operations reading order
Outcome: Apply least privilege and calculate partition/storage/network/catch-up capacity, then observe, recover, and administer.
Files: `operations/01`–`05`.
EXECUTION PAYOFF: entry 1 (FAIL; fragments exist but no composed allowed/denied verification can be run).
UNDERSTANDING PAYOFF: entry 2 (PASS; security-layer intersection and changed recovery-capacity arithmetic are clear).
TRANSFER: FAIL
Checkpoint: after upgrade/recovery entry.
Scenario: Brokers run 4.3 binaries and appear healthy; decide when to finalize the metadata/feature version and whether the previous metadata version remains a rollback option.
Reasoning: Verify the rolling binary upgrade before finalization; the metadata-version change has an explicit non-downgrade boundary that must gate rollback planning.
Evidence: `operations/04:18–20` says only to check release notes; the state transition and cutoff are absent.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `operations.audit.md` owns the missing security composition; `coverage.audit.md` owns upgrade operational depth.

# ecosystem/README.md :: Ecosystem decision path
Outcome: Classify data movement and transformation, then decide whether optional Kafka ecosystem mechanisms are needed.
Files: `ecosystem/01`, `02`, `03`, `04` as indexed; root architecture path offers a decision-first alternate ordering.
EXECUTION PAYOFF: entry n/a (n/a; optional decision/conceptual path, no executable milestone; usable decisions are not executed programs).
UNDERSTANDING PAYOFF: entry 2 (FAIL; the aggregate example is concrete but its closing-clock rule is incorrect/underspecified; ecosystem.audit.md E02-TIME).
TRANSFER: FAIL
Checkpoint: aggregate across selection and time-progression probes after entry 2.
Scenario: A transformation joins streams keyed differently and can tolerate hourly latency; choose the first correction or alternative.
Reasoning: A streaming join needs deliberate repartitioning for compatible keys; because latency permits simpler recomputation, batch SQL may be the better starting choice.
Evidence: `ecosystem/02:31–57`.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: The stated repartition/batch choice follows from the early criteria, but the complete stream-time lesson has a local technical defect (ecosystem.audit.md). This narrow checkpoint pass does not clear LQ-E02 or certify window closure reasoning. Later share-group currency is also locally owned.

## Checkpoint — initial processing choice
TRANSFER: PASS
Checkpoint: after ecosystem/02's engine/latency and key-boundary discussion.
Scenario: Differently keyed inputs need a join, but the application tolerates hourly latency.
Reasoning: The note supports considering batch SQL before paying continuous-state costs and flags incompatible partition keys as a streaming join constraint. This is a selection result, not a complete repartition implementation.
Evidence: ecosystem/02 §§1–2, especially its explicit batch/database alternatives.

## Checkpoint — a later wall clock without later event-time progress
TRANSFER: FAIL
Checkpoint: after the window example in ecosystem/02.
Scenario: Keep event-time progress at10:06 while wall-clock reaches10:08; an event timestamped10:04 arrives for [10:00,10:05) with two-minute grace.
Reasoning: Wall-clock arrival alone does not advance the stated event-time progress beyond the window's closing threshold. Choose and state the engine's progress model; do not infer a late/drop outcome solely from the arrival column. The existing example instead teaches exactly that unsupported inference.
Evidence: ecosystem/02 lines9–27; ecosystem.audit.md E02-TIME owns the technical correction and LQ-E02 the remaining state/recovery development. External docs verify the defect but cannot supply the missing teaching on the note's behalf.
