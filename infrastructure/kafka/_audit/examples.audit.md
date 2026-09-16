# fundamentals/01_first_event_round_trip.md :: broker setup (lines 10–15)
Claim: runnable
Status: VERIFIED
Command: exact `docker run ... apache/kafka:4.3.1` and in-container `kafka-topics.sh --create` block.
Environment: fresh refresh run on 2026-09-16; official Kafka 4.3.1 image; isolated `kafka-notes` container.
Observed: exit 0; `Created topic orders.` after transient startup connection warnings.

NO-ACTION: The bounded local setup ran exactly as shown.

# fundamentals/01_first_event_round_trip.md :: publish/consume (lines 19–27)
Claim: end-to-end
Status: VERIFIED
Command: exact producer pipeline and in-container console-consumer block.
Environment: freshly created disposable broker/topic; exact refresh reproduction 2026-09-16.
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
Environment: same fresh disposable broker/topic; exact refresh reproduction 2026-09-16.
Observed: exit 0; partition 0 offset 0 and the same JSON returned again.

NO-ACTION: The changed-condition replay claim was reproduced.

# fundamentals/01_first_event_round_trip.md :: cleanup (line 87)
Claim: runnable
Status: VERIFIED
Command: `docker stop kafka-notes`, then `docker ps -a --filter name='^/kafka-notes$' --format '{{.Names}}'` to check the documented absence signal.
Environment: container created in this refresh with `--rm`; filtered docker ps -a subsequently empty.
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
Command: executed the documented first dependency step `uv add jsonschema` in a fresh directory. Its failure blocks the documented `&& uv run python -c ...` continuation; that continuation was not executed.
Environment: fresh temporary directory; no undeclared project metadata.
Observed: fresh exact dependency command exited 2: `No pyproject.toml found`; the chained validator command was not reached. Evidence: `_parts/refresh-global/local-probes.json`. No successful validator execution is claimed by this entry.

FIX-MED: Add the missing project initialization/manifest (or use a self-contained `uv run --with` command) and retain the exact success signal.

# application_design/01_event_contracts_and_schema_evolution.md :: compatibility tests (lines 98–130)
Claim: test
Status: BROKEN
Command: executed the documented first dependency step `uv add --dev pytest` in a fresh directory. The `&& uv run pytest -q` continuation was not executed; the source test block was inspected separately.
Environment: fresh temporary directory; no documented project initialization or test filename.
Observed: fresh exact dependency command exited 2 without `pyproject.toml`; pytest was not reached. Static inspection additionally shows both calls use the same v1 validator, and `coupon_code` is already declared in the v1 schema at line 43. A hypothetical green result would not establish the claimed two reader generations. Evidence: `_parts/refresh-global/local-probes.json`.

FIX-HIGH: Supply distinct v1 and v2 reader schemas/validators and a named test file; make backward compatibility run old retained data through the v2 reader and forward compatibility run v2 data through the v1 reader. Use a genuinely new additive field, then execute the exact documented command.

# application_design/02_python_producers_and_consumers.md :: Python round trip (lines 7–72)
Claim: end-to-end
Status: BROKEN
Command: `uv add confluent-kafka`, then `uv run python kafka_round_trip.py`.
Environment: fresh temporary directory for the exact dependency command; static inspection of collection root and named root exploration path.
Observed: fresh `uv add confluent-kafka` exited 2 because no `pyproject.toml` exists; the live client script was not run. Static inspection shows the script also imports `event_contract`, which the root exploration path intentionally places later, and its earliest reader encounters the quickstart record whose schema is incompatible with event_contract. Supplemental execution of the exact validator against that retained payload raised ValidationError: event_type is a required property. The quickstart uses type and a top-level order_id; the client expects event_type and data.order_id.

FIX-HIGH: Compose this client with the shared project setup owned by the contract-command finding; place or generate `event_contract.py` before this script in every named route; use a dedicated freshly seeded topic or teach an explicit schema transition from the quickstart record; then reproduce acknowledgment, consumption, timeout, and cleanup.

