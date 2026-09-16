# Reliability package review — 2026-09-16

Scope: `infrastructure/kafka/reliability/README.md` and teaching notes `01`–`05` only. Prerequisites read in full: `infrastructure/kafka/README.md`, `fundamentals/README.md`, and all five fundamentals notes. Linked application owners inspected where this package depends on them: `application_design/01_event_contracts_and_schema_evolution.md`, `02_python_producers_and_consumers.md`, and `05_schema_registry_and_serialization.md`. Findings below concern only the assigned reliability files; cross-package issues are handoffs, not findings against prerequisite files.

Audience used: backend engineers who know processes, network failure, and database transactions but may not have operated Kafka (`kafka/README.md:49-52,101-104`). The reliability path promises that they can derive real delivery behavior from crash traces, choose an idempotency boundary, implement a Kafka transaction or outbox transaction, and prove the boundary with process-kill tests (`kafka/README.md:69-83`; `reliability/README.md:19-31`).

Research status: COMPLETE for the mechanisms needed to check this batch; sources and limitations appear at the end.

## Per-note review

# reliability/README.md (31 lines)

Role: index and learning-path contract.

ORDERING: n/a for index prose; lookup orientation PASS at lines 7-15. Path sequencing is FAIL: entry 2 says to execute “the Kafka transaction boundary or the outbox transaction” (lines 23-25), but entry 2 points only to note 02, which contains a conceptual transaction trace rather than a runnable implementation, while the outbox is note 04 after the test entry. The claimed implementation milestone (“produces one committed output,” lines 28-29) therefore has no artifact in the listed entry.

EXPLANATION: n/a for the index; teach-back n/a. The outcome and stop condition are explicit at lines 21 and 28-31.

Summary: 0 critical, 0 high, 0 med, 0 low (local owner).

RELATED: reader-path owner — lines 23-29 promise execution by entry 2 and a harness by entry 3, but neither runnable artifact exists in those entries.

RELATED: examples owner — lines 24-25 and 28-29 are executable/test promises contradicted by notes 02 and 05; see executable claims E1, E3, and E6.

Candidate correction: either add a complete runnable transaction path to note 02 and the referenced harness to note 05, or rename the milestone as a worked trace and route an outbox implementation through note 04 before claiming execution.

# reliability/01_delivery_semantics.md (46 lines)

Role: foundation.

ORDERING: PASS; payoff 5/46 (10.9%). The note begins with the crash comparison (lines 5-10), explains the checkpoint/effect ordering (lines 14-21), then adds verification, failure, and boundary sections (lines 25-42).

EXPLANATION: FAIL; teach-back FAIL (missing: an accurate at-most-once transition/result and a demonstrated idempotency state transition). The note supplies the problem and decision at lines 14-18, a consumer/checkpoint actor implicitly at lines 16-18 and 25-30, a misconception boundary at lines 32-33, and a first batch failure at line 39. However, the at-most-once trace says `commit offset 8 → process 8 → crash = possible loss` (line 8). A crash *after* process 8 is not the loss window; the loss occurs after committing past 8 and before its effect completes. The stable-key advice at lines 20-21 never shows the store/constraint that converts the duplicate attempt into one effect.

Summary: 0 critical, 1 high, 0 med, 0 low.

FIX-HIGH: The central at-most-once trace places the crash after `process 8`, so it does not exhibit the claimed loss (`01_delivery_semantics.md:7-10`). This prevents a learner from deriving the guarantee from the event order and conflicts with the authoritative consumer sequence (save position, crash before processing output). Move the crash between checkpoint and effect, and name whether “process” means attempt or durable effect; contrast it with the at-least-once crash after the durable effect but before checkpoint.

RELATED: coverage owner — idempotency-key selection is only defined at lines 20-21. The package promises selection of a deduplication boundary, but no canonical note demonstrates a unique-key claim, existing-result lookup, and offset commit across a duplicate crash trace.

Candidate mechanism coverage:

- Consumer at-most-once/at-least-once: required `demonstrated`; achieved `explained` because one central trace is causally wrong.
- Consumer-effect idempotency: required `demonstrated` by the package milestone; achieved `defined` (stable `event_id` advice only).
- Crash-window testing: required `operationalized` in the production path; achieved `explained` here and depends on the missing note-05 harness.

