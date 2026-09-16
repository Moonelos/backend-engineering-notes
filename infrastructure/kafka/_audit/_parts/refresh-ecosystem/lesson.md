# LQ-E01 — Decide whether Connect owns an integration
Files: ecosystem/01_kafka_connect_and_data_integration.md
LESSON: PASS
Reader: Programmer with the retained-log and checkpoint model choosing standard data movement versus application-owned domain logic; this note is an initial decision guide, not a connector setup tutorial.
Evidence: Development map:

| Promise | Prior knowledge | Passage and reasoning | Status |
|---|---|---|---|
| Source/sink and standard movement | Producers, consumers and checkpoints | Lines 7–11 identify direction, worker responsibilities and database-log CDC versus polling | developed at selection level |
| Connect versus business workflow | HTTP/domain service ownership | Lines 9–11 and 39–40 tie the choice to whether domain decisions/orchestration dominate | developed decision boundary |
| Trust and operational cost | Executable code and checkpoint model | Lines 17–23 connect installed code/REST mutation to trust and task-level verification | explained boundary; security implementation not claimed |
| Shared schema lifecycle | Application05 is linked prerequisite | Lines 25–27 explicitly name the contract owner | explicitly deferred |
| Retry duplicates | Effect-before-checkpoint crash model | Lines 36–37 give concrete sink-write/checkpoint ordering and duplicate consequence | developed causal boundary |

Reasoning burden: The reader can classify straightforward database-log transport versus multi-step business work using stated criteria and can identify the first checkpoint failure. The guide does not promise that reading it configures or operates a connector. Production Connect coverage is a collection-level question; do not manufacture a chapter failure solely because this selection guide is short.
Visual support: A source→Kafka→sink arrow could aid orientation, but the directional sentences already make that relationship easy to simulate; no compulsory diagram.
Structure: KEEP; retain this selection role and link a developed operational owner if the wider curriculum adds Connect implementation.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: LQ-E01 — The initial choice and its meaningful boundaries are explained for this role.
RELATED: coverage.audit.md should separately decide whether the collection's production data-integration promise needs connector configuration/status/checkpoint/restart depth; this guide is not evidence that those operations are operationalized.

# LQ-E02 — Develop stream state, time progress and output updates
Files: ecosystem/02_stream_processing.md
LESSON: FAIL
Reader: Programmer with retained logs and consumer checkpoints; should distinguish stateless from stateful processing and reason about windowed results, recovery, compatible keys and simpler alternatives.
Evidence: Development map:

| Promise | Prior knowledge | Passage and reasoning | Status |
|---|---|---|---|
| Unbounded stream to finite window | Repeated event arrival | Lines 7–14 define merchant/window problem and fields | developed motivation |
| Aggregate updates | Named payment amounts and timestamps | Lines 17–27 show running count/total and changed arrival | developed carrier, but wrong/underspecified closing clock separately reported |
| Recovery of owned state | Consumer checkpoint | Line 20 says restore preserves totals; lines 33–36 name changelog/checkpoint without showing relationship between recovered total and resumed input | merely stated mechanism |
| Event-time progress and grace | Event versus processing time definitions | Lines 9–14 define watermark/grace; no advancement event appears before the late decision | local correctness issue E02-TIME; not recounted as a structural severity |
| Stateful versus stateless; joins | Prior single-record processing | Lines 33–37 name stateful operations; 53–54 prescribe repartitioning but show neither a join key nor the failed/changed match | partially developed distinction, merely stated join choice |
| Output/restart verification | Running aggregate | Lines 43–44 prescribe on-time/late/restart input, but omit downstream update identity and how corrected answers replace earlier output | merely stated output interpretation |
| Engine/batch/database choice | Python service and latency needs | Lines 39–41 and 56–57 give role and latency boundaries | explained initial choice; engine implementation not promised |

Reasoning burden: Even after correcting the clock, the reader must invent why restoring the total alone is insufficient without matching input progress, why repeated emitted totals are updates rather than additions, and what key change makes the warned-about join work. These are substantive later promises, not an obligation to implement a full engine or master every streaming operator.
Visual support: Reuse one merchant/window state table with input position, restored aggregate and output key/value; interpret a crash/restart transition. A small two-input join table should expose the mismatched keys before a repartition prescription.
Structure: REWRITE; develop the existing payment example through state recovery and output interpretation, then clearly branch to joins and engine selection.
Summary: 0 critical, 0 high, 1 med, 0 low

FIX-MED: LQ-E02 — The first aggregate trace is followed by undeveloped state/recovery/join prescriptions — carry the named window through recovery and downstream interpretation, then show one keyed join contrast or explicitly defer that topic to a named owner.
RELATED: ecosystem.audit.md E02-TIME owns the central clock error; this finding owns the distinct repeated development gaps that remain after fixing it.
Proposed sequence: Select window by event timestamp → advance the chosen engine's event-time progress explicitly → emit a keyed updated result → crash and restore aggregate plus matching input progress → explain stateful joins using matching keys → compare engines and batch alternatives.
Content mapping: Keep the named merchant and payments 7–27 while correcting time semantics; expand 31–37 and 43–44 into the recovery/output stage; develop 53–54 with a small join or move that depth to a named future owner; retain 39–41 and 56–57 as decision boundaries.
Example development: Window m-7/10:00 contains pay-1 and pay-2, total35 only after pay-3. Carry the output key (merchant,window-start), stored aggregate and next input position together through restart. Contrast a consumer replacing the prior aggregate with one incorrectly summing updates. Join a merchant-keyed total with a merchant-keyed profile, then change one side to payment_id and identify the missing association.
Rewrite sample: The output key is (m-7,10:00). After two payments its value is count=2,total=30. When a late accepted payment adds 5, the next output for that same key is count=3,total=35; it replaces the previous answer. A downstream consumer that adds 30 and 35 counts the earlier payments twice. Recovery must preserve the same relationship between the remembered total and the input already included in it. Restoring total30 while resuming before pay-2 would add that payment again; resuming after pay-3 while restoring only total30 would omit 5. The engine's recovery protocol must align input progress with recovered state, not merely reload a nonempty dictionary.
Acceptance task: A checkpoint stores total30 including pay-2; an accepted pay-3 produced total35 before a crash. Explain the conditions under which replaying pay-3 restores the right answer and why a downstream sink must interpret a keyed replacement instead of summing every emitted total. Separately predict lateness when wall-clock advances but event-time progress does not.

