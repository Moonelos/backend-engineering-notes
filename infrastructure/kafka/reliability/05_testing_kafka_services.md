# Kafka Tests Must Cross the Broker and the Crash Boundary

> **Who this is for**: engineers proving delivery, compatibility, replay, and recovery claims.

## Run the smallest real-broker test

Mocks can verify that code called `produce`; they cannot prove broker acknowledgment, offsets,
consumer-group ownership, serialization, or redelivery. Start the disposable broker from
[First Event Round Trip](../fundamentals/01_first_event_round_trip.md), enter the checked-in example
project, and run this bounded smoke test against `localhost:9092`:

```bash
cd infrastructure/kafka/examples/python
uv sync --dev
uv run pytest -q tests/integration/test_kafka_smoke.py
```

The checked-in [test](../examples/python/tests/integration/test_kafka_smoke.py) creates a uniquely
named topic, waits for the broker acknowledgment, consumes with a unique group, asserts
key/value/partition/offset, and closes the consumer in `finally`. Every broker wait is bounded.

**Success signal:** the test exits with `1 passed` and leaves no running consumer. A mock-only green
test or a test that can hang has not established a Kafka guarantee.

---

## 1. Each guarantee needs the smallest environment that can falsify it

| Claim | Minimum useful test | A mock cannot reveal |
|---|---|---|
| Payload remains compatible | old/new schema fixtures plus registry compatibility check | registry subject policy or wire ID |
| Producer delivered | real broker and delivery callback | broker rejection after local enqueue |
| At-least-once effect is safe | real broker, durable effect store, process kill | redelivery across lost process memory |
| Transaction hides partial output | transactional producer and `read_committed` consumer | aborted broker state |
| Replay is bounded | retained records, explicit offsets, idempotency store | wrong partition/range or duplicate effect |
| Capacity recovers | production-shaped records and constrained downstream | compression, skew, rebalance, or disk limits |

Use unit tests below the first row only for pure decisions: envelope construction, retry
classification, contiguous-offset arithmetic, and idempotency-key selection.

---

## 2. A crash test is an ordered state trace

Add a test-only fault hook immediately after the external effect and before offset commit. For
`evt-101`, persist the effect in a table with `event_id` unique, then terminate the worker process
at that hook:

```text
produce evt-101
worker attempt 1 → INSERT effect(evt-101) → process exits before commit
restart worker
worker attempt 2 → INSERT ... ON CONFLICT DO NOTHING → commit next offset
assert effect rows for evt-101 = 1
assert committed offset advanced exactly once past the input
```

Run the same scenario with faults before the effect, after the effect, and after commit. Synchronize
on an explicit `FAULT_REACHED event_id=evt-101` line or test-control socket before killing the
process; sleeping for an estimated duration makes the crash point nondeterministic.

> **Core:** launch the worker as a child process. Raising an exception inside the test process does
> not reproduce lost memory, abandoned sockets, group departure, or transactional timeout.

The collection implements the trace in
[`test_crash_recovery.py`](../examples/python/tests/integration/test_crash_recovery.py). Run it with
the disposable broker still active:

```bash
uv run pytest -q tests/integration/test_crash_recovery.py
```

The controller starts [`crash_worker.py`](../examples/python/kafka_notes/crash_worker.py) at three
fault stages: before effect, after effect, and after commit. It expects the explicit `FAULT_REACHED`
line and exit code `86`; cases before commit restart with the same group and SQLite effect store.
**Success signal:** `3 passed`; the after-effect restart prints `created=false`, Kafka reports the
group's committed offset as exactly `1`, and SQL reports one `evt-101` row in every case.

The companion transaction test performs the other central boundary:

```bash
uv run pytest -q tests/integration/test_transactions.py
```

The first process dies with an open transaction after staging output. The second starts with the
same `transactional.id`, resolves the previous instance in `init_transactions()`, and atomically
commits output plus source position. The test requires source-group offset `1`; a `read_committed`
consumer must also see exactly one output.

> **Key insight**: a delivery guarantee is falsifiable only when the test controls the exact state
> boundary and observes every durable store on both sides of the crash.

---

## 3. A reusable suite composes fixtures, not one giant scenario

Keep four fixture layers: contract fixtures with representative old data; a disposable real broker
and registry; application dependencies such as PostgreSQL; and process controls for ready, fault,
kill, and restart. Give every test unique topic/group identifiers so parallel runs cannot consume
one another's records.

Then keep focused suites:

1. Contract tests run on every change and never need Kafka unless wire serialization is under test.
2. Broker integration tests cover callbacks, commits, rebalances, transactions, and retry records.
3. Replay tests seed an explicit partition/offset interval and compare before/after effect counts.
4. Load tests use real record-size/compression/key distributions and assert a lag recovery time.
5. Game days exercise broker or region loss with production runbooks and measure recovery-time
   objective (RTO) and recovery-point objective (RPO).

In routine work, the first three are the default subset; the crash trace above is the concrete
broker-integration case. Load tests and game days run on a scheduled or release gate where their
cost and disruption are controlled.

> **Production:** pin container images to the deployed Kafka line, retain broker/client logs on
> failure, cap every wait, and make cleanup idempotent. The checked-in suite uses the same explicit
> Docker broker as the first lesson so setup remains visible; a maintained Python container fixture
> may wrap the same lifecycle in a larger codebase.

---

## 4. What breaks, and when not to use a local broker

⚠️ Reusing a consumer group or topic across tests makes the result depend on prior committed
offsets. The symptom is a test that passes alone and times out in the suite.

⚠️ A single-node broker cannot prove replication, leader failover, quorum loss, or cross-region
recovery. Use a multi-node staging environment for those claims.

Do not replace deterministic contract and state-machine unit tests with broker tests; the slower
harness belongs only where broker state or process death can change the answer. Do not run
destructive replay or region game days against production without an approved, bounded exercise.

---

**Next**: [Kafka Operations](../operations/README.md)
