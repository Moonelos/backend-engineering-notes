# Audit refresh — 2026-09-16

Audience: programmer with Python/HTTP basics, no Kafka expertise; beginner through production.
All notes are read-only. Reviewer: `.agents/skills/note-reviewer` in repository root.
Five semantic topic batches (5/5/5/5/4 notes), dispatched in bounded waves across three workers.
Coordinator owns all final global reports and reconciles structural findings across batches.

| Package | Scope and dependencies | Worker | Allowed writes / outputs | Status |
|---|---|---|---|---|
| foundations | fundamentals 01–05 + README; read root | foundation_audit | fundamentals.audit.md; _parts/refresh-foundations/ | accepted |
| application | application_design 01–05 + README; read foundations and referenced reliability | application_audit | application_design.audit.md; _parts/refresh-application/ | accepted |
| reliability | reliability 01–05 + README; read foundations/application prerequisites | reliability_audit | reliability.audit.md; _parts/refresh-reliability/ | accepted |
| operations | operations 01–05 + README; read foundation/reliability | foundation_audit (second batch) | operations.audit.md; _parts/refresh-operations/ | accepted |
| ecosystem | ecosystem 01–04 + README; read prerequisites | application_audit (second batch) | ecosystem.audit.md; _parts/refresh-ecosystem/ | accepted |
| global | full prose of all paths; curriculum research, coverage/gaps, execution inventory, lesson quality, root and metrics | coordinator | global canonical reports; _parts/refresh-global/ | accepted |

Workers return per-note verdicts, full lesson blocks with development maps and concrete repairs,
primary-source evidence, and proposed coverage corrections. No worker edits notes or shared reports.
Coordinator accepts by reading source and fragments, removes duplicate findings, aggregates last.

## Acceptance evidence

Coordinator read all 30 learner-facing Markdown files and all merged lesson fragments. Each of the
24 teaching notes and 6 indexes is represented; the collection-wide plan is separately assessed.
Global reports reconcile development maps, primary sources and actual executable probes.
An independent execution-inventory pass by reliability_audit identified omitted probes and removed
unsupported historical execution assertions; its accepted corrections are in examples.audit.md.

Validation: updated reviewer report validator STRUCTURE PASS; scoped git diff --check PASS;
SHA-256 comparison confirms all 30 original source files unchanged. Structure validation does not
verify pedagogical judgment. The only service created for reproduction, kafka-notes, was stopped
and its absence confirmed; unrelated containers were not modified.
