# application_design/README.md (29 lines)
ORDERING: role reference/navigation; n/a; payoff n/a; lines 19–29 define a contract-first sequence, milestone, and stop point.
EXPLANATION: n/a; teach-back n/a (missing: none); this is a path index rather than a mechanism owner.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `reader_paths.audit.md` owns the missing runnable-environment bridge in this named path.

# application_design/01_event_contracts_and_schema_evolution.md (162 lines)
ORDERING: role implementation; PASS; payoff 5/162; a concrete event, complete JSON Schema, validator, command, and success/failure signal precede compatibility theory.
EXPLANATION: PASS; teach-back PASS (missing: none); lines 75–96 explain retained-data/deployment skew, reader/writer compatibility, and the structural-versus-semantic boundary, while lines 136–158 supply the event/command distinction and first production failures.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `examples.audit.md` owns the compatibility test that passes without exercising the claimed old/new reader directions.

# application_design/02_python_producers_and_consumers.md (118 lines)
ORDERING: role implementation; PASS; payoff 5/118; the complete producer/consumer path and its visible delivery/consumption signals appear before client internals and hardening.
EXPLANATION: PASS; teach-back PASS (missing: none); lines 76–104 distinguish local enqueue from broker acknowledgement and place the committed offset after the effect, while lines 108–114 identify buffered-loss and deployment boundaries.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `examples.audit.md` owns the environment-dependent round trip; `reader_paths.audit.md` owns the root exploration route placing this imported validator after the client example.

# application_design/03_processing_loops_backpressure_and_shutdown.md (251 lines)
ORDERING: role implementation; PASS; payoff 55/251; the motivating overload failure, bounded-queue carrier, commit-gap trace, and shutdown protocol make the later assembled worker intelligible without delaying it behind unrelated reference material.
EXPLANATION: FAIL; teach-back FAIL (missing: safe ownership transition on rebalance); lines 152–166 can return from revocation with unfinished work, yet lines 140–144 and 192–195 may later commit that revoked partition, contradicting the claimed partition-ownership invariant at lines 203–206.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `examples.audit.md` owns the unsafe executable rebalance/commit behavior and its correction.

# application_design/04_topic_and_partition_design.md (64 lines)
ORDERING: role decision guide; PASS; payoff 5/64; lines 7–10 state a starting topology and the conditions that change it before the detail.
EXPLANATION: FAIL; teach-back FAIL (missing: transition/result for partition sizing and retention/compaction choice); lines 24–29 prescribe sizing from throughput and handler capacity, but no named workload maps values to a partition count or shows the consequences of a changed assumption.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `coverage.audit.md` owns the underdeveloped topic/partition sizing and log-compaction mechanisms.

# application_design/05_schema_registry_and_serialization.md (134 lines)
ORDERING: role implementation; PASS; payoff 5/134; bounded registry inputs, registration commands, and HTTP success/failure signals precede the conceptual explanation.
EXPLANATION: FAIL; teach-back FAIL (missing: end-to-end serializer/deserializer transition and a reproducible restore transition); lines 46–55 explain IDs and versions and lines 105–118 prescribe recovery, but the note never shows bytes produced with an ID, read with a writer schema, or restored into a fresh registry.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `coverage.audit.md` owns insufficient schema-registry integration and recovery depth; `examples.audit.md` records the unavailable registry-dependent commands.