Cross-topic/path dependency: the preceding consumer-group note correctly shows `effect → crash → no commit → duplicate` (`fundamentals/04_consumer_groups_offsets_and_rebalancing.md:30-41`), so the at-least-once half has a sound prerequisite. Nothing earlier supplies the missing deduplication store transition.

# reliability/02_idempotence_transactions_and_exactly_once.md (73 lines)

Role: deep dive.

ORDERING: PASS for a deep dive; payoff 5/73 (6.8%). The scope matrix at lines 5-11 immediately bounds the three meanings of “once,” and the transactional failure that motivates the deeper mechanism appears at lines 25-30. It does not, however, satisfy the separate path-level promise to “execute” a transaction.

EXPLANATION: FAIL; teach-back FAIL for the note as a three-mechanism lesson (missing: producer-idempotence transition/contrast and first failure; consumer-idempotency owned state, transition/result, and failure). Kafka transactions themselves pass teach-back: problem/boundary at lines 25-30, producer decision and API transition at lines 32-52, visible result at lines 41-56, misconception boundary at lines 58-59, and fencing failure at lines 63-69. Producer idempotence receives only configuration prose (lines 15-21), and consumer idempotency is only a matrix row (line 11).

Summary: 0 critical, 0 high, 1 med, 0 low.

FIX-MED: The crash explanation says the broker “aborts or times out” the open transaction and that a `read_committed` consumer “sees no charge” (`02_idempotence_transactions_and_exactly_once.md:41-45`), but omits the observable interval before resolution: an open transaction holds a read-committed consumer at the last stable offset, potentially withholding later records. It also omits the recovery actor: `initTransactions()`/equivalent on a restarted producer with the same unique `transactional.id` resolves a prior instance’s in-flight transaction; otherwise the coordinator aborts it only on timeout. Add this intermediate state and its lag/timeout symptom so the operational prediction follows from the trace.

RELATED: coverage owner — the title and opening promise three scopes, but producer idempotence is `explained` at best and consumer idempotency is `defined`; only the Kafka transaction is `demonstrated`.

RELATED: examples owner — lines 32-39 are a `text`-fenced API trace, not executable code. Lines 54-56 prescribe a kill/restart observation without a processor, configuration, topic setup, consumer command, or fault hook. The reliability README nevertheless claims that this entry executes the boundary; see E3.

Candidate mechanism coverage:

- Producer idempotence: required `demonstrated`; achieved `explained`. The note states compatible settings and scope but lacks a retry sequence/contrast and the session/application-resend boundary documented by Kafka.
- Consume-transform-produce Kafka transaction/EOS: required `operationalized` by the path’s build claim; achieved `demonstrated`. The trace covers atomic output+offset and a crash contrast, but no complete client configuration (`transactional.id`, `enable.auto.commit=false`, `isolation.level=read_committed`), `initTransactions`, abort/exception path, position reset after abort, or executable verification exists.
- Consumer/business-effect idempotency: required `demonstrated`; achieved `defined` in the opening matrix.
- External side-effect boundary: required `explained`; achieved `explained` at lines 27-30 and 58-59.

Cross-topic/path dependencies:

- `fundamentals/05_replication_leaders_and_kraft.md:30-37` supplies `acks=all` and ISR durability, but transaction-topic durability and transaction-coordinator availability remain implicit.
- `application_design/02_python_producers_and_consumers.md:85-89` points here as the idempotency owner, so this note cannot delegate the missing consumer dedupe implementation back to application design.
- The official Kafka API requires auto commit off and no separate manual commits when offsets are sent transactionally; that constraint is absent here even though the earlier Python baseline manually commits.

# reliability/03_retries_dead_letters_and_replay.md (86 lines)

Role: implementation.

ORDERING: FAIL; payoff none/86. The opening gives a useful policy and envelope (lines 5-36), but an implementation role requires a minimal runnable recovery path. The only command appears at lines 54-60 and is not runnable in the documented Docker environment. No retry consumer/scheduler, source-offset handoff, DLT producer, or assembled success result is supplied before production trade-offs.

EXPLANATION: FAIL; teach-back FAIL (missing: the actor/state transition that enforces `next_attempt_at`; the atomic or idempotent handoff from the source record to retry/DLT; a successful executable replay transition). The note supplies failure classes and provenance (lines 5-36), an ordering consequence (lines 40-43), replay checks and bounds (lines 47-71), a misconception boundary (line 73), and a first failure (lines 77-82). Expert knowledge is still required to explain why a record in `retry.5s` waits five seconds or what happens if the consumer crashes between producing the recovery record and committing the original offset.

