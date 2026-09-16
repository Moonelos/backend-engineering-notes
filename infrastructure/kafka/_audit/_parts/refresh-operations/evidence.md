# Operations refresh evidence — 2026-09-16

Full prose read: operations/README.md and 01–05, plus their existing local report and whole-collection coverage owners. Reader is a programmer proceeding through fundamentals/application/reliability; note that earlier failed instruction remains a path concern, not an excuse to demand duplicated baseline teaching everywhere.

Teaching LESSON counts: 1 PASS (capacity), 4 FAIL (security, incidents, lifecycle, administration), 0 unchecked; README n/a. Local findings: 1 HIGH (O-ACL), 0 other severities. Lesson blocks: 0 new severities; every failure points to an existing coverage-owned root cause and supplies its concrete editorial plan. Do not count each zero-summary failed lesson as a clean note.

Ownership corrections: old security local assembly HIGH and rotation MED duplicate coverage's Security and multitenancy finding; old observability local validation HIGH duplicates coverage's incident finding. Removed locally, retained as RELATED. The new O-ACL is distinct existing-claim correctness: topic fetch permission is not bound to a consumer group's identity.

Primary pages opened and checked 2026-09-16:

- https://kafka.apache.org/43/security/authorization-and-acls/ — protocol/resource table separates FETCH Topic Read, JOIN_GROUP Group Read, and offset commit's topic/group checks. Supports O-ACL; examples requesting other group participation must distinguish join/commit denial from independent fetch permission. This is not a demand to disable manual assignment.
- https://kafka.apache.org/43/operations/basic-kafka-operations/ — resource lifecycle, reassignment generate/execute/verify distinctions and position reset behavior. Supports operation-specific learning obligations; not a substitute for local teaching.
- https://kafka.apache.org/43/getting-started/upgrade/ — current supported transition and feature-state boundaries; parent can reconcile its more detailed current-landscape research. No actual broker upgrade was performed.

Checks and limitations: capacity arithmetic checked directly: 72 GB / 1800 s = 40 MB/s additional recovery load; (40+20)/4 = 15 partitions; 20×604800×3 ≈36.3 TB replicated storage. The subsequent 30% allowance and 70% disk ceiling are separate explicit margins, not silently treated as one. Estimates assume measured rates, workload distribution and broker limits; those invalidating assumptions are actually taught. Security/admin live examples were not executed by this worker. Alert syntax or execution ownership remains with the examples owner; no new claim of verification.

Transfer candidates: capacity PASS for halving catch-up time while holding backlog/handler rate fixed: required drain rate doubles from 40 to 80 MB/s, so total 100 MB/s requires 25 partitions under the same assumptions. Security policy transfer FAIL for the exact group-as-data-boundary claim until O-ACL corrected. Lifecycle upgrade transition FAIL because 18–20 does not supply binary/feature intermediate states. Administration retention reversal PASS using 32–67; generalizing that reversal to partition expansion FAIL as an operational capability, since the warning names the asymmetry without teaching its plan.

The regional timeline is usefully developed, but an eventual rewrite should label source versus target record coordinates explicitly so it does not imply every mirroring tool preserves numeric offsets. This is a precision recommendation here, not a researched new severity or forced rewrite of the otherwise useful DR trace.
