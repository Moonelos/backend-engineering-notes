# fundamentals/01_first_event_round_trip.md :: broker setup (lines 10–15)
Claim: runnable
Status: VERIFIED
Command: exact `docker run ... apache/kafka:4.3.1` and in-container `kafka-topics.sh --create` block.
Environment: Docker 29.6.2; official Kafka 4.3.1 image; isolated `kafka-notes` container.
Observed: exit 0; `Created topic orders.` after transient startup connection warnings.

NO-ACTION: The bounded local setup ran exactly as shown.

# fundamentals/01_first_event_round_trip.md :: publish/consume (lines 19–27)
Claim: end-to-end
Status: VERIFIED
Command: exact producer pipeline and in-container console-consumer block.
Environment: preceding disposable broker/topic.
Observed: exit 0; `Partition:0 Offset:0` plus the `evt-101` JSON and `Processed a total of 1 messages`; Kafka also emitted the deprecated-option warning owned by `fundamentals.audit.md`.

NO-ACTION: Record, partition, offset, and payload matched the claim.

# fundamentals/01_first_event_round_trip.md :: startup diagnostic (line 30)
Claim: runnable
Status: NOT-RUN
Command: `docker logs kafka-notes`
Environment: failure condition did not persist.
Observed: Setup itself showed transient connection warnings, but forcing the failure would not test the claimed usual cause.

# fundamentals/01_first_event_round_trip.md :: replay (lines 40–42)
Claim: integration
Status: VERIFIED
Command: exact console-consumer command rerun after the first consumer exited.
Environment: same disposable broker/topic.
Observed: exit 0; partition 0 offset 0 and the same JSON returned again.

NO-ACTION: The changed-condition replay claim was reproduced.

# fundamentals/01_first_event_round_trip.md :: cleanup (line 87)
Claim: runnable
Status: VERIFIED
Command: `docker stop kafka-notes`, then `docker ps`.
Environment: container created with `--rm`.
Observed: exit 0; no running or stopped `kafka-notes` container remained.

NO-ACTION: Cleanup and absence signal matched.

# fundamentals/03_partitioning_keys_and_ordering.md :: cross-client placement (lines 27–30)
Claim: integration
Status: NOT-RUN
Command: n/a; no client languages/versions, serializers, partitioners, topic size, or inspection command are supplied.
Environment: unspecified multi-client fixture.
Observed: The prose gives a valid expected equality/mismatch signal but is not exactly reproducible.

# fundamentals/04_consumer_groups_offsets_and_rebalancing.md :: assignment/restart check (lines 68–69)
Claim: integration
Status: NOT-RUN
Command: n/a; topology, group members, effect probe, inspection command, timeout, and bounded-handoff threshold are absent.
Environment: unspecified multi-consumer fixture.
Observed: Conceptual success criterion only.

# fundamentals/05_replication_leaders_and_kraft.md :: broker failover check (lines 58–60)
Claim: integration
Status: NOT-RUN
Command: n/a; no multi-broker fixture or exact describe/stop/read sequence is supplied.
Environment: documented quick start is intentionally one broker/RF=1.
Observed: Not reproducible from the collection.

# application_design/01_event_contracts_and_schema_evolution.md :: validator command (lines 22–71)
Claim: runnable
Status: BROKEN
Command: exact `uv add jsonschema && uv run python -c ...` command after saving the two named files.
Environment: fresh temporary directory, `uv 0.8.13`, no undeclared project metadata.
Observed: exit 2: `No pyproject.toml found`. Running the code with `uv run --with jsonschema` separately printed `contract: valid`, so code logic was only partially verified.

FIX-MED: Add the missing project initialization/manifest (or use a self-contained `uv run --with` command) and retain the exact success signal.

# application_design/01_event_contracts_and_schema_evolution.md :: compatibility tests (lines 98–130)
Claim: test
Status: BROKEN
Command: exact `uv add --dev pytest && uv run pytest -q` after saving the shown block as a discovered test file.
Environment: fresh temporary directory; no documented project initialization or test filename.
Observed: exact dependency command fails without `pyproject.toml`; with an audit-supplied environment, both tests passed. The pass is false evidence for the stated two directions: both calls use the same v1 validator, and `coupon_code` is already declared in the v1 schema at line 43.

FIX-HIGH: Supply distinct v1 and v2 reader schemas/validators and a named test file; make backward compatibility run old retained data through the v2 reader and forward compatibility run v2 data through the v1 reader. Use a genuinely new additive field, then execute the exact documented command.

