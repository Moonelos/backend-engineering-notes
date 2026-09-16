# operations/README.md (20 lines)
ORDERING: role reference/navigation; n/a; payoff n/a; lines 9–20 give the lookup map, milestone, managed-service stop point, and continuation.
EXPLANATION: n/a; teach-back n/a (missing: none); this is a section index.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The index states concrete outcomes without claiming to teach their mechanisms itself.

# operations/01_security_and_multitenancy.md (86 lines)
ORDERING: role implementation; FAIL; payoff absent/86; safe client and ACL fragments are present, but no composed positive/negative producer-consumer run produces the stated authorization results.
EXPLANATION: PASS; teach-back PASS (missing: none); lines 5–73 distinguish TLS, identity, and authorization and map named principals/actions/resources to allowed and denied decisions.
Summary: 0 critical, 1 high, 1 med, 0 low

FIX-HIGH: Add the smallest composed verification with bounded broker/admin/CA/credential inputs, one actual produce, one `billing-v1` consume, two denied operations, and exact success/authorization-failure output. Preserve the current verified-TLS and environment-secret choices.

FIX-MED: Line 17 prescribes overlapping credential rotation without a rotation state transition, verification, or rollback. Show a second principal/credential with temporarily duplicated least-privilege ACLs and the old-credential rejection signal.

# operations/02_capacity_planning_and_performance.md (70 lines)
ORDERING: role decision guide; PASS; payoff 26/70; named measured inputs lead to a changed recommendation from 5 to 15 partitions before hardening detail.
EXPLANATION: PASS; teach-back PASS (missing: none); the arithmetic, failure headroom, invalidating assumptions, load-test signal, and hot-key boundary are all reconstructable.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The sizing carrier is internally consistent and demonstrates why recovery capacity, not steady state, dominates.

# operations/03_observability_and_incident_response.md (93 lines)
ORDERING: role implementation; FAIL; payoff absent/93; the YAML parses, but no rule-validation/reload, metric fixture, slow-handler injection, or observed firing output is provided.
EXPLANATION: FAIL; teach-back PASS for correlated freshness diagnosis (missing: none), but coordinator/controller detection remains only a triage-list mention with no signal or recovery mapping.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: Add exact rule validation/reload steps, bounded metric or fault inputs, observed pending/firing labels, and the separate `absent()` alert already required by lines 67–68.

RELATED: `coverage.audit.md` owns missing coordinator/controller incident depth.

# operations/04_deployment_upgrades_and_disaster_recovery.md (73 lines)
ORDERING: role deep dive; PASS; payoff 5/73; RTO/RPO/authority precede topology and the cross-region trace makes duplicates and loss visible.
EXPLANATION: FAIL; teach-back FAIL for upgrades (missing: owned state, transition/result, rollback cutoff, first failure); regional recovery is demonstrated, but upgrades are only a generic checklist at lines 18–20.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `coverage.audit.md` owns Kafka 4.3 rolling upgrade/finalization depth. Apache's upgrade guide requires broker-by-broker verification before the feature/metadata upgrade and identifies the downgrade boundary: https://kafka.apache.org/43/getting-started/upgrade/ (checked 2026-09-16).

# operations/05_configuration_and_topic_administration.md (108 lines)
ORDERING: role reference with implementation-led common path; PASS; payoff 5/108; topic creation/effective-value inspection and override precedence appear immediately.
EXPLANATION: FAIL; teach-back PASS for retention override and rollback (missing: none), but partition expansion, reassignment, quotas, and deletion remain one-line rules rather than operable procedures.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: `coverage.audit.md` owns underdeveloped administration beyond retention; `examples.audit.md` records live mutation as not run.
