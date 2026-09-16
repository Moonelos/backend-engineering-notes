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
