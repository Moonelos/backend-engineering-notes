# LQ-G00 — Collection-wide learning and editorial plan
Files: README.md; all 24 teaching notes and five section indexes under fundamentals/, application_design/, reliability/, operations/, ecosystem/.
LESSON: FAIL
Reader: A Python/HTTP programmer starting without Kafka expertise; must learn the retained-log model, build a working application, reason through failure, and operate within stated production boundaries.
Evidence: Full prose read across all 24 notes, not just outlines. Development map: first record and repeated read are developed in fundamentals/01; storage/cleanup and routing decisions repeatedly become claims in fundamentals/02–03; assignment and replica mechanisms in04–05 introduce new independently changing state without sufficient intermediate reasoning. Application code introduces real artifacts but compatibility, worker state and registry recovery are not developed throughout. Reliability has useful transaction/outbox traces but handoffs to retry, effect deduplication and actual crash proof are incomplete. Operations capacity is a strong continuous worked example; upgrade/admin breadth outstrips its worked retention/DR cases. Ecosystem decision notes have legitimate narrow scopes; time/state reasoning still needs technical and teaching repair. See each LQ unit's precise source map and related correctness/execution evidence.
Reasoning burden: A beginner repeatedly leaves a successful small example for new terminology, multiple remedies and operational prescriptions that require expertise the path has not supplied. Later cross-links sometimes lead to another summary or nonexistent harness. This cannot be repaired by adding a glossary sentence or diagram to each existing subsection. Early executable success and extractable facts are useful but insufficient for the full learning promise.
Visual support: Use a consistent orders/billing/analytics example for the initial record and reader state, with interpreted before/after positions. Add separate actor/state lanes only when introducing a new boundary: partition ownership, replication/controllers, database effects and retry scheduling. Keep a visual only when it helps track those changing states. The collection needs interpreted transitions rather than a quota of drawings.
Structure: REORDER + REWRITE; develop coherent units and combine dependent sections where they form one learner question. Existing file count is not an acceptance criterion.
Summary: 0 critical, 0 high, 0 med, 0 low
RELATED: Canonical chapter findings below, coverage.audit.md, reader_paths.audit.md and examples.audit.md own specific defects. This assembled judgment and plan do not add another duplicate severity.
Proposed sequence: (1) Why an order service needs retained events, followed by the disposable round trip. (2) Where events remain and how billing/analytics independently read them: addresses, current/saved positions, lag, finite retention and cleanup. (3) Which events must share order: key choice, concurrent independent orders, and the cost of hot entities; clearly defer advanced migration to its developed continuation. (4) How group membership moves work: normal processing, interrupted handoff, checkpoints and the need for duplicate-safe effects. (5) What storage and controller failures change: replicated tail, acknowledgment, eligibility and metadata majority. Then build one contract-first Python project before adding bounded workers; derive reliability protections from three distinct crash boundaries; complete the executable crash harness before claiming implementation; carry a named application into security, capacity, incidents and lifecycle decisions. Ecosystem remains optional branches at the relevant problem.
Content mapping: Preserve fundamentals/01's concrete result. Join the group-identity/bookmark parts of fundamentals/04 with02's read-state explanation, then let04 develop ownership changes rather than repeat definitions. Within02, put lag and retention around the same changing positions; defer compaction details only to a named developed owner. Reorder03's production tactics after key selection; retain05 as a distinct replica/controller unit with worked state. Keep application01 before02 on every runnable route, reconcile the quickstart payload and project setup, and break application03's large block into explained state transitions before presenting its complete version. Reliability01–02 should derive protections before summarizing them; combine retry/DLT/replay explanations around one failure lifecycle in03. A separate idempotency or CDC chapter is optional only if it earns a distinct outcome; do not fix every gap by creating another file. Operations02 supplies useful arithmetic for application04, which should bring forward the necessary small example;05's broad admin reference must point to real developed procedures. Preserve production depth and move it to explicit destinations rather than deleting it.
Example development: Start with ord-42 creation and two independent readers. Add a second event, advance one reader, then remove old history. Introduce ord-43 only to expose safe independence, then introduce a hot entity. Move the same billing record between group members and compare effect/checkpoint state. Replicate the same record across brokers, then separately lose controller majority. Later use the same event identity across schema evolution, intentional resend, retry, outbox and controlled replay so each new boundary has visible prior state. Change examples deliberately when their business question differs, such as latest-profile compaction.
Rewrite sample: Billing creates an invoice from ord-42 while analytics counts the same order. If reading removed the event, whichever application ran first would prevent the other from doing its job. Instead, keep the event in orders and give each application its own saved place in that history. Suppose ord-42 is at partition0, offset8. Billing has finished it and saved9; analytics still has8. The event is unchanged: only billing's saved position moved. Now stop billing after it creates the next invoice but before saving10. On restart its bookmark still says9. That bookmark tells Kafka where to resume reading; it does not tell Kafka whether the external invoice exists. We can now see why replay and duplicate-safe business effects are connected, before introducing a deduplication table or transaction API.
Acceptance task: A learner must reason through a previously unseen combination: one group offline, another crashing after an effect, finite retained history, a changed key distribution and one unavailable replica. At each step identify available records, saved positions, possible repeated/lost work and the layer that owns the needed protection. They must then run the documented assembled project and synchronized crash test with the promised observations. Existing canonical failures block this outcome; generated teach-back is a textual check, not a human-learning study.

# LQ-G01 — Root learning map
Files: README.md
LESSON: n/a
Reader: Programmer selecting exploration, production or architecture paths.
Evidence: The root supplies three named routes and stop points; their actual dependency and implementation outcomes are assessed in reader_paths.audit.md.
Reasoning burden: The index maps destinations; it is not a standalone Kafka explanation.
Visual support: Existing structure sketch and contents table suffice for navigation.
Structure: KEEP; repair the route definitions through the path findings.
Summary: 0 critical, 0 high, 0 med, 0 low
RELATED: reader_paths.audit.md owns the contract/client ordering and premature production implementation claims. LQ-G00 judges the assembled learning promise.

# LQ-F01 — First event round trip
Files: fundamentals/01_first_event_round_trip.md
LESSON: PASS
Reader: Programmer comfortable with a shell and Docker, without Kafka knowledge; produce one event, interpret its address, and repeat its read in a disposable environment.
Evidence: Development map: broker/process and record path are developed at 7–31 through commands and an exact expected event; retained-versus-consumed state is developed at 38–52 by running the same read again and interpreting why the record remains; topic/partition/offset coordinates are developed at 56–66 with the observed zeros and another partition's possible offset zero; disposable storage failure and production boundary are explicit at 70–87. Custom-listener detail at 75–77 is a bounded troubleshooting signpost, not an instruction to implement a listener topology.
Reasoning burden: The reader can connect a repeated read to preserved broker state. The command is narrow enough that production replication, authentication, and client internals may be explicitly deferred. A delayed broker startup is described; actual execution is a separate evidence axis.
Visual support: The producer→partition→consumer diagram at 46–50 identifies the retained object; prose interprets the branch by asking the reader to repeat the command.
Structure: KEEP; one coherent first-result lesson, with a local deprecated-flag correction.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The lesson develops its bounded capability without requiring an invented full production walkthrough.
RELATED: fundamentals.audit.md F-CLI; examples.audit.md owns reproduction status.

