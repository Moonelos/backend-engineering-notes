# Kafka's “Exactly Once” Ends at the Boundary It Can Transact

> **Who this is for**: engineers reviewing duplicate-prevention or exactly-once claims.

## Three mechanisms cover three scopes

| Mechanism | Prevents | Does not prevent |
|---|---|---|
| Producer idempotence | duplicate log appends from one producer retry sequence | duplicate business events sent intentionally |
| Kafka transaction | partial writes across Kafka records and consumed offsets | duplicate effects in an unrelated database or API |
| Consumer idempotency | repeated business effects for a stable key | data loss from committing too early |

---

## 1. Producer idempotence makes retry sequencing safe

Modern clients enable idempotence when compatible settings remain in force. `acks=all`, retries,
and bounded in-flight requests let the broker assign a producer ID and reject a repeated sequence
number. For example, if batch sequence `17` reaches the leader but its acknowledgment is lost, the
retry still carries sequence `17`; the leader returns success without appending a second copy. A
new intentional `produce()` call uses sequence `18`, so producer idempotence does not deduplicate
two business calls with the same payload. Explicitly verify effective configuration rather than
assuming a framework wrapper preserved it. See the
[Kafka 4.3 producer configuration](https://kafka.apache.org/43/configuration/producer-configs/)
for the exact compatibility constraints.

---

## 2. Transactions atomically publish Kafka output and offsets

A consume-transform-produce application can write output records and the input group's offsets in
one Kafka transaction. `read_committed` consumers hide aborted transactional records. If the effect
is a card API call, Kafka cannot roll it back; use the provider's idempotency key or a durable local
state transition.

For input `orders[2]@8`, the processor API sequence and visible state are:

```text
producer.begin_transaction()
producer.produce("billing.commands", key="ord-42", value=charge)
producer.send_offsets_to_transaction({orders[2]: 9}, group_metadata)
producer.commit_transaction()
```

The offset value is `9`, the next record to read. If the process crashes after `produce` but before
commit, the transaction remains open temporarily. A `read_committed` consumer stops at the **last
stable offset** before that open transaction, so later records can exist physically while the
consumer appears to lag. Restarting a producer with the same stable `transactional.id` and calling
`init_transactions()` fences the dead instance and resolves its unfinished transaction; otherwise
the coordinator aborts it after the transaction timeout. The input group still resumes at offset
8. After restart, one committed charge and offset 9 become visible together. If commit succeeds
before the crash, restart begins at 9 and does not repeat offset 8.

```text
crash point                         read_committed output   group resumes
after produce, before commit        none                    orders[2]@8
after successful commit             one charge              orders[2]@9
explicit abort_transaction()        none                    orders[2]@8
```

**Success signal:** kill the processor before commit and observe no partial output with
`read_committed`; restart and obtain one committed result. Counting records under the default
isolation silently includes aborted work.

The collection includes that exact process-death test. Start the disposable Kafka 4.3.1 broker from
the first fundamentals note. Then, from `infrastructure/kafka/examples/python`, run:

```bash
uv sync --dev
uv run pytest -q tests/integration/test_transactions.py
```

[`transaction_worker.py`](../examples/python/kafka_notes/transaction_worker.py) configures a stable
transactional identity, disables consumer auto-commit, sends next offset `1` with the output, and
aborts on handled errors. The first child deliberately exits after `OUTPUT_STAGED`; the second uses
the same identity, resolves the open transaction, and commits. The `read_committed` assertion sees
exactly one output. **Failure signal:** `init_transactions()` times out or returns a coordinator
error; preserve the broker and client logs rather than treating the staged output as committed.

> **Key insight**: exactly-once processing is credible only after naming every state store inside
> the atomic boundary and the strategy for every store outside it.

---

## 3. What breaks, and when not to use transactions

⚠️ Reusing a transactional ID concurrently fences one producer instance; generating random IDs on
every restart loses the stable identity required for recovery.

⚠️ After an abort, discard or reposition consumer state before processing again. Do not continue
from in-memory positions that belonged to the aborted attempt; this example exits and lets group
assignment resume from the committed offset.

Avoid Kafka transactions for simple source producers or external sinks when idempotent writes are
clearer and cheaper.

---

**Next**: [Retries, Dead Letters, and Replay](03_retries_dead_letters_and_replay.md).
