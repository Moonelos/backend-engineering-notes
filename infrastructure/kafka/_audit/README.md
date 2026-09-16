# Kafka audit — 2026-09-16 refresh

**Overall learning verdict: FAIL for the requested beginner-to-production course.**
The collection contains useful traces and real introductory examples, but many chapters stop
developing the explanation after their opening and turn into recommendations the learner cannot
yet apply. Successful first-event execution does not establish the rest of the learning journey.

Start with the [whole-lesson review and editorial plan](lesson_quality.audit.md), especially
LQ-G00 and LQ-F02–F05. Each teaching unit has a development map, a separate lesson verdict,
concrete evidence and—where needed—a proposed sequence, content mapping, actual replacement
passage and acceptance task. Short successful lessons retain their PASS; file length and diagram
counts are not grading criteria.

## Repair priorities

1. Develop the foundations into connected reasoning: two independent readers, positions versus
   stored history, cleanup/recovery, ordering choices, group handoffs, replicated data and controller
   majority. Preserve useful depth and join related sections; adding more files is not the default.
2. Repair the assembled application path: project setup, contract before client, quickstart payload
   compatibility, truthful compatibility tests, and ownership/offset-gap-safe worker state.
3. Build the missing reliability implementations and controlled crash harness. Separate producer
   retry identity, Kafka transaction scope and durable business-effect deduplication.
4. Complete operational procedures: independent topic/group authorization, incident diagnosis,
   version finalization and rollback, registry recovery, and state-moving administration.
5. Correct ecosystem time semantics and state client-specific share-group limitations explicitly.

## Evidence and limits

- [Per-note fundamentals review](fundamentals.audit.md) distinguishes local technical defects from
  chapter-wide teaching repairs. The other folder reports follow the same ownership rule.
- [Reader paths](reader_paths.audit.md) checks actual prerequisite order and changed-condition
  reasoning, without borrowing knowledge from later notes.
- [Curriculum](curriculum.audit.md), [coverage](coverage.audit.md), and [placement proposals](gaps.audit.md)
  distinguish absent mechanisms, insufficient depth and optional new-file boundaries.
- [Executable claims](examples.audit.md) separates exact fresh reproduction from component probes,
  missing artifacts and unavailable service-dependent drills. Detailed evidence is under
  [_parts/refresh-global](_parts/refresh-global/README.md).
- [Metrics](metrics.audit.md) reports the reconciled denominators and single-owner severity counts.

This refresh reread all learner-facing Kafka notes, checked primary sources and used topic reviewers
plus a coordinator's complete-path review. It did not modify the notes. Broker/region failures,
secured-cluster administration, registry restore and production-shaped load were not executed.
The report validator checks report completeness and coherence of required fields; it does not
prove instructional quality or replace an independent review after rewriting.