Summary: 0 critical, 0 high, 0 med, 0 low (local owner).

RELATED: coverage owner — the package’s central retry implementation is underdeveloped. Kafka topics do not implement delayed delivery merely from a name or `next_attempt_at`; lines 30-36 state delays without a delaying actor. The original-record → retry/DLT handoff also lacks a transaction/idempotency design, so crashes can duplicate the recovery record or lose it if the source offset is committed too early.

RELATED: examples owner — the replay command at lines 54-60 fails exactly as shown in the declared environment because both Kafka CLI programs exist only inside the Docker container used by the prerequisite. See E4.

Candidate mechanism coverage:

- Failure classification and retry policy: required `demonstrated`; achieved `demonstrated` by the bounded envelope and changed failure classes at lines 5-36.
- Retry delay/scheduling: required `operationalized` for an implementation note; achieved `mentioned` (`next_attempt_at` and topic labels only).
- Source-to-retry/DLT handoff correctness: required `operationalized`; achieved `absent`.
- DLT provenance: required `demonstrated`; achieved `demonstrated` by lines 7-36.
- Bounded replay: required `operationalized`; achieved `explained`; its only command is broken in the documented environment and no preflight/rollback or rate-limited executor is provided.
- Per-entity ordering during retry: required `explained`; achieved `explained` at lines 40-43, but no implementation choice is demonstrated.

Cross-topic/path dependencies: this note depends on transaction/idempotency behavior from note 02 to make the source-to-recovery handoff safe, but never applies it. It also depends on the stable-key ordering invariant in `fundamentals/03_partitioning_keys_and_ordering.md:34-42`; moving one event aside is correctly identified as weakening order.

# reliability/04_transactional_outbox_and_cdc.md (114 lines)

Role: implementation.

ORDERING: FAIL; payoff none/114 for the declared implementation role. A strong conceptual payoff appears at 5/114 (4.4%) and the local database transaction is shown at lines 12-70, but the note never supplies a runnable PostgreSQL setup/call or an assembled polling/CDC publication path. The relay—the half that reaches Kafka—remains prose and a state trace at lines 74-98.

EXPLANATION: FAIL as an “outbox and CDC” lesson; teach-back PASS for the outbox handoff but FAIL for CDC (missing: CDC-owned position/state, connector actor/configuration, publication transition/result, misconception boundary, and first CDC failure). The outbox problem is lines 5-9; durable state and application actor are lines 12-70; relay transition and duplicate contrast are lines 74-98; the atomicity misconception is explicitly corrected at lines 100-101; and deletion loss is line 107.

Summary: 0 critical, 1 high, 0 med, 0 low.

FIX-HIGH: The polling relay is told to publish with `event_id` as the Kafka key (`04_transactional_outbox_and_cdc.md:80-82`). A unique key per event does not colocate successive events for the same aggregate and can reorder `order.created`, `order.paid`, and `order.cancelled` across partitions, directly contradicting the prerequisite rule to key by the stable entity whose relative order matters (`fundamentals/03_partitioning_keys_and_ordering.md:34-42`). Publish with `aggregate_id`/`order_id` as the Kafka record key and retain `event_id` separately for deduplication; demonstrate two events for one aggregate landing in one partition.

RELATED: coverage owner — polling and CDC are presented as alternatives at lines 74-78 but share one schema and are never separated into concrete mechanisms. A polling relay needs the claim transaction boundaries, concurrent-worker behavior, broker-ack handling, and mark-published/reconciliation query. A CDC path needs an insert-only outbox contract, connector/event-router configuration, database-log position/recovery behavior, and operational response to connector/log-retention failure. The current `published_at` update flow is a polling design, while Debezium’s outbox event router expects insert operations and treats updates as invalid behavior.

RELATED: examples owner — the DDL (lines 25-42) and Python function (lines 46-66) are useful artifacts but are not a runnable path: no PostgreSQL service/DSN, driver dependency, connection construction, invocation, verification query, or cleanup is provided. See E5.

Candidate mechanism coverage:

