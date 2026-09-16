# Reliability refresh evidence — 2026-09-16

Scope: All six reliability Markdown files read in full; root named paths, fundamentals 02–04, application Python client and processing loop, ecosystem Connect prerequisite inspected. No note edits, service starts, broker mutations, or execution claims performed by this worker.

Local findings: 0 critical, 2 high, 1 med, 0 low. Structural lesson findings: 0 critical, 2 high, 1 med, 0 low. Teaching notes: LESSON 1/5 PASS, 4/5 FAIL; README n/a. ORDERING 2/5 PASS; EXPLANATION 1/5 PASS. Do not add RELATED cross-references to severity totals.

## Sources read

- https://kafka.apache.org/43/design/design/ — Message Delivery Semantics and Using Transactions: checkpoint-before-durable-output crash creates omitted work; effect-before-checkpoint crash allows repeat; consumed offsets and Kafka output can share a transaction. Supports R-C01 and chapter-boundary interpretation.
- https://kafka.apache.org/43/generated/consumer_config.html — isolation.level: open transactions can withhold later records from read_committed consumers. Supports R-C02.
- https://kafka.apache.org/43/javadoc/org/apache/kafka/clients/producer/KafkaProducer.html — initTransactions resolves previous same-ID transactional state; sendOffsetsToTransaction uses next-to-consume position. Python naming in the audit is init_transactions; source describes broker-level lifecycle through Java API. Supports R-C02 and R-C01's offset convention.
- https://debezium.io/documentation/reference/transformations/outbox-event-router.html — distinct unique event identity and aggregate routing key. Supports R-C04. Merely fixing routing does not enforce concurrent relay publication order.

All four opened and relevant sections inspected on 2026-09-16. This is scoped technical verification, not a claim to complete current-landscape research or to executing the examples.

## Transfer for root synthesis

Production-hardening checkpoint after reliability/02: change transaction output from Kafka billing.commands to a card API invoked before commit. Existing §2 supports the negative conclusion that Kafka abort cannot undo the charge. TRANSFER PASS for recognizing the scope boundary. TRANSFER FAIL for the promised constructive outcome “select an idempotency boundary” that actually prevents duplicate effects: stable event IDs and a durable local state transition are named, but the note does not teach the atomic claim/effect mechanism or an API provider protocol. Do not let a correct negative answer imply that safe implementation has been taught. Canonical missing capability remains coverage; LQ-R02 owns the disconnected presentation of three protections.

Reliability recovery checkpoint after 03: same-order creation at 8 enters retry and cancellation at 9 proceeds. Text supports that their effects can reorder. TRANSFER PASS for identifying this trade-off. Asking the reader how a next_attempt_at timestamp survives restart as a delayed attempt, or where to commit during source-to-retry handoff, needs missing actors and state. TRANSFER FAIL for implemented controlled recovery, cross-reference coverage and LQ-R03.

Outbox checkpoint after 04: broker acknowledges, relay crashes before published_at update, then another relay claims the row. Text explicitly supports possible repeat publication with no vanished database intent; TRANSFER PASS for this polling recovery window. A changed scenario with two events for the same order exposes R-C04; event_id as routing key does not preserve required partition co-location. CDC position loss cannot be solved from the note's one-sentence definition.

Test-design checkpoint after 05: a unit test raises inside the parent test process versus a synchronized child-process kill after durable effect. TRANSFER PASS for choosing the second to expose process-state loss and replay, with durable effect count and input checkpoint as separate assertions. This does not verify the absent harness.

## Proposed global changes

- Add canonical LQ-R00–R05 blocks from lesson.md. Keep 01's central fact error locally owned rather than inventing a duplicate structural severity.
- Preserve existing missing idempotency/retry/CDC/harness coverage findings. Replace any inferred EXPLANATION PASS from one local transaction trace with the complete-scope verdict.
- Keep the path's conceptual early payoff separate from false runnable milestone. Reliability 05 can teach testing well and still fail its executable promise.
- Curriculum/execution owners should retain assembly/operationalization limits; this worker did not reproduce or invalidate execution statuses independently.
