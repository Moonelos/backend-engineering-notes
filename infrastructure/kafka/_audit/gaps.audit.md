# reliability/
Suggested new notes: 2
GAP: Durable consumer-effect idempotency — the production path repeatedly depends on a stable `event_id`, but no canonical unit teaches the effect store's unique claim, duplicate lookup/result, crash windows, and offset relationship; this independently changing database/external-effect state warrants a focused implementation note rather than another matrix row.
  SIGNAL: leaned-on
  EVIDENCE: `reliability/01:18–21`, `02:5–11`, and `04:92–98`; cross-reference coverage “Delivery semantics and consumer idempotency.”
GAP: CDC outbox relay — polling and log-based CDC have different actors, state, schemas, failure symptoms, and recovery; keep the polling relay in the existing outbox owner and move a complete insert-only connector/event-router path into its own production unit.
  SIGNAL: learning-bridge
  EVIDENCE: `reliability/04:74–82` collapses both choices into prose, while Debezium documents insert-only outbox changes and aggregate-key routing: https://debezium.io/documentation/reference/transformations/outbox-event-router.html (checked 2026-09-16); cross-reference coverage “Transactional outbox, polling relay, and CDC.”

# operations/
Suggested new notes: 1
GAP: Tiered storage — choosing and operating remote log storage changes the capacity, replay, retention, monitoring, plugin, recovery, and disablement model enough to form a distinct operations boundary.
  SIGNAL: current-landscape
  EVIDENCE: Apache Kafka 4.3 requires an external `RemoteStorageManager` and separate local/total retention controls: https://kafka.apache.org/43/operations/tiered-storage/ (checked 2026-09-16); cross-reference coverage “Tiered storage.”

# application_design/
Suggested new notes: 0
NO-GAPS: Existing owners are the right placement for the topic-sizing carrier, complete Python project setup, safe worker lifecycle, and serializer/restore integration; expand them rather than fragmenting the application path. Cross-reference the corresponding coverage and examples findings.

# fundamentals/
Suggested new notes: 0
NO-GAPS: Existing group and replication deep dives can absorb the coordinator/idempotency bridge, consumer-protocol migration carrier, corrected acknowledgment rule, and ELR transition. Cross-reference `fundamentals.audit.md`.

# ecosystem/
Suggested new notes: 0
NO-GAPS: The decision-level scope has coherent owners; update the existing share-group deep dive with concrete Python-client readiness rather than adding another note.

# /
Suggested new notes: 0
NO-GAPS: Root navigation already exposes the right major paths; sequence and milestone corrections belong in existing route definitions, as recorded in `reader_paths.audit.md`.