- Database/outbox atomic write: required `operationalized`; achieved `demonstrated`. The schema and parameterized one-transaction function carry the mechanism, but the success query is not shown/run and no failure execution exists.
- Polling relay: required `operationalized`; achieved `explained`, with a correctness error in record key selection and unclear lock/transaction scope around `FOR UPDATE SKIP LOCKED`.
- CDC outbox relay: required `operationalized` by the title/role; achieved `defined` at lines 20-21 and 74-78.
- Duplicate downstream collapse: required `demonstrated`; achieved `explained`; a “unique `event_id` constraint” is named (lines 92-94) but no table/write/duplicate-result carrier appears anywhere in the reliability package.
- Reconciliation/retention: required `operationalized`; achieved `explained` at lines 92-98 without a reconciliation query, alert, or recovery procedure.

Cross-topic/path dependencies:

- The keying defect violates the explicit prerequisite contract in fundamentals note 03.
- The schema-evolution owner provides event identity and contract validation, but does not supply the outbox relay or consumer dedupe implementation.
- Debezium’s maintained outbox documentation uses aggregate ID as the event key specifically to maintain partition ordering and describes insert-only outbox changes; the note should distinguish that CDC model from its mutable polling schema.

# reliability/05_testing_kafka_services.md (111 lines)

Role: implementation.

ORDERING: FAIL; payoff none/111. The intended payoff is line 5, but the two-command quick start at lines 12-15 has no corresponding `tests/integration/test_kafka_smoke.py` in the repository and no project manifest. The note then describes what the missing test “should” do (lines 17-20) rather than composing it. The first executable result never arrives.

EXPLANATION: PASS; teach-back PASS for the testing principle. The problem with mocks is explained at lines 7-10 and 27-39; the test-environment decision is mapped by claim at lines 27-39; the harness/test process acts on broker, worker, and durable store state in the trace at lines 43-66; the exception-vs-process-death misconception is ruled out at lines 62-63; shared identifiers and one-node scope supply first failures at lines 97-107. This conceptual quality does not repair the missing implementation.

Summary: 0 critical, 0 high, 0 med, 0 low (local owner).

RELATED: examples owner — the central smoke command is BROKEN, and the crash/replay procedures are not implemented. See E6-E8.

RELATED: coverage owner — real-broker smoke testing is `explained`, not `operationalized`; deterministic process-kill crash testing is `demonstrated` as a conceptual trace but not operationalized; transaction, replay, compatibility, capacity, and game-day coverage are a useful test matrix rather than working tests.

Candidate mechanism coverage:

- Real-broker smoke harness: required `operationalized`; achieved `explained` because the named file/fixtures are absent.
- Deterministic crash hook and child-process kill: required `operationalized`; achieved `demonstrated` by lines 43-66 but not executable.
- Transaction visibility test: required `operationalized` by notes 02 and 05; achieved `defined` in the matrix at line 34.
- Replay-bound/idempotency test: required `operationalized`; achieved `defined` in the matrix and suite list (lines 35,81).
- Test isolation/cleanup: required `operationalized`; achieved `explained` at lines 17-23, 70-93, and 97-107.

Cross-topic/path dependencies:

- Line 9 depends on the fundamentals Docker broker and line 19 depends on the deadline/diagnostics in `application_design/02_python_producers_and_consumers.md:48-65`, but neither linked note provides the missing pytest fixture or smoke-test file.
- The repository root has no `pyproject.toml`/`uv.lock`, so `uv add` has no declared project target. Even after adding one, the named test artifact is absent.
- Lines 92-93 link the Java Testcontainers module in a Python course. The conceptual recommendation is current, but a runnable Python harness needs a Python-specific dependency/API owner or an explicitly language-neutral container setup.

## Candidate mechanism coverage summary

These are inputs for the collection-wide coverage owner, not duplicate canonical findings.