# application_design/02_python_producers_and_consumers.md :: Python round trip (lines 7–72)
Claim: end-to-end
Status: BROKEN
Command: `uv add confluent-kafka`, then `uv run python kafka_round_trip.py`.
Environment: collection root and named root exploration path.
Observed: no `pyproject.toml` exists; the script also imports `event_contract`, which the root exploration path intentionally places later, and no host broker remained after the disposable prerequisite cleanup.

FIX-HIGH: Provide one assembled project/setup path and place or generate `event_contract.py` before this script in every named route; then reproduce acknowledgment, consumption, timeout, and cleanup.

# application_design/03_processing_loops_backpressure_and_shutdown.md :: bounded worker drill (lines 55–233)
Claim: end-to-end
Status: NOT-RUN
Command: exact worker plus topic/create/publish/SIGTERM/restart procedure.
Environment: Python blocks parse; live execution withheld because the ownership-loss path is unsafe and would require recreating mutable broker state.
Observed: `on_revoke` times out with unfinished work, calls `unassign`, and later final draining can process/attempt commits for revoked work; no `on_lost` handler distinguishes already-lost ownership. The client docs warn lost partitions may already belong to another member and commits may fail.

FIX-HIGH: Fence or cancel revoked work, never commit a partition after ownership is lost, add a distinct `on_lost` path, and verify a forced rebalance with two consumers before presenting the drill as safe. Source: https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html (checked 2026-09-16).

# application_design/05_schema_registry_and_serialization.md :: configure/register v1 (lines 25–42)
Claim: runnable
Status: NOT-RUN
Command: exact PUT policy and POST registration commands.
Environment: no Schema Registry at documented `localhost:8081`; procedure mutates registry state.
Observed: endpoint connection failed; no registration result was invented.

# application_design/05_schema_registry_and_serialization.md :: additive schema transform (lines 65–75)
Claim: runnable
Status: VERIFIED
Command: exact `jq '.fields += ...' order-created-v1.avsc` transform; output parsed with `jq empty`.
Environment: temporary exact v1 Avro file.
Observed: exit 0; generated valid JSON containing nullable `coupon_code` with default null.

NO-ACTION: The local transformation reproduced successfully.

# application_design/05_schema_registry_and_serialization.md :: compatibility request (lines 78–88)
Claim: integration
Status: NOT-RUN
Command: exact `jq -Rs ... | curl ... /compatibility/.../versions?verbose=true` pipeline.
Environment: no Schema Registry at `localhost:8081`.
Observed: remote compatibility result unavailable; endpoint shape matches the current Confluent API.

# application_design/05_schema_registry_and_serialization.md :: breaking schema transform (lines 88–98)
Claim: runnable
Status: VERIFIED
Command: exact `jq` assignment changing `total_minor` to `string`; output parsed with `jq empty`.
Environment: temporary exact v1 Avro file.
Observed: exit 0; generated valid JSON with the intended type change.

NO-ACTION: The local breaking-candidate transformation reproduced successfully.

# reliability/README.md :: execution milestone (lines 24–29)
Claim: end-to-end
Status: BROKEN
Command: n/a; promised processor/harness artifacts are absent.
Environment: repository tree.
Observed: note 02 has a text trace only; note 05 names a nonexistent test file.

FIX-HIGH: Narrow the milestone to a worked trace or provide the complete transaction/outbox processor, process-kill harness, setup, and observed one-output result.

# reliability/01_delivery_semantics.md :: crash-window tests (lines 25–30)
Claim: test
Status: BROKEN
Command: n/a; delegated harness does not exist.
Environment: repository tree.
Observed: no process/fixture commands or durable-state assertions can be run.

FIX-HIGH: Provide exact fault-hook, process, durable-store, restart, and offset/effect assertions for all three crash points.

# reliability/02_idempotence_transactions_and_exactly_once.md :: transaction kill/restart (lines 32–56)
Claim: integration
Status: BROKEN
Command: n/a; the API sequence is a text excerpt.
Environment: no processor, transaction configuration, topics, consumer, or fault hook.
Observed: the package's central implementation milestone cannot execute.

FIX-HIGH: Supply `transactional.id`, initialization, auto-commit/isolation settings, abort/error path, synchronized kill, restart, and output/offset inspection.

