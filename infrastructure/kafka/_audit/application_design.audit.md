# application_design/README.md (29 lines)
ORDERING: role reference/navigation; n/a; payoff n/a; lines 19–29 describe contract-first progression and its first milestone; named-path prerequisite assembly is assessed separately.
EXPLANATION: n/a; teach-back n/a (missing: none); index rather than mechanism owner.
LESSON: n/a; lesson_quality.audit.md LQ-A00 records the legitimate navigation role.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: reader_paths.audit.md owns the local-broker/environment bridge and stop-point sufficiency.

# application_design/01_event_contracts_and_schema_evolution.md (162 lines)
ORDERING: role implementation; PASS; payoff 69/162; the event, schema and validator form the first bounded result before evolution theory; the compatibility repair is development rather than a late-payoff problem.
EXPLANATION: FAIL; teach-back FAIL (missing: distinct reader/writer evolution transition and same-shape semantic check); lines 75–96 name deployment skew and directions, but 115–119 use one unchanged validator, while 122–126 reject a type change rather than test stable-type business meaning.
LESSON: FAIL; lesson_quality.audit.md LQ-A01 maps the whole promise and proposes a developed deployment matrix, not another definition.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: lesson_quality.audit.md LQ-A01 owns the lesson repair; examples.audit.md owns the misleading compatibility test and missing test filename.

# application_design/02_python_producers_and_consumers.md (118 lines)
ORDERING: role implementation; PASS; payoff 68/118; the complete synchronous path precedes client lifecycle interpretation; the missing prerequisites on an alternative path are separately owned.
EXPLANATION: PASS; teach-back PASS (missing: none within the bounded synchronous-client explanation); lines 76–89 connect enqueue/acknowledgment and effect/checkpoint to failure, and 96–114 explain deployment and shutdown boundaries. This does not certify the runnable claim.
LESSON: PASS; lesson_quality.audit.md LQ-A02 checks all later prescriptions and the explicit lifecycle/reliability continuation.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: One consistent program plus causal prose teaches the synchronous round trip and its limits.
RELATED: examples.audit.md owns the original quick-start payload versus strict-validator mismatch; reader_paths.audit.md owns the root exploration route's late validator dependency. The research handoff records the current AsyncIO producer alternative without declaring the synchronous example obsolete.

# application_design/03_processing_loops_backpressure_and_shutdown.md (251 lines)
ORDERING: role implementation; PASS; payoff 31/251; the overload scenario and concrete unfinished-offset trace motivate the worker before the assembled implementation.
EXPLANATION: FAIL; teach-back FAIL (missing: safe ownership transition and interpretation of combined pending/frontier/assignment state); lines 31–37 explain a dense offset gap, but lines 86–206 require reverse engineering the complete state machine and its revoke/lost/deadline branches.
LESSON: FAIL; lesson_quality.audit.md LQ-A03 supplies staged worker development, interpreted state table and ownership timeline.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: lesson_quality.audit.md LQ-A03 owns whole-worker explanation; examples.audit.md owns the post-revocation commit defect and the deterministic frontier probe for legitimate numeric offset gaps. These executable errors are not recounted here.

# application_design/04_topic_and_partition_design.md (64 lines)
ORDERING: role decision guide; PASS; payoff 7/64; starts with a named order-event design and the criteria for changing it, but later decisions lack development.
EXPLANATION: FAIL; teach-back FAIL (missing: workload-to-partition-count transition and replay-window derivation); lines 26–29 and 39–47 supply recommendations and checklist labels rather than a worked design.
LESSON: FAIL; lesson_quality.audit.md LQ-A04 develops workload, skew, replay and policy choices using one service; it retains the useful access-control contrast and final checklist.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: lesson_quality.audit.md LQ-A04 owns the editorial design repair; coverage.audit.md records topic-sizing and cleanup maturity without duplicating the same explanatory defect.

# application_design/05_schema_registry_and_serialization.md (134 lines)
ORDERING: role implementation; PASS; payoff 25/134; registration is introduced with a bounded schema and request before operational depth; the absent serialized record path is an explanation/development issue.
EXPLANATION: FAIL; teach-back FAIL (missing: serializer/deserializer state transition and reproducible identity-preserving restore); lines 46–59 and 105–118 state the lifecycle without tracing bytes, lookup, reader resolution and recovery.
LESSON: FAIL; lesson_quality.audit.md LQ-A05 develops the full writer-to-replay lifecycle rather than treating successful registration as sufficient.
Summary: 0 critical, 1 high, 1 med, 0 low

FIX-HIGH: A05-GATE — Lines 39–41 call HTTP 200 from the compatibility endpoint a deployment gate, but an incompatible candidate can return a successful HTTP response with is_compatible=false (the note itself shows that body at 96). Require a successful response AND is_compatible=true; distinguish this validation response from successful registration and HTTP409 rejection. Primary evidence: https://docs.confluent.io/platform/current/schema-registry/develop/api.html, Compatibility response schema and all-version endpoint; checked 2026-09-16.
FIX-MED: A05-DELETE — Lines 124–126 say deleting a schema version makes retained data undecodable, then recommend soft deletion without explaining the distinction. Soft deletion retains schema IDs for lookup; permanent deletion removes the underlying metadata. State which deletion threatens fresh decoding and why cached reads are insufficient verification. Primary evidence: https://docs.confluent.io/platform/current/schema-registry/schema-deletion-guidelines.html; checked 2026-09-16.
RELATED: lesson_quality.audit.md LQ-A05 owns the structural lifecycle explanation; coverage.audit.md tracks missing integration/restore depth; examples.audit.md records registry-dependent commands without claiming they were executed during this review.
