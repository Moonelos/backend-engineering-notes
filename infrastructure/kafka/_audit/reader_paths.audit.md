# README.md :: Explore Kafka with a runnable record
Outcome: Publish/consume `order.created`, explain retained topic/partition/offset state, then build a Python client.
Files: `fundamentals/01`, `02`, `03`, `04`, `application_design/02`, then revisits `application_design/01` and `04`.
EXECUTION PAYOFF: entry 1 (PASS; exact broker/topic/record path reproduced).
UNDERSTANDING PAYOFF: entry 2 (PASS; retained-record and offset trace supports the stated explanation).
TRANSFER: FAIL
Checkpoint: after fundamentals entry 4.
Scenario: The consumer charges a card, loses ownership before committing, and the new owner retries the same record; choose the state/idempotency boundary that prevents a second charge.
Reasoning: The path predicts redelivery from the committed position, but the only prior idempotency sentence does not define the stable identity or effect-store/provider decision that collapses the second attempt.
Evidence: `fundamentals/04:25–41` predicts the duplicate; missing premise is owned by `fundamentals.audit.md` and `coverage.audit.md`.
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
EXECUTION PAYOFF: entry 1 (PASS; role-appropriate decision scenarios and starting choices are immediately usable).
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
Reasoning: Kafka waits for all current ISR acknowledgments; below min ISR it rejects writes; safe election considers ISR then unfenced ELR.
Evidence: The local note's “wait for that rule” wording supports the wrong first answer and provides no ELR premise; see `fundamentals.audit.md`.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `fundamentals.audit.md` owns both incorrect/stale claims; the early execution/understanding milestone still passes.

# application_design/README.md :: Contract-first application path
Outcome: Validate an event contract, publish/consume it from Python, then harden lifecycle/topology and optionally add registry enforcement.
Files: `application_design/01`–`05` in numeric order.
EXECUTION PAYOFF: entry 2 (FAIL; exact `uv add` commands have no project initialization, and broker setup is only an undeclared linked prerequisite).
UNDERSTANDING PAYOFF: entry 2 (PASS; contract boundary and enqueue/ack/commit mechanisms are explained).
TRANSFER: PASS
Checkpoint: after entry 3.
Scenario: offsets 10 and 12 finish while 11 is still running; decide the next committed offset and what a restart repeats.
Reasoning: Commit only the highest contiguous completion frontier, so next offset remains 11; restart repeats 11 and may repeat later completed effects behind the gap, which must be idempotent.
Evidence: `application_design/03:29–37,41–51`.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `examples.audit.md` owns missing runnable setup and unsafe ownership-loss behavior; the text supports this commit-frontier transfer probe.

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
EXECUTION PAYOFF: entry 1 (PASS; Connect-versus-service decision is immediately usable).
UNDERSTANDING PAYOFF: entry 2 (PASS; the window/state trace explains the transformation branch).
TRANSFER: PASS
Checkpoint: after entry 2.
Scenario: A transformation joins streams keyed differently and can tolerate hourly latency; choose the first correction or alternative.
Reasoning: A streaming join needs deliberate repartitioning for compatible keys; because latency permits simpler recomputation, batch SQL may be the better starting choice.
Evidence: `ecosystem/02:31–57`.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: Both decision and changed-condition reasoning follow from the first two entries; later share-group currency is a per-note defect, not a sequence failure.