# LQ-F02 — Independent readers, stored history, and disappearing records
Files: fundamentals/02_log_topics_partitions_and_offsets.md
LESSON: FAIL
Reader: Programmer after the round trip, without prior consumer-group or log-cleanup knowledge; explain record coordinates and use that model to reason about independent reading, cleanup, lag, and an expired recovery position.
Evidence: Development map: named partition addresses and commit/non-deletion are developed at 7–17, but reader-group identity is assumed there and only named again at 25; independent applications at 23–25 are stated without a second position in the trace; per-partition order at 34–44 is explained with separate sequences; compaction at 50–61 has a useful three-record reduction but switches to profiles and introduces tombstones without their deletion meaning; retention segments are named, not illustrated; lag at 67–69 is a formula and monitoring prescription, not a worked continuation of the positions already shown; reset behavior at 82–84 names two outcomes without showing what has disappeared or what replay can recover. These are substantive recommendations, not explicitly deferred topics.
Reasoning burden: The novice must assemble record storage, two independent bookmarks, cleanup, and recovery into a temporal model alone. The opening successfully teaches one conclusion; the remaining fragments leave the learner to invent which state changes after processing, committing, or deletion. In particular, “earliest” after expiry can sound like recovering the original history when only retained history is available.
Visual support: Expand the existing partition sketch into a before/after table with retained offsets, billing and analytics saved positions, and log-end position. Interpret each row after one action. The separate P0/P1 arrows and one compaction reduction do not presently connect that state to lag or recovery.
Structure: REWRITE; develop one retained-history lesson rather than insert a glossary sentence into each small section. Keep the file boundary; join related sections and make cleanup a consequence of finite history.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: LQ-F02 — The storage foundation repeatedly states conclusions without developing the independent state changes needed to apply them. Rebuild its continuous explanation around named readers and a shrinking retained log; use a clearly separate latest-state example only when changing the cleanup question.
Proposed sequence: Why billing and analytics need independent reads → append and identify one record → advance one group's saved next position while the other stays behind → compare partition-local ordering → compute lag from those positions → remove old history and resume → contrast history preservation with latest-keyed-state reconstruction. Close with the distinction between replaying retained events and recovering deleted information.
Content mapping: Keep 7–17 as the first checkpoint after introducing the group as a named logical subscription; merge 21–44 with that trace; move 65–76 beside the evolving bookmark table; develop 80–88 directly after retention removes named offsets; retain 48–61 as a later cleanup comparison with a defined null-value deletion record, or explicitly defer detailed compaction settings to application_design/04_topic_and_partition_design.md. Preserve all useful limits; the result need not add another file.
Example development: Begin with orders P1 offsets 0=B, 1=C, 2=D and two groups billing and analytics. Show billing process B then save 1 while analytics stays at 0; append E at 3, making log end 4. Calculate each group's offset-distance lag. Expire 0 and 1, leaving earliest 2; walk the stale analytics bookmark through earliest/latest/error choices. Explain that consumer progress never reserved the deleted records. Then introduce customer-profile as a different business question and interpret a compaction before/after sketch without renumbering surviving offsets.
Rewrite sample: Billing and analytics need the same orders for different work. Give each application a name for its subscription: `billing-v1` and `analytics-v1`. Kafka stores their saved positions separately. Suppose P1 contains B at 0, C at 1, and D at 2. Billing finishes B and saves 1, meaning “resume with C”; analytics still has 0. B has not moved or disappeared. Only billing's bookmark changed, so analytics can still read B. Now suppose cleanup removes offsets 0 and 1 while analytics is offline. Its saved 0 still tells us where it wanted to resume, but that record no longer exists. Choosing the earliest available position starts at D, offset 2; it cannot recreate B or C. This is why the lifetime of stored history and the progress of a reader must be reasoned about separately.
Acceptance task: Given P0 retained offsets 4–7, log end 8, billing checkpoint 6 and analytics checkpoint 2, explain each offset-distance, which position is outside retained history, and what earliest versus latest reset can and cannot recover. Then advance only billing's checkpoint and explain why neither analytics nor stored records changed. Require intermediate state reasoning, not a copied definition.

# LQ-F03 — Choosing an ordering domain before production routing tactics
Files: fundamentals/03_partitioning_keys_and_ordering.md
LESSON: FAIL
Reader: Programmer with the retained-log model, choosing a key and judging ordering/skew/expansion trade-offs for the first time.
Evidence: Development map: split created/cancelled failure at 7–9 and shared-key routing at 15–22 are developed; serialized bytes/client partitioner compatibility at 27–30 is a concrete test prescription but interrupts the first key-choice model; account-versus-order invariant at 36–38 is explained briefly; hot-entity key splitting at 40–42 is prescribed without showing the lost order or a reconstruction mechanism; expansion at 50–52 explains why old and new records can separate; new-topic migration and stable logical buckets at 54–55 are named remedies without mapping, cutover, or destination; timestamp/retry/causal-order verification at 61–66 and entity sequencing/version/database alternatives at 75–77 are further decisions left stated.
Reasoning burden: The reader can predict same-key affinity under stable placement. That does not let a novice design a stable logical bucket, preserve a lifecycle during migration, or choose between splitting load and preserving an invariant. Treating the strongest opening trace as proof of the later design advice mistakes recoverable facts for a developed decision lesson.
Visual support: Keep the good-key diagram. Add one small workload/state table showing which transitions must stay ordered and which unrelated orders may run concurrently; later use a before/after placement table with old and new records and interpret the migration hazard. Show a bucket-to-physical-partition mapping only if that strategy is actually taught.
Structure: REORDER + REWRITE; first develop key choice and the competing throughput requirement, then give clearly bounded production continuations instead of equal-weight miniature advice sections.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: LQ-F03 — The note promises key and ordering decisions but repeatedly hands the reader unexplained remedies after its successful first trace. Develop the trade-off through changed conditions, and teach or explicitly defer each advanced recommendation with a real owner.
Proposed sequence: State a lifecycle invariant → compare a bad and good key → separate append order from business causality → introduce one hot entity and explain what splitting sacrifices → show partition expansion changing future placement → choose whether advanced compatibility/migration is needed and follow its named continuation.
Content mapping: Keep 5–25; move 34–44 immediately after it and develop the skew contrast; join 59–77 with the causal-order boundary instead of introducing several new alternatives at the end; move 27–30 into a later client-compatibility check; retain 48–55 as the reason for a migration lesson owned by application_design/04_topic_and_partition_design.md and operations/05_configuration_and_topic_administration.md, but those destinations must actually teach the relevant mapping/handoff before claiming they solve it. Do not silently delete logical-bucket or version-check depth: develop it there or label it explicitly outside this introductory outcome.
Example development: Keep ord-42 through created→paid→cancelled, with ord-43 independently progressing. Change only the key to show what can now overlap. Add a hot account requiring more throughput but one indivisible balance invariant. Finally show a hypothetical stable hash value 8 mapping to 8 mod 6 = 2 and 8 mod 12 = 8, clearly labeled illustrative rather than a universal client algorithm. Old records remain on P2; new records can reach P8. A migration plan must now explain the ordering handoff rather than merely change the topic name.
Rewrite sample: Choosing `order_id` lets different orders progress independently while keeping each order's lifecycle in one partition. That works because billing must interpret `paid` relative to earlier changes for the same order; it does not need ord-42 to finish before ord-43. Now imagine one order produces enough work to saturate its partition. Adding a random suffix to its key may distribute that work, but it also puts `paid` and `cancelled` back on independent sequences. We have removed the very constraint the key was expressing. Before splitting the key, decide whether those operations can commute or whether the application will explicitly coordinate their versions. A throughput improvement is not a proof that the original lifecycle is still valid.
Acceptance task: A ledger has one extremely busy account and requires balance changes in a valid sequence. Explain why key=account_id meets the ordering requirement, why random salting changes it, and why increasing partition count does not move old records. Identify the additional mechanism or a named later lesson needed before choosing a migration; “stable buckets” alone is not an answer.

# LQ-F04 — Ownership, saved progress, and an interrupted handoff
Files: fundamentals/04_consumer_groups_offsets_and_rebalancing.md
LESSON: FAIL
Reader: Programmer who knows a group's independent next-offset bookmark; predict assignment and recovery before implementing concurrent workers.
Evidence: Development map: three partitions/four consumers at 7–15 develops the concurrency ceiling; independent group identity and saved/live position at 21–26 are explained but not shown together; rebalance and duplicate charge at 32–39 provide a useful failure trace while leaving the coordinator and checkpoint state implicit; idempotency at 41 is a remedy name with no changed-effect trace; poll limits, pause, worker separation and safe commit frontier at 47–50 are multiple prescriptions without the corresponding in-flight state; protocol choice at 52–57 names an external operations owner that lacks its promised rollout check; diagnostic bullets at 63–69 present conclusions without a worked observation-to-hypothesis sequence; auto-commit loss at 78–79 adds a second crash window without connecting it to the first.
Reasoning burden: The student must mentally combine partition ownership, processing still in flight, saved checkpoints and external effects. Neither the static assignment diagram nor the two-line duplicate trace teaches why an old worker can still cause a side effect after reassignment, or why finishing a later record must not advance past unfinished earlier work. The advertised safe-handoff understanding remains dependent on expert inference.
Visual support: Use one timeline with broker coordinator, C1, C2, saved next offset and effect store. Keep the same offset values through normal processing, crash before commit, and commit before completion. A small in-flight table makes the safe commit frontier visible; a larger cluster topology would not resolve this burden.
Structure: REWRITE; combine identity, assignment and checkpoint sections into one evolving handoff lesson, then separate optional concurrency/protocol depth with explicit destinations.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: LQ-F04 — Disconnected ownership and failure fragments do not develop the handoff model needed to judge safe consumer behavior. Build the normal sequence and change one failure point at a time before prescribing worker and idempotency tactics.
RELATED: coverage.audit.md, Consumer protocol migration, owns the absent operational rollout; this lesson finding does not count that omission again.
Proposed sequence: Two subscriptions versus two members of one subscription → assignment and coordinator role → fetch/process/save in one partition → handoff before saving → repeated delivery versus repeated effect → early save causing missing effect → optional bounded concurrency and protocol continuation.
Content mapping: Keep 7–15 after a short group identity bridge from 19–26; merge 30–41 and 76–79 as contrasting crash windows; develop 45–50 only after showing unfinished work, or defer full worker design to application_design/03_processing_loops_backpressure_and_shutdown.md; retain protocol version/config detail at a real operations owner; rewrite 61–69 as interpreted observations with more than one possible cause instead of a deterministic diagnosis list. Preserve conventional-versus-share-group boundary at 81–83 as a signpost.
Example development: C1 owns P0, saved next=8, fetches 8 and applies invoice(evt-8), then crashes before saving 9. The coordinator reassigns P0 to C2, which resumes at 8; the saved bookmark cannot prove the effect was absent. Reuse evt-8 in a deduplicating effect store to show the second attempt returning the prior outcome. Contrast saving 9 before invoice completion. Only then add offsets 9 and 10 to illustrate an unfinished lower offset holding back the commit frontier.
Rewrite sample: At the start, Kafka's saved checkpoint for billing on P0 is 8. C1 reads event 8 and creates its invoice. If C1 crashes now, the invoice can exist even though Kafka still stores 8 as the next position. The group coordinator on a broker helps manage the group's membership and partition assignment; when C2 takes over, it resumes from that saved checkpoint. C2 therefore attempts event 8 again. No contradiction exists: one current partition owner does not tell Kafka whether an earlier owner's external invoice succeeded. Give both attempts the same event identity, and make the invoice store record that identity atomically with the invoice. The second attempt can then discover the existing result instead of creating another invoice. The complete database or provider implementation belongs in the reliability lesson; the reason it is needed belongs here.
Acceptance task: With saved next=8, offsets 8 and 9 fetched, effect 9 complete and effect 8 still pending, explain why saving 10 can lose effect 8 after a crash. Then explain what may repeat if no new checkpoint is saved and why idempotent producer settings do not deduplicate the invoice. State the broker-versus-application responsibilities explicitly.