| Mechanism | Promise/evidence | Required | Achieved | Teach-back | Candidate disposition |
|---|---|---:|---:|---|---|
| Consumer delivery semantics | README outcome; note 01 | demonstrated | explained | FAIL | COVERAGE-HIGH: repair at-most-once trace |
| Durable consumer-effect idempotency | README entry-2 boundary; notes 01/02 | demonstrated | defined | FAIL | COVERAGE-HIGH: add store/unique-claim/duplicate trace |
| Producer idempotence | note 02 title/matrix | demonstrated | explained | FAIL | COVERAGE-MED/HIGH depending whole-path owner |
| Kafka consume-transform-produce transaction | README build milestone; note 02 | operationalized | demonstrated | PASS conceptually | COVERAGE-HIGH: complete config, recovery, runnable proof |
| External-side-effect boundary | note 02 | explained | explained | PASS | no depth defect |
| Failure classification and bounded retry policy | note 03 | demonstrated | demonstrated | PASS | no depth defect |
| Retry delay/scheduling | note 03 implementation role | operationalized | mentioned | FAIL | COVERAGE-HIGH |
| Atomic/idempotent source→retry/DLT handoff | note 03 recovery promise | operationalized | absent | FAIL | COVERAGE-HIGH |
| DLT provenance | note 03 | demonstrated | demonstrated | PASS | no depth defect |
| Controlled replay | note 03 | operationalized | explained | FAIL execution | COVERAGE-HIGH plus examples defect |
| Database/outbox atomic write | note 04 | operationalized | demonstrated | PASS | COVERAGE-MED/HIGH |
| Polling outbox relay | note 04 | operationalized | explained | FAIL due key/claim details | COVERAGE-HIGH plus local correctness defect |
| CDC outbox relay | note 04 title/role | operationalized | defined | FAIL | COVERAGE-HIGH |
| Consumer duplicate collapse | notes 01/02/04/05 | demonstrated | defined/explained | FAIL | COVERAGE-HIGH; select one canonical owner |
| Real-broker and deterministic crash harness | README and note 05 | operationalized | explained/demonstrated | PASS conceptually | COVERAGE-HIGH plus examples defect |

## Cross-topic and reader-path handoffs

1. Production-hardening path entry 2 cannot meet its advertised execution milestone: note 02 is a correct conceptual transaction trace but not a runnable implementation. Entry 3 then invokes a nonexistent harness. This is the earliest path barrier after note 01.
2. The path says “transaction boundary or outbox transaction where it applies” at entry 2, but outbox is entry 4 and the reading order tests before reaching it. A database→Kafka service therefore encounters its test milestone before its reliability mechanism.
3. Note 01 and application-design note 02 both send readers to reliability note 02 for idempotency, but note 02 gives consumer idempotency only one table row. There is no canonical dedupe implementation owner.
4. Note 03 needs note 02’s transaction/idempotency principle to hand a source record to retry/DLT safely but does not compose it. A reader can describe retry classes yet cannot predict the crash outcomes around recovery publication and offset commit.
5. Note 04 contradicts the already-taught stable aggregate-key invariant by selecting `event_id` as Kafka key. This is a local correctness defect, not merely a path-order problem.
6. Operations is a sensible continuation, but this package does not yet expose transaction timeout/LSO blocking, retry scheduler lag, outbox relay lag/reconciliation, or connector log-retention symptoms that operations can monitor.

Suggested transfer probes for the reader-path owner:

- After note 01: “Offset 8 is committed, then the worker crashes before the database insert returns. What final states are possible?” Expected reasoning cannot be derived reliably from the current at-most-once trace because its crash is placed after processing.
- After note 02: “A transaction for offset 8 is left open, and a later non-transactional record exists at offset 10. What can a `read_committed` consumer return before timeout?” Expected: it stops at the last stable offset and withholds later records; current note lacks this premise, so TRANSFER FAIL.
- After note 03: “The worker publishes offset 8 to `retry.5s` and crashes before committing offset 9. What prevents two retry records?” Current text supplies no transaction/dedupe premise for the handoff, so TRANSFER FAIL.
- After note 04: “Two relays publish `order.created` and `order.cancelled` with different event IDs. Can Kafka preserve their order?” The prerequisite keying lesson supports “not necessarily”; current note’s prescription is wrong, so TRANSFER exposes the defect.
- After note 05: “How does the test know it killed after the effect rather than before it?” Lines 58-63 support waiting for `FAULT_REACHED` from a child process before termination, so conceptual TRANSFER PASS; execution remains unproven.

## Complete executable-claim inventory for assigned files

Statuses follow the skill definitions. Conceptual state traces, JSON envelopes, and decision tables are not counted as executable claims merely because they show exact values.

### E1 — reliability/README.md:24-25,28-29 — package execution milestone

Claim: end-to-end/path promise (“execute” a Kafka transaction or outbox transaction; transaction trace produces one committed output; harness kills at each boundary).

Status: BROKEN.

Command: n/a; promised commands/artifacts are absent from the referenced entries.

Environment: repository at audit commit/worktree; prerequisite broker available at `localhost:9092`.

