# Retries, Timeouts, and Cancellation Are Durable Control Decisions

> **Who this is for**: Engineers deciding when another attempt may run, when work is too late, and how a stop request races completion.

Before reading this, understand temporary attempt ownership in **[Leases, Heartbeats, and Fencing](02_leases_heartbeats_and_fencing.md)**.

---

## 1. An exception handler cannot own a recovery schedule

A provider returns `503`, the worker sleeps for 30 seconds, and the pod is deployed during the sleep. The retry disappears. On another day, every worker retries immediately and multiplies an outage into a retry storm.

A retry is a durable state transition from the currently owned attempt to either:

```text
RUNNING(token-a)
  ├── retryable + budget remains ──► PENDING(next_attempt_at, no token)
  └── permanent or exhausted ──────► FAILED(terminal evidence)
```

The database timestamp, error class, and budgets decide when another claim is legal. The worker runtime may wake polling, but it is not the source of the schedule.

> **The near-miss**: broker retry count looks like the retry budget. It does not include republishing, manual redrive, job recreation, or time spent between deliveries. Keep the business attempt and wall-clock budgets in durable execution state.

---

## 2. Retry only errors that time or a new attempt can change

The **default retry set** is connection timeout, rate limit, temporary provider failure, and transaction serialization conflict.

| Error class | Retry? | Durable policy |
|---|:---:|---|
| **Connection timeout** | ✓ | Full-jitter backoff; same operation key |
| **HTTP `429`** | ✓ | Honor `Retry-After`; global rate limit |
| **Provider `502`/`503`** | ✓ | Backoff, concurrency reduction, circuit breaker |
| **Database serialization conflict** | ✓ | Short bounded transaction retry after reloading state |
| Invalid input | No | `FAILED` with validation evidence |
| Authorization denied | No automatic loop | Terminal/config incident until credentials change |
| Missing domain entity | Usually no | Mark stale contract violation |
| Deterministic code defect | No automatic loop | Quarantine and deploy a fix |
| Ambiguous provider timeout | Same-key recovery | Query/repeat with provider idempotency; do not assume failure |

Classify at the boundary where evidence is available. “Any exception is retryable” hides programmer defects and authorization incidents inside queue noise.

---

## 3. Full jitter spreads a shared outage

This complete helper caps exponential growth and validates its inputs:

```python
import random


def retry_delay(
    attempt: int,
    base_seconds: float = 1.0,
    cap_seconds: float = 300.0,
    rng: random.Random | None = None,
) -> float:
    if attempt < 1:
        raise ValueError("attempt starts at 1")
    if base_seconds <= 0 or cap_seconds <= 0:
        raise ValueError("retry delays must be positive")
    random_source = rng or random.Random()
    ceiling = min(cap_seconds, base_seconds * (2 ** (attempt - 1)))
    return random_source.uniform(0.0, ceiling)


if __name__ == "__main__":
    seeded = random.Random(7)
    delays = [retry_delay(attempt, rng=seeded) for attempt in range(1, 6)]
    assert all(0 <= delay <= 2 ** (attempt - 1) for attempt, delay in enumerate(delays, 1))
    print(delays)
```

When a provider returns a valid `Retry-After`, treat it as the minimum next eligible time and still apply a small random spread if many jobs share that timestamp.

> **Key insight**: Retry policy is load policy. Every delay and budget changes how much traffic a failing dependency receives, so it belongs in durable, observable state.

---

### The budget is checked again when work is claimed

A retry chosen at 10:59 for 11:01 already exceeds an 11:00 cutoff. The scheduling predicate above compares the proposed `next_attempt_at`, not only the current time. A queue delay can still push a valid 10:59 retry past 11:00, so the claim must also include:

```sql
-- Add to the canonical PENDING claim predicate; max_retry_age is an interval.
AND (first_failed_at IS NULL OR now() < first_failed_at + :max_retry_age)
```

