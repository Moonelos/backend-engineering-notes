# Application audit refresh — 2026-09-16

Scope: fully read application_design 01–05 and README, all fundamentals prose, root README named paths, and the previous application/coverage/example findings. Audience: Python/HTTP programmer with only actually taught Kafka prerequisites. No notes edited, no Kafka/registry services mutated, no executable results asserted by this worker.

## Verdicts and ownership

- Five teaching units: one LESSON PASS (02), four FAIL (01/03/04/05), zero unchecked; README n/a.
- Structural findings: LQ-A01 MED; LQ-A03, LQ-A04, LQ-A05 HIGH. These are in lesson.md for single-owner aggregation.
- Local findings: A05-GATE HIGH; A05-DELETE MED. All other per-file severities zero to avoid counting related systemic/executable defects twice.
- ORDERING PASS for the five teaching notes is compatible with LESSON FAIL: the notes mostly begin promptly, but beginning promptly does not develop the later promises.
- Existing event compatibility test defect, quick-start/client payload mismatch, worker ownership defect and frontier gap probe remain examples-owned. Parent executes isolated probes and preserves execution provenance.
- Existing coverage topic-design and schema-registry findings overlap LQ-A04/A05. Keep actual maturity evidence but replace same-root coverage severity with RELATED to lesson quality; retain distinct missing mechanisms as separate coverage findings where warranted.

## Primary-source research

Checked 2026-09-16:

1. https://docs.confluent.io/platform/current/schema-registry/develop/api.html — inspected compatibility response and all-version endpoint. is_compatible is the decision; transitive policy tests historical versions. Used for A05-GATE and to confirm the documented endpoint shape, not as proof the requests ran.
2. https://docs.confluent.io/platform/current/schema-registry/schema-deletion-guidelines.html — inspected soft/hard deletion distinction. Soft deletion preserves ID lookup; permanent deletion removes metadata. Supports A05-DELETE.
3. https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html — inspected Consumer subscribe/on_lost and client API. When on_lost is absent, lost ownership can go to on_revoke; commits may already fail after ownership loss. Supports the existing worker executable finding, without claiming every such commit necessarily succeeds or causes data loss.
4. https://docs.confluent.io/kafka-clients/python/current/overview.html — checked maintained client overview as context for the synchronous example.
5. https://github.com/confluentinc/confluent-kafka-python — current maintained README documents AIOProducer, awaitable delivery and lifecycle, including batching/header limitations. The synchronous classes remain valid; 02 section 3 should identify its synchronous API scope and link the current async producer option if claiming broad FastAPI integration guidance. This is a current-landscape curriculum item, not a demand to replace the first synchronous tutorial or proof that all consumers are natively asynchronous.

Research limits: no live registry, no restore reproduction, no asynchronous service reproduction by this worker. Source inspection verifies described API distinctions, not local environment execution.

## Changed-condition checkpoints for path owner

1. After application 01, change R2 so coupon_code is required while retained R1 data has none. TRANSFER PASS for this narrow prediction: lines 29/38 show required fields, and 81 plus 88 explain optional additions and new-reader/old-data direction, so the reader can predict rejection. This does not prove the wider old/new deployment lesson is developed; LQ-A01 remains a separate whole-lesson FAIL and the unchanged-validator test remains examples-owned. Do not fail a solvable question merely because no exercise heading exists.
2. After application 02, crash after print but before commit. TRANSFER PASS for duplicate print/replay reasoning from lines 85–89 and fundamentals checkpoint model. Real external side effects explicitly require the reliability continuation; passing this probe does not certify the original runnable composition.
3. After application 03, allow completion 12→10, then lose partition before 11 finishes. Dense-sequence frontier result 11 is locally supported, but ownership-safe late-completion behavior is not developed and current code contradicts the promise. TRANSFER FAIL; LQ-A03 and examples own separate teaching/executable remedies.
4. After application 04, measured 200 records/s per worker, 800 total, 600 on one key. TRANSFER PASS for rejecting “four workers suffice”: earlier group/key basics establish that the 600-record/s key remains on one owner. That narrow prediction does not establish an operational sizing/headroom/replay design; LQ-A04 still owns the missing developed decision process. Do not use this limited probe as evidence for all advertised design promises.
5. After application 05, restore same schema under a new ID while one client still has the old schema cached. The note explains changed-ID danger but never develops cache versus fresh lookup or proves the restore transition. TRANSFER FAIL for operationalized recovery; LQ-A05.

The application README remains an index. Its environment/prerequisite gaps and claim that internal harmless duplicates suffice as a stop point should be reconciled by the whole-path owner against the actual runtime and failure guarantees.