Observed: note 02 contains only a `text` API trace; note 05 names a missing test file. No executable transaction/outbox processor or process-kill harness exists under `infrastructure/kafka`.

Examples-owner candidate: FIX-HIGH — narrow the milestone to “trace” or provide the complete processor, harness, setup, and observed one-output result.

### E2 — reliability/01_delivery_semantics.md:25-30 — inject three crash windows

Claim: test/integration procedure.

Status: BROKEN.

Command: n/a; delegates to note 05.

Observed: no reusable harness or fault-hook implementation exists; note 05 supplies only a conceptual trace and a missing smoke-test path.

Examples-owner candidate: FIX-HIGH — central guarantee test cannot be reproduced; provide exact process/fixture commands and durable-state assertions.

### E3 — reliability/02_idempotence_transactions_and_exactly_once.md:32-56 — transaction kill/restart success signal

Claim: integration/test procedure; the lines 34-39 `text` block alone is an explanatory trace, but lines 54-56 instruct an observable kill/restart check.

Status: BROKEN.

Command: n/a.

Observed: no producer/consumer program, transaction configuration, input/output topic setup, kill synchronization, or inspection command is supplied. The pseudo-API sequence omits initialization and error/abort behavior and cannot be executed as a file.

Examples-owner candidate: FIX-HIGH — this is the reliability README’s entry-2 implementation milestone.

### E4 — reliability/03_retries_dead_letters_and_replay.md:54-60 — bounded DLT replay pipeline

Claim: runnable operational command.

Status: BROKEN.

Command (executed exactly):

```bash
kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic orders.dlt --partition 0 --offset 0 --max-messages 1 --timeout-ms 10000 \
  --property print.key=true --property key.separator=$'\t' \
  | kafka-console-producer.sh --bootstrap-server localhost:9092 \
      --topic orders.replay.reviewed --property parse.key=true --property key.separator=$'\t'
```

Environment: macOS/zsh repository shell; Docker prerequisite broker running as `kafka-notes`; no host Kafka CLI installation is declared or present.

Observed: exit 127. `zsh: command not found: kafka-console-consumer.sh` and `zsh: command not found: kafka-console-producer.sh`.

Examples-owner candidate: FIX-HIGH — run both tools through the documented container (with stdin/stdout arranged correctly) or add and verify a host-CLI prerequisite; seed the exact DLT record and assert destination key/value and effect count.

### E5 — reliability/04_transactional_outbox_and_cdc.md:23-70 — PostgreSQL schema and atomic `create_order`

Claim: copyable implementation plus a query-based success procedure.

Status: NOT-RUN.

Command: n/a; no PostgreSQL startup/DSN, driver dependency, connection setup, function call, or verification query is supplied.

Environment: unrelated PostgreSQL containers were present but were not mutated; the note authorizes no target database and does not identify one.

Observed: JSON/Python-independent static check only: the Python block at lines 46-66 parses successfully with Python 3 AST. SQL and transaction behavior remain unexecuted.

Examples-owner candidate: FIX-HIGH — because the path promises an executable outbox boundary, provide a disposable database setup, exact driver, schema application, call, both-row/neither-row failure test, query output, and cleanup.

### E6 — reliability/05_testing_kafka_services.md:12-15 — smoke-test setup and run

Claim: runnable quick start.

Status: BROKEN.

Commands:

```bash
uv add --dev pytest confluent-kafka
uv run pytest -q tests/integration/test_kafka_smoke.py
```

Environment: repository root; `uv 0.8.13`; Docker broker running at `localhost:9092`; no `pyproject.toml`, `uv.lock`, `tests/`, or named test file.

Observed: the dependency-add command was not run because it would mutate the audited repository and has no declared project target. The test command was run exactly and exited 2: `Failed to spawn: pytest` / `No such file or directory`. Independent file search confirms `tests/integration/test_kafka_smoke.py` does not exist.

Examples-owner candidate: FIX-HIGH — add the actual isolated test project and file, then run both commands and retain `1 passed` plus cleanup evidence.

### E7 — reliability/05_testing_kafka_services.md:43-66 — child-process crash test

Claim: test/integration procedure.

Status: BROKEN.

Command: n/a; the block is an explanatory state trace, but lines 58-60 explicitly direct running variants.

Observed: no worker executable, effect-store schema, fault-hook implementation, parent-process controller, offset inspection, or assertions are present.

Examples-owner candidate: FIX-HIGH — the note’s central claimed harness cannot be reproduced.

