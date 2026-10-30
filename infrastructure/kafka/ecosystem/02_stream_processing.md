# Stream Processing Materializes Continuously Changing Answers

> **Who this is for**: engineers deriving, joining, or aggregating event streams.

## A window changes an unbounded stream into a bounded question

“Count payments” never finishes. “Count accepted payments per merchant in five-minute **event-time
windows**”—buckets selected by timestamps inside the events—defines keys, time boundaries,
late-arrival policy, and an output update model. A **watermark** is the engine's estimate of how far
event time has advanced; a **grace period** keeps a window revisable for a bounded interval after
its nominal end.

Take merchant `m-7`, a five-minute window `[10:00, 10:05)`, a two-minute grace period, with the
watermark advancing to `10:06` before `pay-3`, then beyond `10:07` before `pay-4`:

```text
arrival  event timestamp  record       window state / emitted update
10:01    10:01            pay-1, €10   count=1, total=€10  → emit (1, €10)
10:04    10:03            pay-2, €20   count=2, total=€30  → emit (2, €30)
restart  —                restore      state remains (2, €30) from changelog/checkpoint
10:06    10:02            pay-3, €5    within grace        → emit correction (3, €35)
10:07:30 10:08            progress     watermark/stream-time advances to 10:08
10:08    10:04            pay-4, €9    window now closed   → late/drop side output
```

The event timestamp, not arrival time, selects the window. `pay-3` updates an already emitted
answer because the event-time progress frontier has not passed the window end plus grace.
`pay-4` is late because that frontier has advanced beyond `10:07`; a later wall-clock arrival alone
does not close the window. If the frontier stayed at `10:06`, the same delayed record could still
update it. Engines define progress differently (Kafka Streams uses stream-time); apply the chosen
engine's advancement and idle-partition rules. Recovery must restore the matching aggregate and
progress state before new input.

---

## 1. State appears as soon as output depends on history

Filtering one record is stateless. Counts, joins, deduplication, and sessions require a **state
store**, durable per-key working data restored after failure; partition-compatible keys; a recovery
**changelog**, a replicated record of state updates, or checkpoint; and retention. Event time uses
the timestamp carried by the event;
**processing time** uses when the application sees it. Late events make those answers diverge.

Kafka Streams is the native Java library; Flink and other engines provide broader distributed
processing models. Python services can consume and produce directly, but should not recreate a
stateful engine casually.

**Success signal:** feed on-time and deliberately late records and observe the documented window
updates after restart. A correct happy-path count silently avoids the hard time semantics.

> **Key insight**: a streaming computation is a maintained state machine whose correctness depends
> on keys, time, recovery, and output semantics—not a loop that happens to run forever.

---

## 2. What breaks, and when not to stream

⚠️ Joining streams partitioned by different keys produces incomplete or expensive results unless
one side is repartitioned deliberately.

Use batch SQL when minutes or hours of latency are acceptable and recomputation is simpler than
continuous state. Use a database view when all inputs already live transactionally in one database.

---

## Recap

- Stream processing retains state across records instead of treating each record independently.
- Event time describes the business occurrence; processing time describes arrival at the worker.
- Late-data policy and restored state determine the result after delay or restart.

## Check yourself

**Q: An event occurred at 12:01 but arrives at 12:07. Which clock assigns its event-time window?**

<details><summary>Answer</summary>

Its validated 12:01 event timestamp. Whether the already-closed window may change depends on the taught lateness/grace policy; arrival alone does not move the event into a 12:07 business window.

</details>

**Q: Can restoring offsets without the corresponding aggregate state preserve the result?**

<details><summary>Answer</summary>

No. Advancing the checkpoint beyond lost state skips contributions, while replaying against already-applied state can double-count. Restore compatible state/checkpoints or rebuild an isolated result.

</details>


**Next**: [Share Groups and Queue Semantics](03_share_groups_and_queue_semantics.md)