# LQ-F05 — Replica state, acknowledgments, and controller availability
Files: fundamentals/05_replication_leaders_and_kraft.md
LESSON: FAIL
Reader: Programmer without quorum background; explain which broker/controller failures preserve acknowledged data and which can stop progress.
Evidence: Development map: single-copy disk-loss motivation at 7–9 is useful but the multiple-copy contrast already assumes ISR/acks/minimum semantics; leader/follower diagram at 15–26 identifies actors but does not show their changing offsets or the acknowledgment point; settings at 32–37 state a threshold contract with a local correctness error; metadata-versus-payload at 43–52 is well explained categorically, but quorum loss remains a claimed consequence without majority/voter reasoning; topic inspection and broker-stop verification at 58–60 are prescribed with no interpreted result; stale election at 62–63 states data loss without showing the absent tail; managed-service boundary at 72–74 is an appropriate brief decision boundary.
Reasoning burden: Several independently changing states—replica copy position, ISR eligibility, admission floor, acknowledgment, and controller majority—are compressed into labels and warnings. Even after fixing the acknowledgment sentence, the reader still has to invent the failure table that fulfills the chapter's central availability/durability promise.
Visual support: Replace or extend the static arrows with rows for leader/follower copied offset and ISR, marking when the producer receives success. Use a separate three-controller majority sketch to explain why payload copies can survive while new leadership cannot be coordinated. Interpret an unavailable case alongside the successful failover; diagrams should expose state rather than add decorative broker boxes.
Structure: REWRITE; build the data-replication model first, then contrast control-plane failure without mixing the two kinds of copies.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: LQ-F05 — The chapter promises failure prediction but presents the needed multi-state reasoning as a settings summary and several separate warnings. Develop one acknowledged record through successive failures, followed by the independent controller-quorum model.
RELATED: fundamentals.audit.md F-ACK owns the incorrect wait/admission claim. coverage.audit.md owns missing current safe-election/ELR depth; do not count either twice as additional editorial findings.
Proposed sequence: Why one disk is insufficient → followers copy a named log tail → producer acknowledgment and minimum ISR as distinct decisions → one follower slow, removed, or failed → leader failure with eligible up-to-date successor → stale-tail/data-loss boundary → separate controller majority and unavailable election → interpreted verification and managed-service boundary.
Content mapping: Keep the offset-51 scenario and 19–23 topology; merge 5–37 into an evolving state trace using the corrected configuration semantics; develop 41–52 as a distinct control-plane comparison with a plain majority example; join 56–63 to the replica trace's observable outcomes; preserve the useful 70–74 operational-ownership boundary. The canonical replication chapter should contain first-time reasoning, with detailed administration and ELR rollout controls continued in operations.
Example development: Start with brokers 1/2/3 in ISR, all through offset 50. Append 51 to leader 1, then show follower 2 and follower 3 catching up in separate rows before acknowledging all-current-ISR success. Change ISR to {1,2} with minISR=2; then {1}, where the write floor prevents continuing the same promise. Stop leader 1 and show a successor's retained tail. Separately show three metadata voters losing one versus two, without pretending metadata replicas contain event payloads.
Rewrite sample: Having three configured replicas does not mean all three already hold the new record. Suppose brokers 1, 2 and 3 are in ISR and each ends at offset 50. Broker 1 appends record 51 first. While broker 3 still ends at 50, an `acks=all` write cannot report success merely because brokers 1 and 2 have copied 51: broker 3 is still part of the in-sync set. If it catches up, the full set has 51. If it falls out of ISR, the set being waited on changes; the separate `min.insync.replicas=2` condition still requires enough replicas for the write. These are two different questions: “are there enough eligible replicas to accept this durability promise?” and “has the current in-sync set received this record?” Track both before reasoning about losing the leader.
Acceptance task: Given ISR={1,2,3}, minISR=2, and only brokers 1/2 holding the new tail, decide whether all acknowledgments are satisfied; then change ISR to {1,2} and to {1}. Separately remove two of three controller voters while broker disks remain intact and explain which data still exists and which new coordination actions cannot proceed. Include a current ELR scenario only after the required eligibility rules are taught.

# LQ-F00 — Fundamentals navigation
Files: fundamentals/README.md
LESSON: n/a
Reader: A learner selecting the first Kafka route.
Evidence: Lines 9–29 provide file roles, outcomes and a stop point; lines 33–36 explicitly permit no prior Kafka knowledge. This is an index rather than substantive lesson prose.
Reasoning burden: The table supplies navigation; the linked teaching units bear their own explanatory obligations.
Visual support: The table is sufficient for route selection; no system diagram is required in an index.
Structure: KEEP; revisit advertised outcomes only after repairing the teaching chapters, without weakening the user's from-zero promise.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: Navigation is usable. This n/a is not a PASS for the linked fundamentals sequence.

# LQ-A01 — Event contracts across independent deployments
Files: application_design/01_event_contracts_and_schema_evolution.md
LESSON: FAIL
Reader: Python/HTTP programmer who has read fundamentals; should validate a meaningful event and reason about independently deployed old/new readers and retained records.
Evidence: Development map across the full promise:

| Promise | Earned starting knowledge | Passage and worked reasoning | Status |
|---|---|---|---|
| Envelope and boundary validation | Python dictionaries, Kafka retained bytes | Lines 7–71 connect event fields to purpose and provide schema/validator with accepted input | developed |
| Additive deployment evolution | Retention, validation | Lines 77–82 explain deployment skew and removal risk, but never track one writer and two deployed readers through a change | merely stated for deployment choice |
| Backward/forward/full compatibility | Old/new data named in 88–90 | Lines 115–119 call one unchanged validator for both directions; no two reader rules or rollout state to compare | merely stated for actual evolution |
| Wire shape versus business meaning | Integer money field | Lines 92–96 contrast integer/string shape, but 122–130 fail by type, not by changed meaning with unchanged type | partially developed; semantic check stated |
| Event versus command | HTTP action intuition | Lines 136–140 compare completed order fact with an instruction for one worker | developed at the promised conceptual level |
| New event generation; blob/privacy boundary | Shared envelope | Lines 149–158 explain corrupt interpretation and unsuitable retained payload; concrete implementation is not promised | developed as boundaries; registry explicitly deferred to 05 |

Reasoning burden: The reader can repeat compatibility definitions but must construct the reader/writer version matrix and deployment sequence that make those definitions actionable. The strongest runnable validator does not teach the later evolution promise. This is a focused development defect, not a demand for a bigger envelope or more files.
Visual support: A two-reader/two-record matrix with cells explained by the actual schema rule, followed by a deployment timeline, would separate old/new reader identity from old/new payload identity.
Structure: REWRITE; develop the compatibility section around the existing order example while retaining the validator and event/command boundary.
Summary: 0 critical, 0 high, 1 med, 0 low