# reliability/03_retries_dead_letters_and_replay.md :: bounded replay (lines 54–60)
Claim: runnable
Status: BROKEN
Command: exact host `kafka-console-consumer.sh | kafka-console-producer.sh` pipeline.
Environment: documented Kafka CLIs exist only inside the prerequisite Docker container.
Observed: exit 127; both commands were not found.

FIX-HIGH: Run both tools through the documented container or declare/install host CLIs; seed the exact DLT record and assert destination key/value and effect count.

# reliability/04_transactional_outbox_and_cdc.md :: database/outbox write (lines 23–70)
Claim: copyable
Status: NOT-RUN
Command: n/a; SQL/Python artifacts lack database startup/DSN, driver, connection, invocation, verification query, and cleanup.
Environment: unrelated PostgreSQL services were not mutated.
Observed: Python parses; database transaction behavior remains unexecuted.

FIX-HIGH: Provide a disposable database, exact dependency/DSN/schema/call/query/cleanup, and both-row-or-neither-row failure test.

# reliability/05_testing_kafka_services.md :: smoke test (lines 12–15)
Claim: test
Status: BROKEN
Command: `uv run pytest -q tests/integration/test_kafka_smoke.py` (dependency mutation omitted because no project exists).
Environment: repository root; no `pyproject.toml`, `uv.lock`, `tests/`, or named file.
Observed: exit 2: pytest could not be spawned; file search confirms the target is absent.

FIX-HIGH: Add an isolated Python test project and the actual test, then reproduce `1 passed` and cleanup.

# reliability/05_testing_kafka_services.md :: child-process crash test (lines 43–66)
Claim: test
Status: BROKEN
Command: n/a.
Environment: worker, effect-store schema, hook, controller, offset inspection, and assertions are absent.
Observed: conceptual trace only despite instructions to run variants.

FIX-HIGH: Implement the promised child-process harness and execute each synchronized crash window.

# reliability/05_testing_kafka_services.md :: reusable suites (lines 70–93)
Claim: integration
Status: NOT-RUN
Command: n/a.
Environment: no fixtures or suites exist; linked Testcontainers module is Java-specific in a Python course.
Observed: design inventory only.

FIX-MED: Label this as design guidance and link to one canonical implemented Python or language-neutral suite.

# operations/01_security_and_multitenancy.md :: Python producer config (lines 23–37)
Claim: copyable
Status: PARTIAL
Command: Python AST parse; runtime construction not attempted.
Environment: no client module, password, CA file, DNS, or authorized broker.
Observed: syntax passed; block never calls `produce`, so construction alone would not verify authorization.

RELATED: `operations.audit.md` owns the missing composed verification.

# operations/01_security_and_multitenancy.md :: ACL mutations (lines 42–57)
Claim: runnable
Status: NOT-RUN
Command: three exact `kafka-acls.sh --add` commands.
Environment: no live target/admin properties; commands mutate authorization state.
Observed: shell syntax passed; no mutation attempted.

# operations/01_security_and_multitenancy.md :: ACL diagnosis (line 63)
Claim: runnable
Status: PARTIAL
Command: `kafka-acls.sh --list`
Environment: secured remote environment described by the note.
Observed: inspection only; the inline command omits required bootstrap and authenticated admin configuration.

FIX-MED: Show a complete read-only list command using the same endpoint/admin properties and the wildcard/prefix row that diagnoses the policy.

# operations/03_observability_and_incident_response.md :: Prometheus rules (lines 32–62)
Claim: copyable
Status: PARTIAL
Command: exact YAML parsed; no `promtool check rules` environment was available.
Environment: no Prometheus, exporter metrics, rule file, or alert receiver.
Observed: YAML syntax passed; PromQL labels, reload, and firing remain unverified.

RELATED: `operations.audit.md` owns the absent implementation path.

# operations/05_configuration_and_topic_administration.md :: create/describe (lines 10–20)
Claim: runnable
Status: NOT-RUN
Command: exact topic creation and config-description commands.
Environment: no authorized three-broker target; creation mutates external state.
Observed: shell syntax passed; no mutation attempted.

# operations/05_configuration_and_topic_administration.md :: alter/rollback retention (lines 57–67)
Claim: runnable
Status: NOT-RUN
Command: exact retention alteration; rollback described with prior value.
Environment: no live target/admin properties/canary or observation window; mutation outside authorized scope.
Observed: shell syntax passed; no alteration attempted.

Execution totals: 30 claims; 6 VERIFIED, 9 BROKEN, 3 PARTIAL, 12 NOT-RUN. Explanatory traces and static JSON/YAML/SQL carriers without a runnable claim are excluded.
