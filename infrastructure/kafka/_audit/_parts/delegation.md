# Kafka audit delegation ledger

Scope: learner-facing Markdown under `infrastructure/kafka`, excluding `_audit/` and `_meta/`.
Audience and version assumptions are taken from the collection root README and independently checked by the coordinator.

| Package | Topic/files | Dependencies | Assigned worker | Allowed writes | Expected output | Status |
|---|---|---|---|---|---|---|
| fundamentals | `fundamentals/01`–`05` plus section README | Root README and any explicitly linked earlier owner | fundamentals reviewer | `_audit/_parts/fundamentals/review.md` only | Full-prose per-note verdicts, path-local issues, mechanisms, executable claims | accepted |
| reliability | `reliability/01`–`05` plus section README | Root/fundamentals may be read as prerequisites | reliability reviewer | `_audit/_parts/reliability/review.md` only | Full-prose per-note verdicts, cross-topic dependencies, mechanisms, executable claims | accepted |
| operations | `operations/01`–`05` plus section README | Root/fundamentals/reliability may be read as prerequisites | operations reviewer | `_audit/_parts/operations/review.md` only | Full-prose per-note verdicts, production checks, executable claims | accepted |
| application-design | `application_design/01`–`05` plus section README | Root/fundamentals may be read as prerequisites | coordinator | Canonical audit reports | Full-prose per-note verdicts and cross-collection reconciliation | accepted |
| ecosystem | `ecosystem/01`–`04` plus section README | Root and linked canonical owners may be read | coordinator | Canonical audit reports | Full-prose per-note verdicts and current-landscape reconciliation | accepted |
| collection-wide | All in-scope notes and named paths | All packages | coordinator | Canonical `_audit/*.audit.md` reports | Independent curriculum, reader journey/transfer, coverage/gaps, examples, metrics, validation | accepted |

Shared notes are read-only. Review fragments are evidence inputs, not final report ownership.
