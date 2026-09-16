# Kafka Reliability

> Derive guarantees from crash points, then design retries and external effects around them.

---

## Contents

| File | Role | Reader outcome |
|---|---|---|
| [Delivery semantics](01_delivery_semantics.md) | Foundation | Derive at-most- and at-least-once behavior |
| [Durable consumer-effect idempotency](02_durable_consumer_effect_idempotency.md) | Implementation | Collapse repeated database or API effects by stable identity |
| [Idempotence, transactions, exactly once](02_idempotence_transactions_and_exactly_once.md) | Deep dive | Bound each guarantee accurately |
| [Retries, dead letters, replay](03_retries_dead_letters_and_replay.md) | Implementation | Recover poison and transient failures safely |
| [Polling transactional outbox](04_transactional_outbox_and_cdc.md) | Implementation | Eliminate a database/Kafka dual-write gap with a polling relay |
| [CDC outbox relay](06_cdc_outbox_relay.md) | Implementation | Operate an insert-only database-log relay |
| [Testing Kafka services](05_testing_kafka_services.md) | Implementation | Prove crash, replay, compatibility, and capacity guarantees |

---

## Reading Order

**Working result by entry 2**: classify a crash trace and run a durable duplicate-collapse test.

1. **Do:** trace delivery semantics.
2. **Build:** run the durable consumer-effect idempotency example.
3. **Branch:** use Kafka transactions when input, output, and checkpoint all remain in Kafka; use a
   polling outbox when the authoritative change is in a database.
4. **Test:** use the integration harness to kill the process at the chosen guarantee boundary.
5. **Recover:** add retry scheduling, dead-letter evidence, and controlled replay.
6. **Optional CDC branch:** replace polling with a database-log connector only when its throughput
   or ownership model justifies the extra checkpoint and recovery procedure.

**Implementation milestone:** the checked-in test suite kills a real child process after its durable
effect and proves that restart returns the first result and advances the Kafka position. The Kafka
transaction branch separately proves one committed output after an open-transaction restart.
**Stop here if** duplicate effects are prevented and replay is tested. Continue to
[Operations](../operations/README.md) for platform failure and capacity.
