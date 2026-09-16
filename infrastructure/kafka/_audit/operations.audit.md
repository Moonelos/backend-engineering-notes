# operations/README.md (20 lines)
ORDERING: role reference/navigation; n/a; payoff n/a; lines 9–20 map outcomes, the first milestone and the managed-provider continuation.
EXPLANATION: n/a; teach-back n/a (missing: none); path index.
LESSON: n/a; lesson_quality.audit.md LQ-O00; navigation role.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: A usable route; individual chapters must still fulfill the advertised outcomes.

# operations/01_security_and_multitenancy.md (86 lines)
ORDERING: role implementation; FAIL; payoff absent/86 for a composed verified policy; bounded client and ACL artifacts appear at 19–57, but their setup and positive/negative execution are not assembled.
EXPLANATION: FAIL; teach-back PASS for TLS versus identity versus ACL intent; FAIL for the full operational promise (missing: composed allow/deny observation, credential transition, isolation decision); topic/group binding is also overstated at 59–60.
LESSON: FAIL; lesson_quality.audit.md LQ-O01; useful artifacts do not develop all of the advertised security lifecycle.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: O-ACL — Lines 59–60 say topic reading is allowed “only while joining billing-v1.” Topic Read and Group Read are separate permissions; the latter restricts group operations, not every possible fetch of authorized topic data. Rewrite the mapping as independent topic-fetch and group-membership/checkpoint authorization, and show an authorized topic fetch versus a denied join to another group. Do not teach group IDs as a binding data-isolation boundary. [Kafka 4.3 authorization API/resource table](https://kafka.apache.org/43/security/authorization-and-acls/), checked 2026-09-16, lists FETCH→Topic Read and JOIN_GROUP→Group Read separately.
RELATED: coverage.audit.md, Security and multitenancy, owns the absent composed verification/rotation/isolation depth. The former local assembly HIGH and rotation MED duplicated that coverage root cause and are not counted again. examples.audit.md owns live reproduction status.

# operations/02_capacity_planning_and_performance.md (70 lines)
ORDERING: role decision guide; PASS; payoff 26/70; measured steady-state limits give way to the stronger recovery constraint before tuning detail.
EXPLANATION: PASS; teach-back PASS (missing: none); lines 7–37 expose assumptions, arithmetic, actors, changed recommendation, and limits; 43–66 define validation and the hot-key boundary.
LESSON: PASS; lesson_quality.audit.md LQ-O02; the complete estimate is developed through a single workload and changed constraint.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: Storage, partition, network and recovery arithmetic are connected to a named envelope. The decision-guide role does not require implementing a benchmark framework here; the estimate is explicitly provisional until measured.

# operations/03_observability_and_incident_response.md (93 lines)
ORDERING: role implementation; FAIL; payoff absent/93 for observed incident handling; the first complete carrier at 32–62 is alert configuration, not a validated/reloaded/fired rule or diagnosis episode.
EXPLANATION: FAIL; teach-back PASS for the two-signal alert conjunction and missing-series warning; FAIL across promised incident detection (missing: coordinator/controller signal-to-action sequence, executable observation, and a developed comparison of possible causes).
LESSON: FAIL; lesson_quality.audit.md LQ-O03; the prose explains the sample rules but does not fulfill the full incident-response lesson.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: coverage.audit.md, Observability and incident response, owns rule validation/injection, absent-series implementation and missing coordinator/controller branches. The old local HIGH counted part of this same defect twice. examples.audit.md owns reproduction status.

# operations/04_deployment_upgrades_and_disaster_recovery.md (73 lines)
ORDERING: role lifecycle deep dive; FAIL; payoff 46/73 for regional recovery arithmetic; the opening names objectives and upgrade checks but does not develop the upgrade state model before the regional case.
EXPLANATION: FAIL; teach-back PASS for bounded regional lag/replay and RTO reasoning; FAIL for upgrades (missing: binary-versus-feature state, intermediate health gates, abort and downgrade boundary).
LESSON: FAIL; lesson_quality.audit.md LQ-O04; the developed regional trace does not earn the separate upgrade promise advertised by operations/README.md:14.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: coverage.audit.md, Upgrades and regional disaster recovery, owns upgrade depth. The current [Kafka upgrade guide](https://kafka.apache.org/43/getting-started/upgrade/) separates binary rollout from feature changes and version-specific downgrade restrictions (checked 2026-09-16). Preserve the regional recovery trace while developing the other promised capability; do not force generic advice into a Kafka-version-specific procedure.

# operations/05_configuration_and_topic_administration.md (108 lines)
ORDERING: role reference containing substantive procedural teaching; PASS; payoff 49/108 for override-versus-inheritance reasoning; creation and inspection appear first, followed by a fully interpreted before/after example.
EXPLANATION: FAIL; teach-back PASS for retention override and recorded rollback; FAIL for the wider procedures (missing: expansion/migration handoff, reassignment progression, quota canary outcomes and deletion recovery).
LESSON: FAIL; lesson_quality.audit.md LQ-O05; the reference label does not turn its prescriptions at 76–104 into lookup-only content.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: coverage.audit.md, Topic and configuration administration, owns undeveloped procedures beyond retention. examples.audit.md records live operations as not run. [Kafka basic operations](https://kafka.apache.org/43/operations/basic-kafka-operations/), checked 2026-09-16, provides distinct reassignment generate/execute/verify stages; a warning to verify is not a local demonstration of those stages.
