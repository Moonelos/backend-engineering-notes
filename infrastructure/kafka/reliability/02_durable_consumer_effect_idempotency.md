# A Durable Claim Turns Redelivery into the Same Result

> **Who this is for**: engineers whose Kafka consumer changes a database or calls an external API.

## One event, two attempts, one charge

Suppose `evt-101` charges `ord-42`. Attempt 1 completes the charge, then loses partition ownership
before committing its Kafka offset. Attempt 2 must not ask, “Have I seen this in this process?”—the
new process has no such memory. It asks a durable store to claim the stable operation identity.

```text
attempt 1: claim evt-101 → store charged:ord-42 → crash before Kafka commit
attempt 2: claim evt-101 → conflict → return charged:ord-42 → commit Kafka offset
```

The store owns `event_id → result`; Kafka owns the group's next offset. They are not one atomic
transaction, so the safe order is durable claim/effect first and offset commit second. That order
permits redelivery, and the unique claim makes redelivery converge.

## Run the smallest durable transition

From `infrastructure/kafka/examples/python`:

```bash
uv sync --dev
uv run pytest -q tests/test_idempotent_effect.py
```

The implementation in
[`kafka_notes/effect_store.py`](../examples/python/kafka_notes/effect_store.py) starts a SQLite
write transaction, looks up `event_id`, and inserts only when no row exists. The test deliberately
offers a different second result:

```text
first:  apply_once("evt-101", "charge-ok-1") → ("charge-ok-1", created=true)
second: apply_once("evt-101", "charge-ok-2") → ("charge-ok-1", created=false)
```

**Success signal:** `1 passed`. The second attempt returns the first durable result; it does not
overwrite it or apply a second charge.

For PostgreSQL, the same invariant is normally a `PRIMARY KEY` or `UNIQUE` constraint plus an
atomic insert/read transaction. If the external provider supports idempotency keys, send the same
stable operation ID on every retry and persist its returned provider reference. A local “processed”
flag written *before* a non-idempotent provider call can lose the effect; one written *after* the
call still leaves a crash window. In that case the provider must own the unique claim, or the design
needs explicit reconciliation of uncertain outcomes.

## The offset is evidence, not the deduplication lock

An offset identifies one record location. It is a poor business idempotency key when an event can
be copied to a retry topic, restored to another cluster, or republished. Preserve `event_id` through
those moves. Use the topic/partition/offset tuple as provenance for diagnosis, not as the only
logical identity.

Run the broker-backed crash test from the same project after starting the disposable broker:

```bash
uv run pytest -q tests/integration/test_crash_recovery.py
```

The three cases fail before the effect, after the durable effect, and after the offset commit; none
guesses a sleep interval. The middle case restarts with the same group, observes `created=false`,
and commits next offset `1`. Every case queries Kafka's stored group position and requires exactly
one effect row. **Success signal:** `3 passed`.

⚠️ A read-then-insert without a database uniqueness constraint races when two owners overlap.
Both may read “missing” and apply the effect. Make the claim an atomic storage operation.

Do not build an effect store for naturally convergent writes such as replacing a projection row by
stable key. Do use one for money, inventory, email, permissions, and other non-repeatable effects.

**Next**: [Kafka Idempotence and Transactions](02_idempotence_transactions_and_exactly_once.md) or
[Retries, Dead Letters, and Replay](03_retries_dead_letters_and_replay.md).