FIX-MED: LQ-A01 — Compatibility remains a labeled set of directions rather than a worked deployment decision — stage an old reader, new reader, retained record and new record, explain each acceptance result, then change the meaning without changing the JSON type.
RELATED: examples.audit.md, application_design/01 compatibility-tests block, owns the misleading executable test and missing test filename. Its correction is necessary but replacing test code alone does not provide the lesson's missing deployment reasoning.
Proposed sequence: Validate one event → why a stored event outlives deployment → run both reader generations against both payload generations → derive allowed rollout/replay directions → show a same-type semantic change that shape validation cannot reject → keep event/command and payload boundaries.
Content mapping: Keep lines 7–71; develop 75–132 into the version-matrix lesson; retain 136–158 as design limits; preserve the registry link to 05 rather than introducing registry operations here.
Example development: Keep ord-42 and total_minor=2590. V1 lacks coupon_code; V2 adds an optional field. Give both reader rules, use historical/new payloads, then reinterpret 2590 as major units without changing its integer type. Explain why schema acceptance and correct price are separate outcomes.
Rewrite sample: Billing R1 requires order_id, currency and total_minor and ignores unknown fields. R2 keeps those requirements and additionally reads an optional coupon_code. The retained order has no coupon_code, so R2 uses its stated missing-field behavior and still reads the order: this is the backward direction. A new order containing coupon_code also reaches R1; R1 ignores that extra field, so this is the forward direction. Those two results justify a rolling deployment for this particular change. They do not justify changing what 2590 means. If the writer starts meaning 2590 euros instead of 2590 cents, both validators can accept the integer while billing charges the wrong amount; the business assertion must still expect EUR 25.90.
Acceptance task: Make coupon_code required in R2 while historical records lack it. Explain which matrix cell fails, why old-reader tolerance does not repair that failure, and what missing-field behavior or migration would be needed before historical replay.

# LQ-A02 — A synchronous Python round trip and its boundaries
Files: application_design/02_python_producers_and_consumers.md
LESSON: PASS
Reader: Python programmer with the local broker, group/offset model and event_contract validator available; should run and explain one synchronous round trip and recognize when a worker needs further lifecycle design.
Evidence: Development map across the full promise:

| Promise | Prior knowledge | Passage and worked reasoning | Status |
|---|---|---|---|
| Validate, publish, receive | Contract validator and topic | Lines 13–72 use the same ord-42 payload, callback, flush, poll and output | developed, execution assessed separately |
| Local enqueue versus broker acknowledgment | Function call and retained record | Lines 76–81 interpret produce versus callback and why flush belongs at script/shutdown boundaries | developed |
| Processing versus committed checkpoint | Fundamentals 04 checkpoint/replay | Lines 85–89 map print→commit and crash window to duplicate effect | developed; idempotency implementation explicitly deferred |
| Bounded failure/shutdown | Python try/finally | Lines 35–39, 48–65 and 70–72 expose delivery, timeout and close paths | developed |
| Embedding and scaling decision | Process versus HTTP request | Lines 96–114 explain lifecycle ownership and web scaling changing group membership; next chapter is named lifecycle owner | developed as a boundary, not a complete async-service recipe |
| Full production integration | Above round trip | Lines 91–92 announce additional requirements; authentication/metrics owners are elsewhere in the collection | explicitly deferred |

Reasoning burden: The main state transitions are carried by one program and interpreted by the prose; the novice does not need to invent the difference between function return, broker acknowledgment and checkpoint. The earlier/later validator-route defect is a path defect, and incompatibility with the quick-start payload is an executable composition defect, not evidence that the whole explanation is causally empty.
Visual support: Existing ordered code plus the short enqueue/acknowledgment and effect/commit explanations suffice at this scope. A diagram is optional.
Structure: KEEP; preserve the bounded synchronous introduction and its explicit move to lifecycle work.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: LQ-A02 — The lesson develops its bounded synchronous-client promise; do not force a merge with the contract or worker chapter.
RELATED: examples.audit.md owns runnable composition; reader_paths.audit.md owns the root exploration path's late validator dependency. A current AsyncIO alternative is discussed in the research handoff, without treating this synchronous example as obsolete.

# LQ-A03 — Build the bounded worker from owned state
Files: application_design/03_processing_loops_backpressure_and_shutdown.md
LESSON: FAIL
Reader: Python programmer who has run the single-record client; should explain and implement a bounded worker that preserves partition ownership and safe checkpoints during concurrency and shutdown.
Evidence: Development map across the full promise:

| Promise | Prior knowledge | Passage and worked reasoning | Status |
|---|---|---|---|
| Why backpressure is needed | Single poll/process loop | Lines 7–25 connect 500 tasks/20 DB slots to overload and distinguish rate from concurrency | developed motivation; sizing 100/20/50 remains unexplained |
| Out-of-order completion and checkpoint | Saved next offset | Lines 31–37 show 10/11/12 and prohibit committing through 11 | developed for one dense sequence |
| Per-partition state bookkeeping | Above trace | Lines 86–106 introduce next_offset/done and mutation, but no walkthrough maps observed→running→completed→safe offset across calls | merely stated by code |
| Pause/resume plus polling | Fundamentals 04 | Lines 173–191 and 203–206 assert how pending count, assignment and paused flag compose; no full/half-full state transition is interpreted | merely stated integration |
| Revocation and deadline | Group ownership | Lines 43–45, 140–166 and 192–206 combine draining, commits, unassignment and running futures without an ownership timeline | merely stated integration; executable defect separately owned |
| Shutdown and duplicate effects | Earlier crash window | Lines 208–233 provide a slow/fast termination drill, observable gap replay and idempotency boundary | developed test intent, not proof of every callback branch |
| Retry/metrics and parallelism limits | Above worker | Lines 235–247 defer production harness and warn against relaxing required order | developed boundary; retry implementation explicitly deferred |

Reasoning burden: The opening three-offset trace is useful but cannot explain the independently changing pending map, frontier, assignment and termination state of the assembled worker. A beginner must reverse engineer callback ordering and decide when an old owner may still commit. The repair must make those states visible before the complete program, not add another general warning after it.
Visual support: Use one per-partition state table with assignment generation, fetched records, completed records and committed-next offset. Add a timeline contrasting graceful revocation with ownership already lost, including late handler completion; interpret which state may change in each case.
Structure: REWRITE; keep the note's single coherent worker responsibility, develop staged state transitions and then present the corrected assembled worker.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: LQ-A03 — The central safe-worker capability is presented as a large composition whose ownership and checkpoint transitions are not taught — introduce its state machine in stages and trace the ownership boundary before interpreting the complete implementation.
RELATED: examples.audit.md owns actual worker defects; correcting callbacks or the frontier implementation does not replace the explanation of their invariants.
Proposed sequence: Start from the existing one-record loop → bound submission independently of polling → track one partition's completion frontier → add another partition → introduce revoke/lost ownership → apply shutdown deadline → assemble and run the controlled drill.
Content mapping: Keep failure motivation 7–37, expand the 10/11/12 trace into state transitions before lines 55–201, rewrite explanation 203–206, preserve the termination drill 208–233 and production boundaries. Retain within-partition concurrency as an explicitly advanced stage after showing the sequential-per-partition alternative.
Example development: P0 fetches 10,11,12; completion order is 12,10,11. P1 finishes independently. Next revoke P0 while 11 is still running and observe late completion after ownership changes. Show pause at bounded capacity and resumption at the lower threshold as separate state from checkpoint progress.
Rewrite sample: P0's saved next offset is 10. Finishing record 12 does not make 13 a safe checkpoint: after a crash the group must still return to 10, because 10 and 11 have not finished. When 10 completes, the safe checkpoint becomes 11; we remember that 12 finished, but cannot cross the unfinished 11. Once 11 completes, the remembered success of 12 lets the checkpoint advance to 13. That reasoning applies only while this worker owns P0. If ownership has already been lost, a late success is not permission to commit on the new owner's behalf; the handler result and the right to publish a checkpoint are different pieces of state.
Acceptance task: P0 completes 12, then 10; P1 completes its own next record; ownership of P0 is lost before 11 completes. State each partition's safe checkpoint and explain why finishing old P0 work later must not advance the new owner's checkpoint. Then repeat with a graceful drain before revocation completes.

# LQ-A04 — Derive a topic design from a workload
Files: application_design/04_topic_and_partition_design.md
LESSON: FAIL
Reader: Programmer with partition/key/group basics; should turn workload, ordering, access and replay requirements into a defensible topic design.
Evidence: Development map across the full promise:

| Promise | Prior knowledge | Passage and worked reasoning | Status |
|---|---|---|---|
| Boundary by access/ownership | Topic as named stream | Lines 7–20 and 56–60 connect shared policy with the payments/public-catalog contrast | developed for access separation |
| Partition count from workload | One active conventional consumer per partition | Lines 26–29 say peak bytes, handler capacity and headroom without mapping a measured workload to a count | merely stated |
| Replay retention versus latest keyed state | Fundamentals 02 brief cleanup overview | Lines 8 and 42 offer labels, no downtime/rebuild requirement or contrast explains a retention choice | merely stated decision |
| Key and skew | Fundamentals 03 | Line 41 repeats a default; changed ordering/skew requirements are unnamed, so no applied trade-off | merely stated here; earlier fundamentals owner needs development |
| Ownership, writer ACL and naming | HTTP programmer; no earned ACL policy yet | Lines 35–44 list a review checklist; administrative implementation explicitly linked at 18–20 | explained ownership purpose; policy implementation deferred |
| Migration and review result | Above decisions | Lines 28–29 state asymmetry; 46–47 require a migration plan without showing one or pointing to its worked owner at that point | merely stated |