# application_design/03_processing_loops_backpressure_and_shutdown.md :: bounded worker drill (lines 55–233)
Claim: end-to-end
Status: NOT-RUN
Command: exact worker plus topic/create/publish/SIGTERM/restart procedure.
Environment: source inspection only for the full worker; no live drill executed. The ownership-loss path requires repair before the documented drill can establish correctness.
Observed: `on_revoke` times out with unfinished work, calls `unassign`, and later final draining can process/attempt commits for revoked work; no `on_lost` handler distinguishes already-lost ownership. The client docs warn lost partitions may already belong to another member and commits may fail.

FIX-HIGH: Fence or cancel revoked work, never commit a partition after ownership is lost, add a distinct `on_lost` path, and verify a forced rebalance with two consumers before presenting the drill as safe. Source: https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html (checked 2026-09-16).

# application_design/05_schema_registry_and_serialization.md :: configure/register v1 (lines 25–42)
Claim: runnable
Status: NOT-RUN
Command: exact PUT policy and POST registration commands.
Environment: no isolated Schema Registry fixture was provisioned for this refresh; procedure mutates registry state.
Observed: no HTTP request or registration result is claimed in this refresh.

# application_design/05_schema_registry_and_serialization.md :: additive schema transform (lines 65–75)
Claim: runnable
Status: VERIFIED
Command: exact `jq '.fields += ...' order-created-v1.avsc` transform; output parsed with `jq empty`.
Environment: fresh temporary exact v1 Avro file; rerun 2026-09-16.
Observed: exit 0; generated valid JSON containing nullable `coupon_code` with default null.

NO-ACTION: The local transformation reproduced successfully.

# application_design/05_schema_registry_and_serialization.md :: additive and breaking compatibility requests (lines 78–96)
Claim: integration
Status: NOT-RUN
Command: exact `jq -Rs ... | curl ... /compatibility/.../versions?verbose=true` pipeline, first with the additive candidate, then the instructed breaking-candidate substitution.
Environment: no isolated Schema Registry fixture provisioned.
Observed: neither expected is_compatible=true nor is_compatible=false response was reproduced; successful local jq transformations do not verify either remote result.

# application_design/05_schema_registry_and_serialization.md :: breaking schema transform (lines 88–98)
Claim: runnable
Status: VERIFIED
Command: exact `jq` assignment changing `total_minor` to `string`; output parsed with `jq empty`.
Environment: fresh temporary exact v1 Avro file; rerun 2026-09-16.
Observed: exit 0; generated valid JSON with the intended type change.

NO-ACTION: The local breaking-candidate transformation reproduced successfully.

# reliability/README.md :: execution milestone (lines 24–29)
Claim: end-to-end
Status: NOT-RUN
Command: n/a; promised processor/harness artifacts are absent.
Environment: repository tree.
Observed: static artifact inventory; no command was executed for this claim. Note 02 has a text trace only; note 05 names a nonexistent test file.

RELATED: reader_paths.audit.md owns the premature execution milestone; transaction-processor and reliability/05 harness findings below own the missing executable artifacts.

# reliability/01_delivery_semantics.md :: crash-window tests (lines 25–30)
Claim: test
Status: NOT-RUN
Command: n/a; delegated harness does not exist.
Environment: repository tree.
Observed: static artifact inventory; no command was executed for this claim. No process/fixture commands or durable-state assertions can be run.

RELATED: reliability/05 child-process crash test below owns the shared missing fault-hook/process/store/restart/offset-effect harness; no duplicate severity here.

# reliability/02_idempotence_transactions_and_exactly_once.md :: transaction kill/restart (lines 32–56)
Claim: integration
Status: NOT-RUN
Command: n/a; the API sequence is a text excerpt.
Environment: no processor, transaction configuration, topics, consumer, or fault hook.
Observed: static artifact inventory; no command was executed for this claim. The package's central implementation milestone cannot execute.

FIX-HIGH: Supply the missing transaction processor with `transactional.id`, initialization, input/output topics, auto-commit/isolation settings, abort/error path, and observable committed output/offset state. Compose it with the canonical reliability/05 fault harness; shared kill/restart infrastructure is counted there, not again here.

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
Observed: source artifacts inspected; neither Python execution nor database transaction behavior was reproduced in this refresh.