A bounded reconciler terminalizes expired pending jobs instead of leaving them eligible forever. Use the same token/state conditions when changing running jobs; a past deadline alone does not authorize a stale attempt to write. The complete [durable-job adapter](../examples/durable_job/store.py) stores an absolute `retry_deadline` and checks it in retry, claim and recovery. Its [budget test](../examples/durable_job/test_lifecycle.py) proves that a ready-but-expired row is never claimed and becomes `FAILED`.

## 4. One owned transition chooses retry or terminal failure

The job's `attempt` was incremented at claim. On failure, compute `:next_attempt_at` in application code from the classified error and provider guidance, then commit this conditional transition:

```sql
WITH owned AS (
    SELECT id, workflow_run_id, attempt, first_failed_at
    FROM jobs
    WHERE id = :job_id
      AND status = 'RUNNING'
      AND attempt_token = :attempt_token
      AND lease_expires_at > now()
    FOR UPDATE
),
decided AS (
    UPDATE jobs AS j
    SET status = CASE
            WHEN :retryable
             AND owned.attempt < :max_attempts
             AND :next_attempt_at < COALESCE(owned.first_failed_at, now()) + :max_retry_age
                THEN 'PENDING'
            ELSE 'FAILED'
        END,
        next_attempt_at = CASE
            WHEN :retryable
             AND owned.attempt < :max_attempts
             AND :next_attempt_at < COALESCE(owned.first_failed_at, now()) + :max_retry_age
                THEN :next_attempt_at
            ELSE NULL
        END,
        first_failed_at = COALESCE(owned.first_failed_at, now()),
        last_error_class = :error_class,
        last_error = :safe_error_message,
        terminal_reason = CASE
            WHEN NOT :retryable THEN 'PERMANENT_ERROR'
            WHEN owned.attempt >= :max_attempts THEN 'ATTEMPT_BUDGET_EXHAUSTED'
            WHEN :next_attempt_at >= COALESCE(owned.first_failed_at, now()) + :max_retry_age
                THEN 'WALL_CLOCK_BUDGET_EXHAUSTED'
            ELSE NULL
        END,
        finished_at = CASE
            WHEN :retryable
             AND owned.attempt < :max_attempts
             AND :next_attempt_at < COALESCE(owned.first_failed_at, now()) + :max_retry_age
                THEN NULL
            ELSE now()
        END,
        attempt_token = NULL,
        worker_id = NULL,
        lease_expires_at = NULL
    FROM owned
    WHERE j.id = owned.id
    RETURNING j.id, j.workflow_run_id, j.status, j.next_attempt_at, j.terminal_reason
)
SELECT * FROM decided;
```

One `PENDING` row is a durable retry; one `FAILED` row is terminal. Zero rows means ownership was lost, so the worker must not acknowledge the failure as handled. For a required workflow step, extend the same transaction with a conditional `workflow_runs → FAILED` transition and history insert selected from `decided WHERE status='FAILED'`.

The claim query must include `next_attempt_at <= now()`. Omitting that predicate silently turns every durable backoff into an immediate retry.

**How you know it is working**: freeze time in an integration test, fail attempt 1, and prove no worker can claim until the persisted timestamp. Exhaust attempt and age budgets separately and assert terminal reason identifies which budget ended the job.

---

## 5. Timeouts protect nested resources at different boundaries

| Boundary | Failure it bounds | Required evidence |
|---|---|---|
| Connect/pool timeout | DNS, TCP/TLS, or connection-pool starvation | Dependency and pool-wait metric |
| Read/write timeout | Stalled network transfer | Provider endpoint and phase |
| Provider operation timeout | Remote work exceeding its contract | Provider operation key for recovery |
| Attempt deadline | All work in one lease ownership epoch | Attempt token and elapsed duration |
| Workflow deadline | Result no longer has business value | Named timeout event/history |
| Lease expiry | Worker stopped proving liveness | Lost-token/fencing evidence |