Reasoning burden: The reader can restate a checklist but cannot derive the advertised design. The worked access contrast should become the model for workload, retention and migration decisions. A shorter checklist is useful after a developed lesson, not as the whole beginner decision guide.
Visual support: One workload-to-decision table with measured inputs, calculation, assumptions and a changed condition; a replay timeline should show outage, retained interval and recovery time rather than just the word retention.
Structure: REWRITE; develop the existing design guide around one service and explicit decision branches; retain its reference table as the final review aid.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: LQ-A04 — The central promised design decisions lack a worked path from requirements to choices — derive one complete topology, then change load, key skew and replay needs and reconsider it.
RELATED: coverage.audit.md owns depth inventory for topic sizing and compaction; attach its same-root underdevelopment to LQ-A04 rather than counting an identical new severity. Distinct absent cleanup mechanisms remain coverage-owned.
Proposed sequence: Name order service requirements → decide isolation and key → derive provisional parallelism from measured handler capacity → test skew and broker limits → derive replay retention → define ownership and migration boundary → use checklist for review.
Content mapping: Keep payments/catalog contrast 16–20 and 56–60; develop 7–10 and 24–29 using workload inputs; expand cleanup row 42 into a replay/latest-state contrast; move checklist 39–47 to the end; retain links to operations for configuration and capacity verification.
Example development: Orders arrive at 600 records/s; a measured sequential partition worker sustains 200 records/s at acceptable latency. Derive the balanced-load floor of three partitions, choose and test explicit headroom, then route 500 records/s to one order key. Add a consumer outage of two days plus a measured one-day catch-up budget and discuss why the replay window needs margin beyond those three days. State that these are teaching assumptions, not universal sizing defaults.
Rewrite sample: Three workers can theoretically process 600 records each second only if the records divide evenly and each worker really sustains 200. Because a conventional group cannot split one partition between workers, fewer than three partitions cannot provide that measured parallelism. Three is therefore a lower bound, not a production recommendation: it leaves no catch-up capacity. Now put 500 records each second on one order_id. That key still goes to one partition, so adding idle workers elsewhere does not repair the overloaded owner. We must improve that handler or reconsider the ordering requirement before claiming that a larger partition count solves the problem.
Acceptance task: With 800 records/s, 200 records/s measured worker capacity and a 600-record/s hot key, explain why four evenly loaded workers are only a theoretical floor and why six partitions alone do not meet the actual requirement. Include replay and access constraints in the final decision.

# LQ-A05 — Follow a schema from writer through replay and recovery
Files: application_design/05_schema_registry_and_serialization.md
LESSON: FAIL
Reader: Programmer who has learned local validation and event compatibility; should understand and operate registry-backed serialization across deployment and restore.
Evidence: Development map across the full promise:

| Promise | Prior knowledge | Passage and worked reasoning | Status |
|---|---|---|---|
| Subject and registration | HTTP/JSON, local schemas | Lines 7–42 define subject/Avro and show config/register responses | developed registration, environment separately unverified |
| ID versus subject version and wire decoding | Local validation does not carry writer identity | Lines 48–55 state identifier and writer/reader resolution but show no record, ID lookup or decoded result | merely stated transition |
| Subject naming and registration policy | Subject defined | Lines 57–59 prescribe cross-language naming without showing topic→subject mapping or its consequence | merely stated |
| Backward transitive evolution | Compatibility definitions | Lines 65–98 mutate a schema and show request/results, but do not trace old bytes resolved with new reader/default or demonstrate why historical versions change the check | API procedure developed; application semantics merely stated |
| Restore with stable identity | ID distinction | Lines 107–114 describe changed-ID failure and required drill without concrete ID mapping or recovery procedure | explained risk; operational promise merely stated |
| Registry unavailability, cache and access | Above | Lines 116–118 prescribe bounded refresh and failure testing without a cached/uncached lookup example | merely stated |
| Deletion and avoid-registry boundary | Retention, schema dependency | Lines 124–130 explain broad risks and service cost, but deletion wording conflates soft and permanent deletion | boundary developed; local correctness separately owned |

Reasoning burden: Registering a schema is the one demonstrated workflow; serialization, historical resolution and restore require the reader to invent relationships between producer, registry, Kafka bytes and reader schema. The later production checklist repeatedly relies on that absent model. Fixing HTTP status wording does not develop those relationships.
Visual support: A numbered producer→registry→Kafka→consumer trace must distinguish subject version from wire ID and show a cache hit versus a lookup. Reuse its exact ID in the restore contrast so the reason ID preservation matters is visible.
Structure: REWRITE; keep one registry lifecycle lesson, with an explicitly bounded operational continuation if restore would interrupt the first round trip.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: LQ-A05 — Registration commands stand in for the promised serialized-contract lifecycle — develop writer ID, reader resolution and retained-record recovery as one evolving example before prescribing operational controls.
RELATED: coverage.audit.md owns the missing integration/restore-depth inventory; avoid a second same-root severity alongside LQ-A05. application_design.audit.md owns compatibility-gate and deletion wording errors; examples.audit.md owns unexecuted commands.
Proposed sequence: Show why the earlier local validator is insufficient across deployments → register and identify v1 → serialize/retain/read one record → deploy v2 reader and apply its default to v1 data → explain historical compatibility policy → lose/restore registry identity → add outage/deletion/access limits.
Content mapping: Keep schema/registration 7–42; develop 46–59 into the record-path explanation; preserve candidate requests 63–101 but interpret them through the reader example; develop 105–130 into the later recovery stage. Keep JSON semantic contract checks linked to 01 without claiming a type rejection tests unchanged-type meaning.
Example development: Subject orders.events.v1-value version 1 receives hypothetical ID 17. A retained order carries 17; a v2 reader supplies coupon_code=null for historical data. Compare a cached ID17 lookup with a fresh client during outage, then restore into a registry where an unrelated schema has 17 and show why merely re-registering v1 under another ID is insufficient.
Rewrite sample: The retained record identifies writer schema 17. That number is not “version 17 of orders”: the subject's version history and the identifier carried by the record serve different purposes. The consumer first uses 17 to identify the shape that encoded these bytes. Its new reader schema may then supply coupon_code=null because the old writer never wrote that field. Now rebuild the registry and register the same schema as ID 29. The Kafka record still refers to 17; changing the registry does not rewrite retained bytes. Recovery must preserve their identity relationship before replay can be considered restored.
Acceptance task: A retained v1 record has ID17; the restored registry contains v1 only as ID29, while a long-running consumer has 17 cached. Explain why one apparent successful read does not verify recovery, what a fresh consumer tests, and why subject-version labels cannot replace the wire ID.

# LQ-A00 — Application-design navigation
Files: application_design/README.md
LESSON: n/a
Reader: Course reader choosing the contract-first route, not a standalone mechanism lesson.
Evidence: Lines 9–15 map five files to outcomes; lines 19–29 name the first milestone and reliability continuation. The index does not claim to develop each mechanism itself.
Reasoning burden: Its role is navigation; actual prerequisite and stop-point sufficiency are assessed in reader_paths.audit.md.
Visual support: The existing contents table is sufficient for lookup.
Structure: KEEP; repair path dependencies in the path report without manufacturing a tutorial obligation for the index.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: LQ-A00 — Appropriate index role; no independent lesson-development severity.
RELATED: reader_paths.audit.md owns contract-first environment requirements and the safety of the stated stop point.

# LQ-R00 — Reliability index
Files: reliability/README.md
LESSON: n/a
Reader: Programmer choosing a reliability learning path.
Evidence: Contents maps guarantees, recovery, outbox, testing; Reading Order makes execution promises assessed in reader_paths.audit.md.
Reasoning burden: Navigation supplies destinations rather than a teaching mechanism.
Visual support: Contents table is sufficient for the index role.
Structure: KEEP; correct path promises under the canonical reader-path finding.
Summary: 0 critical, 0 high, 0 med, 0 low
RELATED: reader_paths.audit.md owns the premature implementation milestone.

# LQ-R01 — Derive delivery from a crash
Files: reliability/01_delivery_semantics.md
LESSON: FAIL
Reader: Python/HTTP programmer after fundamentals and Python consumption; must distinguish durable effect from durable checkpoint.
Evidence: Development map: checkpoint vs live position is available in fundamentals/04 §1; duplicate window is developed in fundamentals/04 §2 and reliability/01 lines 8–9; loss window at line 8 is incorrect, not merely terse; stable event identity lines 20–21 is stated and later-owned; crash checks lines 27–31 name desired observations; projection replacement lines 42–43 is a brief boundary, not a worked idempotency implementation. The central local defect prevents an otherwise appropriately narrow conceptual comparison from passing.
Reasoning burden: Reader must reinterpret `commit offset 8` as 9 and move the crash before the effect to make the displayed conclusion true.
Visual support: Keep the two short timelines but add initial/final committed-next-offset and durable-effect rows. This makes the changed order visible without a new diagram framework.
Structure: LOCAL-EDIT; repair the central trace and explain the two resulting states; a new file or merger is unnecessary.
Summary: 0 critical, 0 high, 0 med, 0 low
RELATED: reliability.audit.md R-C01 owns the incorrect central comparison; coverage.audit.md owns durable effect deduplication.