### E8 — reliability/05_testing_kafka_services.md:70-93 — reusable suite claims

Claim: integration/test suite architecture, including contract, broker, replay, and capacity suites.

Status: NOT-RUN.

Command: n/a.

Observed: the section gives a design inventory but no repository fixtures or suite artifacts. The Testcontainers link is the Java module while this collection promises Python systems.

Examples-owner candidate: FIX-MED — label the section explicitly as design guidance and link to one canonical implemented suite; do not imply these suites exist locally.

### Non-executable artifacts inspected

- `03_retries_dead_letters_and_replay.md:18-28`: JSON retry envelope; syntactically VERIFIED with `jq -e .`; conceptual artifact, excluded from executable denominator.
- `02_idempotence_transactions_and_exactly_once.md:34-39,47-52`, `04_transactional_outbox_and_cdc.md:14-18,84-90`, and `05_testing_kafka_services.md:49-56`: explanatory state/API traces; EXCERPT/non-executable.
- `04_transactional_outbox_and_cdc.md:46-66`: Python snippet syntax VERIFIED via `ast.parse`; runtime behavior NOT-RUN as recorded in E5.

Executable-claim totals for this batch: 8 claims; 0 VERIFIED, 6 BROKEN, 2 NOT-RUN, 0 PARTIAL. Explanatory excerpts are excluded.

## Checks and evidence

Local checks run:

- Full-prose read with numbered lines for all six assigned files, Kafka root README, fundamentals README and notes 01-05, and linked application notes 01, 02, and 05.
- `wc -l`: exact assigned counts are README 31; note 01 46; note 02 73; note 03 86; note 04 114; note 05 111.
- Repository search: no `tests/integration/test_kafka_smoke.py`, no `tests/integration/`, no root `pyproject.toml`, and no root `uv.lock`.
- `docker info`: daemon reachable, server 29.6.2; `docker ps` showed `kafka-notes` bound to 9092. Existing containers were not stopped, deleted, or repurposed.
- Exact replay pipeline: exit 127 because both host Kafka commands are absent.
- Exact `uv run pytest -q tests/integration/test_kafka_smoke.py`: exit 2 because `pytest` cannot be spawned; the named file is also absent.
- Retry JSON parsed successfully with `jq`; outbox Python block parsed successfully with Python AST.

Primary sources inspected on 2026-09-16:

- Apache Kafka 4.3 design, “Message Delivery Semantics” and “Using Transactions”: https://kafka.apache.org/43/design/design/ — establishes the correct at-most-once crash window; output+offset transaction boundary; required `read_committed`, disabled auto commit, stable transactional identity, and explicit position reset after abort.
- Apache Kafka 4.3.1 `KafkaProducer` API: https://kafka.apache.org/43/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html — establishes idempotence/session limits, `initTransactions()` recovery, unique producer-instance `transactional.id`, send-offset requirements, and abort/error handling.
- Apache Kafka 4.3 producer configuration: https://kafka.apache.org/43/generated/producer_config.html — confirms idempotence defaults/compatibility and transaction timeout behavior.
- Apache Kafka 4.3 consumer configuration: https://kafka.apache.org/43/generated/consumer_config.html — confirms `read_committed` stops at the last stable offset and withholds later records behind an open transaction; default is `read_uncommitted`.
- Debezium maintained Outbox Event Router documentation: https://debezium.io/documentation/reference/transformations/outbox-event-router.html — confirms insert-only outbox expectations and use of aggregate ID as event key to preserve Kafka partition ordering.
- Testcontainers for Java Kafka module: https://java.testcontainers.org/modules/kafka/ — confirms the note’s linked module is maintained, but it is not a Python harness or proof of this repository’s missing test.

Unresolved items / boundaries:

- No PostgreSQL example was executed because the note supplies no authorized disposable database target or connection inputs; unrelated running containers were not used.
- `uv add --dev pytest confluent-kafka` was not executed because audit-only work must not create or mutate project metadata; the subsequent documented test command was safely attempted and failed.
- The replay command was not rewritten and rerun through `docker exec`; that would test a proposed correction, not the exact documented claim. Exact-command failure is established.
- No broker topics or records were created or deleted during this batch, avoiding interference with concurrently running review work.
- Current Kafka/Debezium documentation was checked, but no vendor-specific managed-Kafka transaction limits or framework wrappers were in scope.