# LQ-E03 — Per-record ownership and redelivery
Files: ecosystem/03_share_groups_and_queue_semantics.md
LESSON: PASS
Reader: Reader who understands conventional partition ownership and duplicate effects; should evaluate the different per-record delivery model, not yet deploy a Python share consumer.
Evidence: Development map:

| Promise | Prior knowledge | Passage and reasoning | Status |
|---|---|---|---|
| Concurrency beyond partitions | Fundamentals04 conventional ownership | Lines 7–9 change ownership granularity while retaining the log | developed contrast |
| Accept, release, timeout and reject | Record delivery and processing | Lines 19–29 use offsets41–43 and delivery counts to show distinct transitions | developed |
| Long work and renewal | Timed ownership from same trace | Lines 27–32 distinguish expiration, extension and successful acknowledgment | developed conceptual relationship; Python applicability fails separately |
| Ordering and repeated effects | Earlier key/commit crash model | Lines 15–17, 48–52 explain concurrent delivery and repeated still-running effects | developed boundary |
| Broker/client readiness | Product selection | Lines 34–36 correctly separate support in principle but leave this Python client's concrete limits unspecified | local factual/applicability repair |
| Evaluation drill | Timed ownership | Lines 38–39 say which two observations discriminate acknowledgment policy | explained evaluation intent; not executed here |

Reasoning burden: The state trace actually changes a condition and shows the different record outcome; the prose relates renewal, completion and idempotency. The missing current Python limits can be repaired locally without restructuring this coherent mechanism explanation.
Visual support: The existing labeled timeline makes actors, offsets, times and outcomes visible; no new diagram is necessary.
Structure: LOCAL-EDIT; retain the explanatory sequence and add the precise client limitation beside renewal and broker availability.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: LQ-E03 — No systemic lesson-development defect; conceptual explanation is coherent.
RELATED: ecosystem.audit.md E03-CLIENT owns the substantive Python-client readiness/renewal mismatch; this LESSON verdict does not approve production use of that client.

# LQ-E04 — Choose an initial messaging architecture
Files: ecosystem/04_when_to_use_kafka.md
LESSON: PASS
Reader: Python/HTTP programmer making an initial architecture classification, then taking the root path's retained-log lesson before committing to a detailed design.
Evidence: Development map:

| Promise | Prior knowledge | Passage and reasoning | Status |
|---|---|---|---|
| Initial Kafka/queue/request choice | HTTP request-response and stated workload needs | Lines 7–9 tie three distinct needs to starting choices | developed at initial classification level |
| Storage/integration alternatives | Transactional database purpose | Lines 15–22 map replay, work claims, durable stream, constraints and request/push needs to alternatives | explained selection map, not deployment recommendations |
| Why pay Kafka's complexity | Multiple independent readers/replay as requirements | Lines 24–26 state when the combined retained-log capabilities earn cost | explained; detailed log mechanics are next in the root architecture path |
| Organizational responsibilities | Team ownership and operational work | Lines 32–38 identify review inputs and explain the managed-service boundary | explained cost boundary, not a promise to teach each operation here |
| Reject incorrect queue model | Consumption versus retained history taught next on initial path | Lines 47–51 name mistaken deletion assumption and simpler alternatives | explained warning; storage model is developed by fundamentals02 |

Reasoning burden: This guide produces a provisional choice, not an architecture implementation. Its small parallel scenarios are appropriate for that role; requiring a full worked production design would erase its useful entry-point boundary. The complete architecture path must still develop retained history before treating the provisional choice as an informed final design.
Visual support: The need-to-choice table supports comparison without multiple independent changing states; a diagram would add little here.
Structure: KEEP; preserve the initial selection role and ensure the root path follows through to the retained-log model.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: LQ-E04 — Concrete starting choices and rejection criteria fit the explicitly initial decision role; do not fail the note for not implementing RabbitMQ, Redis, SQL or Kafka.
RELATED: reader_paths.audit.md owns whether the complete architecture route earns the deeper retained-log understanding it promises. The tool list does not establish comparative benchmarks or vendor feature equivalence.

# LQ-E00 — Optional ecosystem navigation
Files: ecosystem/README.md
LESSON: n/a
Reader: Reader choosing an optional extension after the basic Kafka model.
Evidence: Lines 9–17 map branches to outcomes and state when ordinary producers/consumers suffice.
Reasoning burden: Index role only; Connect and stream-processing milestone is evaluated on actual chapter prose.
Visual support: Existing contents table fits navigation.
Structure: KEEP; no independent tutorial obligation.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: LQ-E00 — Legitimate optional-branch index.