# LQ-R02 — Three boundaries behind a once-only claim
Files: reliability/02_idempotence_transactions_and_exactly_once.md
LESSON: FAIL
Reader: Programmer who knows Kafka offsets and the duplicate crash window; promised ability to bound producer, Kafka transaction, and consumer guarantees.
Evidence: Development map: matrix lines 7–11 states three scopes; producer sequence-number rejection lines 17–21 is stated without a lost-ack retry trace, so actor/remembered sequence/application resend distinction is not developed; Kafka input/output transaction lines 27–54 is developed with input 8, committed-next-offset 9, before/after crash contrast; external API boundary lines 28–30 is explained but the proposed durable local state transition is only named; transactional identity/fencing lines 66–67 is prescribed without following two instances; consumer idempotency appears in the matrix and never receives its owned atomic effect/checkpoint example. The strongest transaction trace therefore cannot justify PASS across the chapter's scope.
Reasoning burden: Reader must infer why a broker can suppress a network retry but not a second application send, and why a remembered event ID must be committed with its business change rather than independently. These are central differences, not optional production trivia.
Visual support: Follow evt-101 through producer/broker, Kafka processor, and business database lanes; explicitly mark which state each mechanism can change atomically. Retain the existing transaction table after explaining its lanes.
Structure: REWRITE; keep the chapter boundary but derive the matrix from a staged example instead of treating the matrix as the explanation.
Summary: 0 critical, 1 high, 0 med, 0 low
FIX-HIGH: LQ-R02 — One developed atomic Kafka trace is surrounded by undeveloped retry and business-effect prescriptions, so a novice cannot select a valid protection for the actual duplicate boundary. Rebuild the chapter around the three distinct repetitions and their owned state, with precise later implementation destinations.
RELATED: coverage.audit.md owns missing idempotency mechanisms and implementation depth; reliability.audit.md R-C02 owns open-transaction recovery; examples.audit.md owns runnable transaction absence. This finding owns the cross-boundary explanatory composition.
Proposed sequence: Start with an acknowledged-or-not append; distinguish automatic retry from an intentional resend; follow duplicate deliveries into one database effect; then change the output to another Kafka topic and derive why input offsets can join that output transaction; return to the matrix as a summary; develop fencing/recovery as a named continuation.
Content mapping: Keep §2's offset-9 trace and external API boundary. Develop §1's sequence identity using lost acknowledgments. Expand matrix consumer-idempotency row into a durable-effect bridge linked to its full implementation owner. Move the opening matrix after examples. Keep §3's warnings after a two-instance recovery trace, not as unexplained exceptions.
Example development: evt-101 first encounters a lost producer acknowledgment; the application then intentionally publishes evt-101 again; a billing consumer crashes after its effect; finally replace the database effect with billing.commands inside Kafka. Maintain separate application event identity, producer retry identity, and input checkpoint throughout.
Rewrite sample: The broker has appended evt-101, but its acknowledgment is lost. From the producer's point of view, no reply is compatible with both “not stored” and “stored, reply lost.” Its automatic retry therefore carries the sequence identity of the original attempt. The broker recognizes that identity and avoids another append. Now change one action: the application calls produce again with the same business event. That is a new send, not the original network retry. Producer idempotence does not compare the business meaning of payloads. Billing must still tolerate seeing evt-101 twice. If billing records the event ID and the invoice in one database transaction, a restart can find both, or neither; it cannot find a completed deduplication marker beside an invoice that was never committed. A separate card API is outside that database transaction, so this particular solution does not make charging atomic.
Acceptance task: Given one lost acknowledgment, one intentional resend, and a crash after a database commit but before Kafka offset commit, identify which mechanism handles each repetition and trace the durable state that survives. Then replace the database effect with an external API and explain which previously claimed atomic boundary no longer applies.

# LQ-R03 — Recover an event without losing its history
Files: reliability/03_retries_dead_letters_and_replay.md
LESSON: FAIL
Reader: Programmer after delivery/transaction foundations; must design bounded retry, preserve order when required, and replay with controlled effects.
Evidence: Development map: timeout vs invalid-currency classification lines 7–9 is explained; provenance envelope lines 16–27 is concrete; retry attempt/delay route lines 30–35 is stated with values but no actor enforcing eligibility or durable handoff; ordering loss lines 42–43 is explained for 8 versus 9 but both suggested remedies are undeveloped; replay gates lines 49–50 are listed without applying them to the envelope; lines 52–69 show transport to a staging topic, then assert a business-effect count without connecting a replay worker/idempotency store; permanent-failure boundary lines 77–82 is explained. The envelope is useful but does not supply the arrows' causal transitions.
Reasoning burden: The reader must invent the scheduler, source checkpoint boundary, ordering behavior during wait, and conversion from reviewed envelope to business action. A timestamp inside JSON does not itself postpone a Kafka read.
Visual support: Expand the existing path into one timeline with source group checkpoint, retry record/eligible time, retry worker action, DLT record, and business effect. Interpret each arrow as a persisted transition and mark the crash between publish and checkpoint.
Structure: REWRITE; retain one recovery chapter, developing retry first and controlled replay second; no file-per-term expansion.
Summary: 0 critical, 1 high, 0 med, 0 low
FIX-HIGH: LQ-R03 — The chapter jumps from a well-specified failure envelope to a route and recovery checklist without teaching how state crosses those steps. Rebuild the explanation around one failure lifecycle and changed-condition ordering comparison before introducing the replay command.
RELATED: coverage.audit.md owns retry scheduling/handoff and controlled replay mechanisms; examples.audit.md owns executable pipeline faults. This finding owns the disconnected progression between supplied artifacts and promised result.
Proposed sequence: Classify evt-101's failure; choose bounded inline retry as the first model; show why releasing the partition requires a separate persisted route; develop delay enforcement and handoff; contrast order-sensitive and independent work; exhaust attempts into DLT; correct and inspect one record; replay through the effect-owning handler and verify its outcome.
Content mapping: Keep opening classification and envelope, but annotate when each field changes. Develop the named retry hops as transitions rather than labels. Move §1's availability/order choice directly after the first retry transition. Keep replay bounds, provenance, and not-to-retry rules in the developed second stage. Keep the shell transport as staging transport only unless an actual handler is composed.
Example development: evt-101 is order creation at source offset 8; evt-102 cancels the same order at 9. First fail 101 transiently, then advance a retry clock, then allow 102 to proceed and inspect the business result. Compare holding the source partition with releasing it; finally make 101 a permanent validation failure and walk its reviewed replay.
Rewrite sample: At 09:00:00 the worker fails to handle evt-101 and sets next_attempt_at to 09:00:05. That field is evidence of the policy, not a timer Kafka will run. A retry worker needs an explicit rule that withholds the attempt until that instant. Before releasing the source record, the recovery design must also make its retry copy durable; otherwise a crash can leave neither a pending source record nor a recoverable retry. Now suppose offset 9 cancels the order created by offset 8. Moving creation to a retry route lets cancellation run first. We have gained availability for later work by giving up this entity's original processing order. If creation-before-cancellation is required, this route is not an adequate design merely because it preserves both records: the chosen recovery mechanism must also preserve or explicitly enforce that dependency.
Acceptance task: A retry copy exists, the source checkpoint has not advanced, and the worker crashes. Predict what can be delivered after restart and which identity must prevent a duplicate effect. Then let offset 9 concern the same order versus an unrelated order; explain how that changes the acceptable ordering policy. Finally distinguish “one envelope copied to staging” from “one verified business effect.”

