# Delivery Semantics Are the Order of Effect and Checkpoint

> **Who this is for**: engineers who need to state what a consumer does across crashes.

## One crash distinguishes the guarantees

```text
at-most-once:  commit next offset 9 → crash → charge for offset 8 never runs = loss
at-least-once: charge offset 8 → crash → no commit → offset 8 runs again    = duplicate
```

---

## 1. No commit order removes both outcomes

Here, **processing** means completing the durable business effect—in this example, charging the
order—not merely entering a handler. Committing next offset `9` says offset `8` is finished. If the
worker says that before charging and then dies, its replacement starts at `9`; record `8` still
exists, but this group has skipped it. Committing after the charge reverses the risk: the replacement
starts at `8` and may charge again.

No commit order removes both outcomes. Kafka's usual baseline is at-least-once plus an idempotent
effect because a detected duplicate is normally safer than silent loss.

An **idempotency key** makes repeated execution converge on one effect. Use stable `event_id`, not
partition offset alone, when the same logical event might be republished elsewhere. The key only
works when a durable store or provider claims it uniquely and returns the first result on a repeat;
the next note implements that transition.

---

## 2. Test the crash windows, not only the happy path

Inject failure before the effect, after the effect, and before the offset commit. **Success signal:**
every input reaches the intended final state and repeated attempts leave one effect. A passing
consumer test without process termination silently proves none of this. Use the runnable
[Kafka service test harness](05_testing_kafka_services.md) to control those crash points.

> **Key insight**: “once” is not a client setting; it is a claim about the combined record,
> checkpoint, and business-effect state transition.

---

## 3. What breaks, and when not to chase exactly once

⚠️ Committing a batch after only some records succeed skips the failed records on restart.

Do not pay transaction complexity for naturally idempotent derived state. Replacing a projection row
by stable key may already make replay safe.

---

**Next**: [Durable Consumer-Effect Idempotency](02_durable_consumer_effect_idempotency.md), then
[Kafka Idempotence and Transactions](02_idempotence_transactions_and_exactly_once.md) when every
effect stays inside Kafka.
