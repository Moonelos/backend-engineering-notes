# Foundations refresh evidence — 2026-09-16

Scope: full prose of fundamentals/README.md and 01–05, root README, operations/05; updated reviewer SKILL.md and lesson-design, report, learning-curve, prose, example-selection, curriculum-research and coverage references. Audience is a programmer without Kafka knowledge. Original notes were not modified. No earlier calibration verdict was used as authority.

## Results and ownership

- Teaching lessons: 1 PASS (01), 4 FAIL (02–05), 0 unchecked; README n/a.
- Local report findings: 1 HIGH (F-ACK), 1 MED (F-CLI); no critical/low.
- Lesson-quality findings: 4 HIGH (LQ-F02..F05), no other severities. These are one editorial root cause per whole chapter, not counts of every weak subsection.
- Former 02 first-use group HIGH is absorbed in LQ-F02. Former 04 coordinator/idempotency HIGHs are absorbed in LQ-F04. Former 04 protocol rollout MED is removed locally because coverage already owns it.
- Former 05 ELR HIGH is not retained as a false-claim allegation. “Eligible follower” never explicitly excludes ELR. The missing current election model needs a coverage-owned correction. Parent should change the existing replication coverage block from only RELATED to its own proportionate missing-eligibility finding, preserving the local F-ACK reference.
- Existing coverage should stop claiming all 03 skew/expansion remedies are demonstrated. Basic key affinity is demonstrated; logical-bucket/migration advice is not. Similarly 02's narrow retained-log model can remain demonstrated while the complete lesson fails.
- No automatic requirement to merge files: the substantive repair is to join/develop dependent sections and explicitly place advanced tactics. The five-file macro-sequence is defensible; its current miniature sections are not sufficient evidence of developed lessons.

## Source checks

Checked 2026-09-16; opened primary pages rather than relying on search snippets:

- https://raw.githubusercontent.com/apache/kafka/4.3.1/tools/src/main/java/org/apache/kafka/tools/consumer/ConsoleConsumerOptions.java — current tagged source marks `--property` deprecated and supports `--formatter-property`; confirms scoped warning, not broken-command claim. Docker not rerun by this worker.
- https://kafka.apache.org/43/configuration/producer-configs/ — current ISR acknowledgment behavior and key-aware versus alternative partitioners. The rewrite's modulo example is explicitly illustrative, not a claim about every Kafka client.
- https://kafka.apache.org/43/configuration/topic-configs/ — minimum ISR and cleanup configuration reference.
- https://kafka.apache.org/43/operations/eligible-leader-replicas/ — ELR default for new clusters since 4.1 and election eligibility beyond current ISR. Preserve as missing coverage; avoid calling every last-known-leader fallback intrinsically unclean.
- https://kafka.apache.org/43/operations/consumer-rebalance-protocol/ — server protocol support versus client opt-in and broker-driven assignment; operations/05 does not supply the rollout it is said to own.
- https://kafka.apache.org/43/design/design/ — primary retained-log/replication/compaction reference supporting the independent expected foundational capabilities.

Research limitation: this worker checked bounded foundational claims, not the whole release landscape or executable examples. Global owners reconcile current-landscape coverage and reproduction status.

## Transfer checks for parent path integration

1. After 01–02, core retained-log transfer PASS: billing commits next=1 in P1 while analytics has its own next=0; reading/committing does not erase record 0, so analytics can read it. Earlier evidence: 01:38–66, 02:7–28. This local pass does not clear LQ-F02's full cleanup/lag/recovery development failure.
2. After 03, elementary changed-key transfer PASS: placing one entity on two independent partitions removes its common ordering sequence, supported by 03:7–22,34–42. Advanced prescribed remedy transfer FAIL: given a hot ordered ledger account and partition expansion, “stable logical bucket” cannot be derived as a safe mapping/handoff from 03:50–55. The missing indirection and cutover must not be invented in the answer.
3. After 04, crash-after-effect/before-commit duplicate trace is reconstructable at 32–41; safe bounded-worker transfer FAIL: if offset 9 finishes before 8, the note says not to commit past unfinished work but supplies no working state or decision procedure connecting in-flight work, next-offset checkpoints and reassignment. The report's acceptance task describes the required repaired lesson, not proof that present prose teaches it.
4. After 05, full-ISR versus minimum-floor transfer FAIL on existing prose at 32–34. Source-correct resolution needs the local technical repair and subsequent worked failure trace; external docs are not teaching evidence on the note's behalf.