# LQ-R04 — Outbox durability and the choice of relay
Files: reliability/04_transactional_outbox_and_cdc.md
LESSON: FAIL
Reader: Programmer with a short database-transaction bridge and Kafka checkpoints; must eliminate the dual-write gap and choose an appropriate publication mechanism.
Evidence: Development map: dual-write failure lines 7–8 is explained; shared transaction lines 14–18 and 24–70 is developed with SQL/Python and both-or-neither reasoning; polling vs CDC introduction lines 20–21 defines names; choice lines 74–78 merely states ownership/query-load versus connector/log/schema costs; polling recovery lines 80–101 is developed through ack/crash/reclaim and durable intent; reconciliation retention lines 94–96 states purpose but no comparison method; smaller Kafka-only boundary lines 110–111 follows the prior transaction lesson. The causal polling model is strong; CDC is not a genuinely taught alternative or explicitly bounded deferral.
Reasoning burden: Reader can explain why an unpublished row is retried but cannot map that recovery position to CDC, or justify the stated “CDC scales integration” choice for a concrete service. The broad comparison demands knowledge not earned by the preceding SQL.
Visual support: Retain the polling crash timeline. Add a small side-by-side state table: polling publication marker versus connector log position, who advances it, and what survives failure. Interpret the table before recommending a relay.
Structure: REWRITE; focused development of the comparison inside the existing chapter; preserve the developed transaction and polling trace.
Summary: 0 critical, 0 high, 1 med, 0 low
FIX-MED: LQ-R04 — The lesson's developed polling example is followed by an unearned architectural comparison, leaving a novice to select CDC from labels rather than consequences. Develop that choice with one changed operational condition and an explicit CDC continuation.
RELATED: coverage.audit.md owns missing CDC/relay operational depth; reliability.audit.md R-C04 owns incorrect event routing; examples.audit.md owns incomplete execution composition.
Proposed sequence: Keep dual-write failure → atomic intent → polling ack/crash trace; only then ask what changes if an existing managed CDC service reads the database log; compare checkpoint ownership and recovery burden; retain both publication-order and cleanup constraints in their relevant stages.
Content mapping: Keep §1 almost intact. Move §2's polling trace before its comparison paragraph. Develop its CDC alternative enough to support choosing, with a named implementation destination rather than silently implying connector configuration has been taught. Preserve SQL, bounded claim ownership, cleanup, and Kafka-only exception.
Example development: Follow the same committed order/outbox row through application-owned polling, then change only who discovers committed inserts: a CDC connector with its own log position. Compare the team and recovery obligations without claiming either can dispense with duplicate-safe consumers.
Rewrite sample: After the order transaction commits, our polling relay asks which outbox rows still have published_at=NULL. That row is its evidence that publication may remain unfinished. Suppose the organization already operates a CDC connector for this database. A different worker can discover the same committed insert from the database change log instead of repeatedly querying unpublished rows. We have changed who tracks progress, not removed the handoff to Kafka. The CDC connector's saved log position now matters to recovery, and the database must retain the changes it still needs. The choice is therefore not simply “CDC is faster”: it transfers work from application polling and row cleanup to connector operation and log-retention recovery. Before choosing it, we need the next lesson's concrete connector checkpoint and restart procedure.
Acceptance task: Compare an application team with no connector operations and an existing managed CDC installation. Explain which state each proposed relay uses to resume, which dependency can prevent recovery, and why an acknowledgment-boundary duplicate still requires safe consumption.

# LQ-R05 — Design a test that can falsify a guarantee
Files: reliability/05_testing_kafka_services.md
LESSON: PASS
Reader: Programmer who has seen delivery, transactions, and retry/outbox traces; must choose a test environment and deterministic failure point.
Evidence: Development map: real-broker-vs-mock distinction lines 7–9 is explained; guarantee/environment table lines 27–36 ties required observation to missing mock evidence; crash trace lines 43–60 is developed from produce to process kill to deduplicated restart and durable assertions; explicit synchronization lines 62–65 explains why arbitrary sleep is invalid; process-vs-exception distinction lines 67–69 explains lost process state; fixture composition and suites lines 76–96 explain isolated scope and routine versus costly exercises; shared-group failure and single-node limits lines 101–107 are explained. Executable opening lines 11–19 is a separate broken artifact claim, not proof the test-design reasoning is empty.
Reasoning burden: No material causal gap in conceptual test selection: the guarantee identifies the relevant durable state, the fault hook isolates its boundary, and the post-restart assertion distinguishes outcomes. Readers cannot run the absent harness; that material limitation remains canonical elsewhere.
Visual support: Existing ordered crash trace and guarantee/environment table are sufficient for the conceptual reasoning; adding decorative topology would not repair the missing executable artifact.
Structure: KEEP; preserve the explanation while supplying the executable harness under its canonical findings.
Summary: 0 critical, 0 high, 0 med, 0 low
NO-ACTION: The whole lesson develops test-design reasoning with an interpreted crash trace and changed test environments; no separate structural pedagogy defect found.
RELATED: examples.audit.md owns the absent smoke test/crash harness; coverage.audit.md owns operationalized test depth. PASS is limited to LESSON, not runnable completeness.

# LQ-O01 — Security policy as an observed lifecycle
Files: operations/01_security_and_multitenancy.md
LESSON: FAIL
Reader: Programmer after the application and reliability paths, learning to apply and verify Kafka client security; generic distributed-security expertise is not assumed.
Evidence: Development map: TLS/SASL/ACL separation at 7–9 is defined; client identity, SCRAM and CA at 15–37 have explained artifacts; ACL principal/action/resource at 39–63 has a useful decision carrier but an overstated group-binding claim; rotation at 17 is prescribed without its credential states; trust boundaries at 65–66 are stated; positive/negative success at 68–70 is expected rather than assembled; hard isolation at 81–82 is a recommendation without a contrasting tenant scenario.
Reasoning burden: The reader can inspect the intended ACL mapping, but must invent how the client, broker, admin inputs and observations form one verified policy, then how that policy survives credential replacement. The isolation boundary also needs one explained threat/constraint rather than another list of security nouns.
Visual support: Use a principal→request→resource→decision table, with topic fetch and group join as separate rows. A before/during/after credential table can show which identity is valid and authorized without displaying secret values.
Structure: REWRITE; preserve the safe client and ACL artifacts, develop their operational sequence and mark later isolation/rotation responsibilities explicitly.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: coverage.audit.md, Security and multitenancy, owns this incomplete operational teaching; operations.audit.md O-ACL owns the distinct false conditional-permission claim. No duplicate lesson severity.
Proposed sequence: A named unauthorized action and its consequence → server/identity assumptions → verified client connection → resource grants → allowed and denied requests with observed outcomes → rotate one identity while preserving least privilege → decide whether shared resources meet the tenant's isolation requirement.
Content mapping: Keep 19–57 and interpret them through one walkthrough; develop 15–17 into a later rotation stage; attach 59–70 to actual policy observations; retain 77–82 as a worked isolation comparison. Detailed platform provisioning may be a named prerequisite, but its required inputs must be bounded here.
Example development: orders-api writes orders while a stolen orders-api credential attempts payments; billing-worker reads orders but cannot join fraud-v1. Introduce orders-api-next with equivalent narrow grants, verify its canary, move the service, revoke old identity and prove old requests fail. Then compare a tenant requiring independent keys or failure domains with one needing only per-resource authorization.
Rewrite sample: A successful TLS connection tells orders-api that its encrypted connection reached a trusted broker. It does not answer whether orders-api should write payment events. Test the next decision separately: publish to orders.events.v1 using the service identity, then attempt payments.events.v1 using that same identity. The second request must fail authorization. For billing, topic reads and group operations are two different checks: permission to fetch orders does not itself grant permission to join fraud-v1. Keeping those observations separate tells us which boundary failed when a negative test unexpectedly succeeds.
Acceptance task: Given a working encrypted connection and successful order publish but an unexpectedly successful payment publish, identify the failed boundary and the next evidence to inspect. During rotation, explain why revoking the old identity before a successful new-identity canary creates an avoidable outage.

# LQ-O02 — A measured capacity envelope
Files: operations/02_capacity_planning_and_performance.md
LESSON: PASS
Reader: Programmer who knows partitions, groups and replication, choosing an initial load-test envelope rather than a universal capacity formula.
Evidence: Development map: bytes×retention×replicas at 7–9 supplies a concrete storage baseline; measured per-partition limits at 13–26 produce competing steady-state and recovery partition counts; live ingress plus backlog draining is explained rather than hidden in the formula; network, headroom and disk-utilization calculations at 28–32 continue the same workload; broker-loss and skew invalidations at 34–37 explain when the estimate stops applying; tuning at 43–45 is a short optional overview, not an unsupported command to pick particular settings; success and hot-key limits at 50–66 close the decision loop.
Reasoning burden: The reader can follow why five partitions satisfy steady state but not the recovery deadline, and which measurements could invalidate fifteen. This is a genuine developed decision lesson despite being short.
Visual support: The measured-input table and successive arithmetic sufficiently expose the bottleneck change; a broker diagram would not improve the central reasoning.
Structure: KEEP; preserve the continuous envelope and explicit load-test assumptions.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The note teaches the promised estimate and its limits. It does not claim that the arithmetic replaces a failure/load test.

