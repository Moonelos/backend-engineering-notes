# Independent execution inventory review — 2026-09-16

Read the current examples report, fresh probe JSON/README, and all 24 teaching notes (reliability and its application/foundation prerequisites were read during the earlier bounded review). Read-only inspection; no service start, execution probe, or mutation performed here.

## Evidence reconciliation

- Fresh setup/roundtrip/replay JSON supports the three exact VERIFIED claims, including transient setup warnings and CLI deprecation. Cleanup is supported by the parent's README but has no separate JSON; this is evidence granularity, not a contradiction.
- local-probes.json confirms fresh dependency setup failures for contract, compatibility, Python client, and smoke; exact jq successes; and the Frontier gap failure. quickstart-contract.json supports the supplemental retained-payload incompatibility. replay-command.json supports exit 127. Keep these claims/statuses.
- Contract `contract: valid` and compatibility `2 passed` supplemental results have no fresh JSON here. They may be valid prior-session results, but label them explicitly as prior execution retained against unchanged source, with evidence location if available. Do not describe them as newly reproduced. The actual fresh dependency failures and static two-identical-validators defect suffice without those historical passes.
- Schema Registry `endpoint connection failed`, YAML/AST/shell parsing, and uv version 0.8.13 are not established by these fresh files. Preserve only with explicit prior-evidence provenance or rewrite as current environmental/static limitations. In particular do not infer an attempted HTTP request from simply having no registry.
- ACL diagnosis is `PARTIAL` despite `Observed: inspection only`. Change to NOT-RUN unless an actual smaller executed component has evidence. Static recognition of missing bootstrap/auth arguments is still valid.
- Syntax-only Python/YAML checks may remain explicitly qualified partial static checks, but must not inflate reproduced-runtime counts. No source claim is VERIFIED from syntax alone.

## Missing execution/verification inventory entries

These are explicit verification instructions or promised observation probes. Add NOT-RUN rows with the actual missing environment and no invented command/output. Existing coverage, local, or lesson findings normally own the defects, so do not add a new severity automatically.

| Source | Distinct unlisted claim | Recommended boundary |
|---|---|---|
| fundamentals/03 lines 61–63 | sample one entity and inspect partition/business ordering | May extend existing cross-client placement entry, but distinguish ordering from equality of placement |
| application_design/05 lines 95–96 | submit breaking candidate to compatibility endpoint and obtain is_compatible=false | Existing request entry currently describes only additive candidate; explicitly include both expected results |
| application_design/05 lines 105–118 | registry restore decodes oldest/newest retained IDs; registry-unavailable client behavior | NOT-RUN; no registry restore/serializer fixture; cross-reference coverage |
| reliability/03 lines 69–71 | inject invalid event → DLT provenance → corrected replay gives one effect | Distinct from shell transport of one already-existing envelope; NOT-RUN missing recovery workers/effect store |
| reliability/04 lines 97–98 | crash after DB commit before publish, then after publish; eventual emission and one effect | DB-write entry does not cover relay crash recovery; NOT-RUN missing relay/fault harness |
| operations/01 lines 60–70 | positive produce/read plus denied unrelated-topic write and wrong-group read | NOT-RUN; config and ACL mutation are not authorization tests |
| operations/02 lines 50–54 | load/burst catch-up and one-broker-loss capacity bounds | NOT-RUN; no production-shaped fixture/multi-broker drill; do not mark the sizing arithmetic broken because no load test ran |
| operations/03 lines 75–77 | injected slow handler fires correct alert and enables diagnosis | NOT-RUN; YAML parsing is not fault injection or alert firing |
| operations/04 lines 53–56 | broker/region game day achieves RTO/RPO and idempotent resume | NOT-RUN; conceptual timestamp trace is separate from executing failover |
| ecosystem/01 lines 21–23 | stop/restart Connect task, retain checkpoint/no loss; reject unauthorized administration | NOT-RUN; no connector/worker/security fixture |
| ecosystem/02 lines 43–44 | feed on-time/late records, restart, inspect window updates | NOT-RUN; engine/application unspecified; conceptual table remains non-executable |
| ecosystem/03 lines 38–39 | kill record-holding worker and observe redelivery vs accepted record | NOT-RUN; no selected supported client/worker fixture |

Operations/05 canary, before/after describe, and rollback verification can stay in its existing combined alteration entry, provided Observed explicitly says those stages were not executed. Broad discussion of quotas/reassignment/deletion does not by itself promise executable commands for every named operation.

## Excerpts, design guidance, and duplicate ownership

- reliability/02 API text trace, reliability/05 crash text trace, ecosystem/02 window table, ecosystem/03 share-lock table, operations/04 regional timeline, and fundamentals conceptual diagrams are explanatory EXCERPT material. Their separate prose instructions to execute kill/restart/feed/game-day tests create NOT-RUN verification claims; do not call the text traces themselves broken programs.
- reliability/05 `reusable suites` is explicitly suite-design explanation, not a supplied runnable suite. Its existing FIX-MED “label this as design guidance” is unnecessary: it already describes fixture layers and which suite runs when. Remove that severity; omit from executable denominator or retain EXCERPT/design inventory. The actual missing smoke/crash harness remains material.
- Missing shared process-kill harness is currently counted in reliability README, reliability/01 crash windows, reliability/02 transaction milestone, and reliability/05 child-process harness. Consolidate common harness absence at reliability/05; the README and 01 should RELATED that owner. Keep transaction-specific processor/config/abort/isolation omissions as a separate substantive requirement if not already coverage-owned. Do not count identical absent worker/kill setup repeatedly.
- reliability README's premature execution milestone is also reader-path-owned. Its examples entry should record NOT-RUN and RELATED rather than repeat the same global milestone FIX-HIGH.
- Fresh setup/project absence is repeated across contract/client/smoke claims. Keep each distinct failed command in the inventory; report shared project setup once, retaining separate file/import/schema-test defects where their repairs differ.
- Do not add runnable claims for application_design/04 topic design, ecosystem/04 architecture selection, or foundations/02 offset interpretation: their stated payoffs are conceptual decisions, not executable outputs.

No unsupported fresh VERIFIED status found. Main remaining issues are incomplete verification inventory, ambiguous prior-execution provenance, one inspection-only PARTIAL, and repeated ownership of the absent harness.