FIX-HIGH: Provide a disposable database, exact dependency/DSN/schema/call/query/cleanup, and both-row-or-neither-row failure test.

# reliability/05_testing_kafka_services.md :: smoke test (lines 12–15)
Claim: test
Status: BROKEN
Command: `uv run pytest -q tests/integration/test_kafka_smoke.py` (dependency mutation omitted because no project exists).
Environment: fresh temporary directory for the command probe; source-tree inspection finds no documented test project or named test file.
Observed: exit 2: pytest could not be spawned; file search confirms the target is absent.

FIX-HIGH: Supply the actual smoke-test file and compose it with the shared Python project setup owned by the contract-command finding, then reproduce `1 passed` and cleanup. The missing test artifact is distinct from dependency initialization.

# reliability/05_testing_kafka_services.md :: child-process crash test (lines 43–66)
Claim: test
Status: NOT-RUN
Command: n/a.
Environment: worker, effect-store schema, hook, controller, offset inspection, and assertions are absent.
Observed: static artifact inventory; no command was executed for this claim. Conceptual trace only despite instructions to run variants.

FIX-HIGH: Implement one canonical child-process harness with worker readiness/fault hooks, effect-store schema, kill/restart controller, and durable offset/effect assertions. Execute every synchronized crash window; reliability/01 and the reliability README reuse this same owner.

# reliability/05_testing_kafka_services.md :: reusable suites (lines 70–93)
Claim: excerpt
Status: EXCERPT
Command: n/a.
Environment: conceptual suite and fixture design; not a supplied runnable suite.
Observed: prose explains test layers and when suites run. Its Java Testcontainers link is an integration-language consideration, not evidence that this conceptual inventory promises executable Python fixtures.

NO-ACTION: Design guidance is assessed as explanation; missing actual smoke/crash artifacts remain separately reported.

# operations/01_security_and_multitenancy.md :: Python producer config (lines 23–37)
Claim: copyable
Status: NOT-RUN
Command: n/a; supplied Producer configuration inspected but not executed.
Environment: no isolated secured broker, credential/CA fixture, or authorized target provisioned.
Observed: source inspection only; block never calls produce, so construction alone would not verify authorization.

RELATED: coverage.audit.md owns missing security composition; operations.audit.md owns the distinct topic/group permission defect.

# operations/01_security_and_multitenancy.md :: ACL mutations (lines 42–57)
Claim: runnable
Status: NOT-RUN
Command: three exact `kafka-acls.sh --add` commands.
Environment: no live target/admin properties; commands mutate authorization state.
Observed: commands inspected; no CLI execution or authorization mutation attempted in this refresh.

# operations/01_security_and_multitenancy.md :: ACL diagnosis (line 63)
Claim: runnable
Status: NOT-RUN
Command: `kafka-acls.sh --list`
Environment: secured remote environment described by the note.
Observed: inspection only; the inline command omits required bootstrap and authenticated admin configuration.

FIX-MED: Show a complete read-only list command using the same endpoint/admin properties and the wildcard/prefix row that diagnoses the policy.

# operations/03_observability_and_incident_response.md :: Prometheus rules (lines 32–62)
Claim: copyable
Status: NOT-RUN
Command: n/a; supplied Prometheus rule YAML inspected, not loaded or checked with promtool.
Environment: no isolated Prometheus/exporter/alert-receiver fixture provisioned.
Observed: source inspection only; syntax validation, PromQL evaluation, reload, and firing are not claimed by this refresh.

RELATED: coverage.audit.md owns the absent monitoring implementation path.

# operations/05_configuration_and_topic_administration.md :: create/describe (lines 10–20)
Claim: runnable
Status: NOT-RUN
Command: exact topic creation and config-description commands.
Environment: no authorized three-broker target; creation mutates external state.
Observed: commands inspected; no CLI execution or topic mutation attempted in this refresh.