# LQ-O03 — From an alert to an explained incident decision
Files: operations/03_observability_and_incident_response.md
LESSON: FAIL
Reader: Engineer with Kafka fundamentals, building alerts and choosing a justified first response rather than merely copying metric names.
Evidence: Development map: possible lag causes at 7–9 and triage tree at 15–21 are enumerated; alert YAML at 32–62 is a concrete carrier; conjunctive lag/age decision and missing-series suppression are explained at 64–68; replica/disk delay is explained at 70–73; injected-handler success at 75–77 is an unperformed procedure without setup; coordinator/controller detection appears only at 9/20; 86–89 gives sensible aggregation/paging boundaries. There is no complete incident with observed values and a changed condition selecting another response.
Reasoning burden: A novice can restate that lag has many causes but must invent the diagnostic episode that distinguishes a handler bottleneck, skew, rebalance churn and control-plane failure. The collection promises implemented detection as well as broad awareness.
Visual support: Add a timed observation table: partition, arrival/processing rates, age, lag, membership, ISR and hypothesis. Change one condition and interpret why the next action changes. The existing triage tree is a route through questions, not evidence answering them.
Structure: REWRITE; organize around one bounded incident and its contrasting diagnosis, keeping the existing alert artifacts as tools in that story.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: coverage.audit.md, Observability and incident response, owns insufficient diagnosis/verification depth and missing control-plane branches. The editorial plan below develops that same defect without another severity.
Proposed sequence: Define the event freshness objective → observe one breached partition → compare arrival and handler rates → evaluate the sample alert → inject and verify a bounded failure → recover and observe clearance → contrast a missing metric and a coordinator/controller incident.
Content mapping: Keep 27–73 but place the YAML after the first observed case; turn 7–21 from a checklist into a developed sequence; implement the stated absent-series branch; retain 84–89 as derived boundaries; add the promised coordinator/controller branch here rather than assuming the replication chapter supplies a runbook.
Example development: billing P2 receives 100 records/s but completes 60 while other partitions are healthy. Keep arrivals constant and show growing backlog/age. Then make processing recover while repeated membership changes interrupt work; explain why adding workers alone is no longer the first hypothesis. Finally remove the age series and show that a joined alert stops producing a result instead of becoming healthy.
Rewrite sample: P2 receives 100 records each second and billing finishes only 60. Its backlog therefore grows by about 40 records per second while the oldest unfinished event becomes older. The alert identifies a consequence, not yet its cause. Compare handler latency and dependency errors before adding consumers: if one database call now takes five times longer, another worker may only add more pressure to the same dependency. If handler time is unchanged but assignments repeatedly move, investigate membership and polling instead. The same rising lag can lead to different actions because the intermediate observations differ.
Acceptance task: Present two partitions with equal lag but different age, arrival rate and membership history; require a justified first investigation and an observation that would falsify it. Then remove the age series and explain why separate missing-data detection is necessary.

# LQ-O04 — Upgrade state and regional recovery are different transitions
Files: operations/04_deployment_upgrades_and_disaster_recovery.md
LESSON: FAIL
Reader: Engineer planning the cluster lifecycle; no prior knowledge of Kafka binary/feature-version transitions is assumed.
Evidence: Development map: RTO/RPO are named at 7–9 and later demonstrated at 30–46; provider/customer ownership at 15–16 is a usable bounded division; upgrade paths/features at 18–20 are only a checklist; asynchronous regional copies, saved progress and repeated effects at 26–46 form a developed trace; failback at 48–51 states a bounded coordination sequence; restored ancillary state at 65–67 is explained as a failure risk. The good recovery trace cannot supply the absent upgrade model advertised in the section README.
Reasoning burden: The learner must infer the distinct binary version, finalized feature state, mixed-version interval and rollback boundary. Adding “check release notes” cannot teach those relationships; an upgrade is not the same state transition as regional failover.
Visual support: Retain the regional timeline; add a separate before/during/after upgrade state table showing node binaries, finalized feature levels, health gates and which rollback remains permitted. Keep regional source/destination record coordinates explicitly labeled rather than implying that every mirroring tool preserves numeric offsets.
Structure: REWRITE; retain the regional lesson and develop a clearly separate upgrade sequence within the same lifecycle chapter or an explicitly named dedicated continuation.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: coverage.audit.md, Upgrades and regional disaster recovery, owns the missing upgrade capability; no second severity for the same missing teaching.
Proposed sequence: Who owns each lifecycle action → common distinction between stored data and control state → supported version-specific upgrade stages and abort gates → independent regional loss/replay scenario → controlled failback and verified recovery objectives.
Content mapping: Keep 24–59 as the strong regional unit; expand 18–20 into a real staged upgrade unit instead of padding each checklist noun; retain 63–69 as the consequence of missing recovery inputs. A split is optional only if the upgrade procedure becomes a separately usable operational responsibility.
Example development: In a pinned supported version transition, record binaries and feature state before restart, after one node, after all nodes and before finalization. Introduce a health regression during the mixed-version stage and explain the stop/rollback decision. Only after that compare the existing eu-primary/eu-replica regional story; do not reuse RPO as an upgrade validation metric.
Rewrite sample: Restarting a broker with a new binary and enabling the cluster's new features are different steps. During the rolling restart, some nodes may run the old binary while others run the new one, so the supported transition must keep them interoperable. Record the finalized feature state before beginning. After replacing one node, check the defined replication and client-health gates before replacing the next. If those gates fail, stop the rollout; do not advance feature levels in the hope that this repairs the symptoms. Finalization changes the state the cluster has agreed to use and can close downgrade options, so its exact version-specific boundary must be explicit in the runbook.
Acceptance task: Given all nodes on the new binary but old finalized feature levels and a newly failing client, explain why automatic finalization is not the next troubleshooting step. Identify the evidence and release-specific restrictions needed before rollback, then distinguish this case from missing regional records after failover.

# LQ-O05 — Reversible configuration versus state-moving operations
Files: operations/05_configuration_and_topic_administration.md
LESSON: FAIL
Reader: Operator who can authenticate an admin client and must change application-owned resources with defensible verification and rollback evidence.
Evidence: Development map: creation at 7–26 has commands and expected policy; precedence at 32–49 is developed through 7-day override versus 30-day inheritance; retention change at 55–67 supplies explicit forward and rollback values; update-mode distinction at 69–72 is a bounded source check; expansion, reassignment, quotas and deletion at 78–83 are one-line behaviors with distinct consequences; drift/canary evidence at 85–90 is prescribed; reassignment throttling at 96–97 adds another action without a plan artifact; incompatible-topic migration at 102–104 names dual publication/backfill and cutover without their state transitions. The final scope is substantially wider than a retention lookup.
Reasoning burden: The well-developed override example can misleadingly make the later operations look like similar scalar changes. The reader has to invent which operations move data, preserve old placement, create a second history, or destroy recovery inputs—and how success/rollback evidence differs.
Visual support: Keep the override before/after trace. Add an operation-state table distinguishing scalar effective values, replica placement, keyed routing and deleted namespaces. For reassignment, show old/new replica sets and copy progress; for migration, show old/new topic writers/readers and the cutover checkpoint.
Structure: REWRITE; preserve the retention lesson as the entry case, then deliberately contrast state-moving/destructive operations with their own compact worked procedures or real named owners.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: coverage.audit.md, Topic and configuration administration, owns incomplete administration procedures. This lesson plan is the editorial repair for that same finding, not a duplicate severity.
Proposed sequence: Observe current effective state → change and restore a scalar setting → contrast an irreversible placement change → trace reassignment to completion → test a bounded quota → explain deletion/recovery preconditions → choose a new-topic migration when compatibility requires it.
Content mapping: Keep 5–72; turn 76–104 into contrasted operations rather than four bullets and two warnings. Maintain the existing canonical administration owner; add subprocedures here or explicitly identify developed destinations. Preserve warnings about internal topics and irreversible actions beside the relevant procedure.
Example development: Retain seven→fourteen→seven days as the reversible case. Change partition count and show that removing an override cannot return old keyed placement. Move one replica from broker 2 to broker 4 and show the catch-up state before completion. Apply a quota to one canary identity and observe its throttle before broad rollout. For deletion, identify the separate restore source before acting.
Rewrite sample: Restoring `retention.ms=604800000` puts the old seven-day policy back because we recorded that explicit value. Adding partitions is a different kind of change. The topic now has more ordered logs, and producers may place future keys differently; there is no symmetric “remove those partitions” rollback. The review therefore needs more than an old scalar value. It needs the affected key-placement assumption, the consumer compatibility check and a migration plan if the old ordering domain must be preserved. A successful admin response proves the command was accepted, not that the application's ordering contract survived.
Acceptance task: Given a successful retention increase and a successful partition expansion, identify why their rollback evidence differs. For an in-progress replica reassignment, distinguish command acceptance from completion and explain why a throttle below incoming traffic can prevent catch-up.

# LQ-O00 — Operations navigation
Files: operations/README.md
LESSON: n/a
Reader: Engineer selecting the operations route and ownership boundary.
Evidence: Lines 9–20 map outcomes and the managed-provider stop/continuation point; they do not themselves teach procedures.
Reasoning burden: Navigation is direct; linked chapters must earn the listed outcomes.
Visual support: The role/outcome table is sufficient for this index.
Structure: KEEP; retain the learning promise while repairing its owners.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: No index-only defect requires a new finding.

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