The first three must exist on every external client. An attempt deadline does not replace them: forcibly cancelling a coroutine or process may leave the remote effect committed. Recover that ambiguity with the same operation key.

Python threads cannot safely stop arbitrary blocking library code. Coroutine cancellation is cooperative. Process termination is forceful and may interrupt local writes. Isolate uncooperative calls in a process when necessary, but still apply provider timeouts and idempotency.

⚠️ A task-level timeout without a shorter provider timeout repeatedly kills local workers while the provider continues processing old requests.

---

## 6. Cancellation is a named compare-and-set command

The API authenticates the actor, loads current state and version, validates the versioned `cancel` event, then commits state plus evidence:

```sql
WITH cancelled AS (
    UPDATE workflow_runs
    SET state = 'CANCELLED',
        version = version + 1,
        cancellation_requested_at = now(),
        updated_at = now()
    WHERE id = :run_id
      AND state = :expected_state
      AND version = :expected_version
    RETURNING id, version
),
history AS (
    INSERT INTO workflow_transitions (
        workflow_run_id, from_state, event, to_state,
        actor_type, actor_id, workflow_version, metadata
    )
    SELECT id,
           :expected_state,
           'cancel',
           'CANCELLED',
           :actor_type,
           :actor_id,
           version,
           jsonb_build_object(
               'reason', :reason,
               'authorization_basis', :authorization_basis
           )
    FROM cancelled
)
SELECT id, version FROM cancelled;
```

The completion transaction expects the previous state/version. If completion commits first, cancellation gets zero rows and returns “already completed.” If cancellation commits first, completion gets zero rows and cannot resurrect the run.

---

## 7. Workers stop at safe points and compensate committed effects

Cancellation is durable state, not a signal guaranteed to arrive. A worker checks it:

```text
before provider call
  → after provider response is persisted
  → before scheduling each next unit
  → before terminal workflow completion
```

Do not check between a provider effect and persistence of its response; complete that local evidence first. If the effect already committed, schedule a new compensation operation:

```text
cancel wins
  + provider_operations(generate).state = SUCCEEDED
  → insert compensation job
       key = run-42:discard_or_reverse_generation:v3
  → append compensation_requested evidence
```

A compensation is a new effect with its own lifecycle. A refund offsets a capture; it does not erase the original payment. An email may have no meaningful compensation, so the product must define “cancel prevents future sends but cannot unsend delivered mail.”

⚠️ Treating infrastructure shutdown as business cancellation incorrectly moves valid workflows to `CANCELLED`. Shutdown should stop claims, preserve heartbeat while draining, then release or retry unfinished attempts.

Do not retry deterministic failures until code or input changes. Do not offer cancellation when the product cannot explain what happens to already committed irreversible effects. Do not use `sleep()` as a durable retry or timer.

---

## Recap and check yourself

- Retry reuses the obligation and records a durable next eligible time.
- Attempt and elapsed-time budgets must hold both when scheduling and when claiming.
- Cancellation and completion race through expected state/version; external committed effects may need compensation.

**Cancellation commits while a provider response is in flight. Can completion set success afterward?**

<details><summary>Answer</summary>

No. Its expected state/version no longer matches. Preserve provider evidence separately and schedule compensation if the business policy requires it.

</details>

**At 10:59 a backoff chooses 11:01, but the retry deadline is 11:00. Schedule it?**

<details><summary>Answer</summary>

No. Compare the proposed eligibility time to the deadline. Also recheck at claim because queue delay can make a previously valid retry too old.

</details>

**Try it:** Set a pending job’s retry_deadline into the past in the canonical test. Fill the expected `claim` result and state after `recover`.

<details><summary>Hint and worked solution</summary>

Eligibility time and deadline are independent conditions. `claim` returns None; recovery marks FAILED. Making it immediately ready must not bypass elapsed-time exhaustion.

</details>


**Next**: [Reconciliation, DLQ, and Observability](05_reconciliation_dlq_and_observability.md)