# operations/05_configuration_and_topic_administration.md :: alter/rollback retention (lines 57–67)
Claim: runnable
Status: NOT-RUN
Command: exact retention alteration; rollback described with prior value.
Environment: no live target/admin properties/canary or observation window; mutation outside authorized scope.
Observed: source inspection only; alteration, canary publication, before/after describe, observation window, and rollback were not executed.

# application_design/03_processing_loops_backpressure_and_shutdown.md :: nonconsecutive offset frontier probe
Claim: test
Status: PARTIAL
Command: execute the original Frontier class in isolation; observe and complete offsets 10 and 12, then call committable twice.
Environment: auditor test; TopicPartition replaced only by a tuple constructor; no live Kafka or service handlers. Original algorithm unchanged.
Observed: first call returned (orders, 0, 11); second returned []; completed offset 12 remained stranded waiting for nonexistent 11. This disproves gap handling, not a claim of full worker reproduction. Evidence: `_parts/refresh-global/local-probes.json`.

FIX-HIGH: Track the ordered records actually delivered and their completion, not every integer offset. Kafka permits gaps from compaction and transactions; advancing through delivered successes must not wait forever for an offset never delivered. Verify both a numeric gap and a real unfinished delivered record before accepting the frontier. [KafkaConsumer position contract](https://kafka.apache.org/43/javadoc/org/apache/kafka/clients/consumer/KafkaConsumer.html), checked 2026-09-16.



# fundamentals/03_partitioning_keys_and_ordering.md :: entity-order verification (lines 61–63)
Claim: integration
Status: NOT-RUN
Command: n/a; no inspection fixture or command supplied.
Environment: No entity-history fixture with a stated business-order invariant.
Observed: Partition co-location and business-valid ordering were not sampled; cross-client partition equality above is a distinct probe.

RELATED: lesson_quality.audit.md owns the undeveloped ordering/placement decision; no additional execution severity.

# application_design/05_schema_registry_and_serialization.md :: restore and unavailable-registry drills (lines 105–118)
Claim: integration
Status: NOT-RUN
Command: n/a; no restore or serializer/unavailability procedure supplied.
Environment: No disposable registry backup, old/new wire-record fixture, or configured serializer/deserializer.
Observed: Decoding oldest/newest retained IDs after restore and client behavior during registry unavailability were not executed.

RELATED: lesson_quality.audit.md LQ-A05 owns registry lifecycle development; coverage.audit.md records unmet operational depth.

# reliability/03_retries_dead_letters_and_replay.md :: invalid-event recovery lifecycle (lines 69–71)
Claim: integration
Status: NOT-RUN
Command: n/a; no composed retry/DLT/replay worker procedure supplied.
Environment: No isolated failure-injection worker, corrected payload fixture, or durable effect store.
Observed: Invalid input was not driven into DLT or through corrected replay to one business effect. The host transport failure above tests only copying an existing envelope.

RELATED: coverage.audit.md owns controlled recovery depth; bounded transport repair remains separately owned above.

# reliability/04_transactional_outbox_and_cdc.md :: relay crash recovery (lines 97–98)
Claim: test
Status: NOT-RUN
Command: n/a; no relay/fault-control invocation supplied.
Environment: No disposable database plus relay and effect-store harness.
Observed: Neither crash after database commit before publication nor crash after acknowledged publication was injected; eventual emission and duplicate-safe effect remain unverified.

RELATED: coverage.audit.md owns relay operationalization; reliability/05 owns shared fault-harness absence.

# operations/01_security_and_multitenancy.md :: positive and negative authorization tests (lines 60–70)
Claim: integration
Status: NOT-RUN
Command: n/a; exact produce/read probes are absent.
Environment: No isolated secured cluster, provisioned service identities, or authenticated test clients.
Observed: Permitted write/read and denied unrelated-topic write/wrong-group read were not executed; ACL configuration alone is not this verification.

RELATED: operations.audit.md and coverage.audit.md own the missing security verification path.

# operations/02_capacity_planning_and_performance.md :: load and broker-loss capacity drill (lines 50–54)
Claim: test
Status: NOT-RUN
Command: n/a; no load generator, fixture, or broker-stop procedure supplied.
Environment: No production-shaped records, downstream service, or disposable multi-broker cluster.
Observed: Peak ingress, 30-minute catch-up, and one-broker-loss disk/throughput limits were not measured. This does not invalidate the explanatory sizing arithmetic by itself.

RELATED: coverage.audit.md credits a provisional demonstrated estimate, not an executed capacity benchmark.

# operations/03_observability_and_incident_response.md :: slow-handler alert drill (lines 75–77)
Claim: test
Status: NOT-RUN
Command: n/a; no injection, metric seed, rule-load, or alert-observation procedure supplied.
Environment: No isolated worker, exporter, Prometheus, or alert receiver.
Observed: No slow handler was injected; firing labels and diagnostic runbook outcome were not observed.

RELATED: coverage.audit.md owns monitoring operationalization; rule configuration above is separately unexecuted.

# operations/04_deployment_upgrades_and_disaster_recovery.md :: broker or region game day (lines 53–56)
Claim: test
Status: NOT-RUN
Command: n/a; no bounded failover procedure supplied.
Environment: No disposable replicated multi-cluster environment, copied schemas/ACLs/offsets, or effect-store drill.
Observed: RTO, actual RPO, and duplicate-safe resume were not measured. The displayed timestamp timeline is conceptual evidence, not execution.

RELATED: coverage.audit.md owns recovery operationalization and lesson_quality.audit.md owns explanation/decision development.

# ecosystem/01_kafka_connect_and_data_integration.md :: task restart and admin denial (lines 21–23)
Claim: integration
Status: NOT-RUN
Command: n/a; no connector configuration or stop/restart/admin probe supplied.
Environment: No isolated Connect workers, source/sink fixture, saved checkpoint, or security setup.
Observed: Checkpointed task recovery without missing data and rejected unauthorized administration were not executed.

RELATED: coverage.audit.md assesses the scoped Connect decision; this unexecuted evaluation drill does not convert a selection guide into a promised implementation.

# ecosystem/02_stream_processing.md :: late-record restart probe (lines 43–44)
Claim: test
Status: NOT-RUN
Command: n/a; no selected engine/application or input driver supplied.
Environment: Conceptual window trace only; no executable stateful processor/checkpoint fixture.
Observed: On-time and late inputs were not fed to a live processor; post-restart window updates were not observed.

RELATED: coverage.audit.md owns stream-processing depth and ecosystem.audit.md owns technical time-model claims.

# ecosystem/03_share_groups_and_queue_semantics.md :: worker-kill redelivery probe (lines 38–39)
Claim: test
Status: NOT-RUN
Command: n/a; no supported client fixture or kill/inspection sequence supplied.
Environment: No share-consumer worker pair with known acknowledgment and lock settings.
Observed: Worker failure, redelivery, and absence of immediate accepted-record redelivery were not reproduced.

RELATED: ecosystem.audit.md records Python-client applicability; coverage.audit.md credits only the conceptual delivery model, not operational verification.

# Conceptual traces across the collection :: explanation artifacts
Claim: excerpt
Status: EXCERPT
Command: n/a; no program execution claimed for the traces themselves.
Environment: fundamentals log/placement/group/replica diagrams; application contract/envelope and frontier illustrations; reliability transaction/crash/retry/outbox timelines; operations sizing/triage/DR/config state tables; ecosystem window/share-lock traces and decision tables.
Observed: These diagrams, JSON examples, pseudocode traces, and decision tables supply conceptual teaching evidence. Their separate explicit execution or observation instructions are inventoried above. Pure topic-design and architecture-choice payoffs do not require a runnable example.

NO-ACTION: Exclude explanatory artifacts from executable-claim denominators; their correctness and instructional quality remain assessed in local, coverage, and lesson-quality reports.

Refresh evidence: `_parts/refresh-global/README.md`. Fresh exact successes, failures, and supplemental probes are distinguished there. Missing-artifact claims use NOT-RUN rather than suggesting a fabricated runtime failure. Other service-dependent checks remain unexecuted; prior static findings were reconciled against unchanged source.
