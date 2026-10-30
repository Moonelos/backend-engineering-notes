# Part 9: Admit provider attempts across a fleet

> **Role:** implementation tutorial. Prerequisites: [local bounded admission](03_call_patterns.md), [failure domains](06_advanced_patterns.md), and basic Redis keys and transactions.
>
> **Outcome:** run two Redis clients racing for the last permit, wire atomic shared admission into the canonical caller, recover an ambiguous reply without charging twice, and understand the boundary between leased capacity and durable quota.

Four replicas each allow twenty provider requests. That is eighty possible active
requests, even if the provider account supports only twenty. A process semaphore has
no view of the other replicas. Shared admission must decide whether an attempt can
start using one common authority and one atomic decision.

The running example is inventory request Q1 from verified tenant Alice. It fails with
503 once, retries, then succeeds. Q1 is **one logical user operation** and **two provider
attempts**. Keeping those identities separate prevents both quota bypass and double
charging of a logical product action.

## 1. State the policy before selecting a data structure

The complete fixture implements these independent limits for one provider account:

| Limit | Fixture default | Charged/released when |
|---|---:|---|
| Global active attempts | 20 | Acquire at admission; release after response close or expire lease |
| Active attempts for authenticated user | 4 | Same attempt lifetime, separate user partition |
| Provider starts in trailing 60 seconds | 100 | Charge once on successful admission; never refund ambiguous starts |
| Pause flag | `paused=1` | Reject new admission; already-owned work completes under its deadline |
| Durable user token budget | Separate PostgreSQL ledger | Reserve once for Q1; settle all attempts in Part 10 |

A rate limit counts starts over time; concurrency counts current owners. A request can
satisfy one and fail the other. The fixture conservatively counts an admitted start even
if cancellation occurs before network dispatch; it never claims the provider definitely
received that request. This sacrifices a little capacity to avoid refunding uncertain work.

The script checks the global count, user count, rolling start count and pause flag before
adding any new lease. A failed check makes no new reservation. The check and mutation
must be atomic: `GET count`, compare in Python, then `INCR` lets two clients both observe
the last free slot and both enter.

```mermaid
sequenceDiagram
  participant A as Replica A
  participant R as Redis authority
  participant B as Replica B
  A->>R: admit Q1 attempt 0
  B->>R: admit Q2 attempt 0
  R->>R: prune expired leases; one slot remains
  R->>R: A: add active lease + user lease + RPM start
  R-->>A: granted
  R->>R: B: global active count now at limit
  R-->>B: denied; no start charged
```

The actual two-client test asserts exactly one grant. It does not substitute an in-memory
lock for the Redis race. [advanced_admission.py](examples/advanced_admission.py) contains
the full script and the asynchronous `FleetAdmission.attempt` context manager.

## 2. One atomic script, one server clock, one cluster slot

Three sorted sets store global lease expiries, per-user lease expiries and start times.
At admission, expired entries are removed using Redis server `TIME`. `ZCARD` after this
pruning describes live leases. A raw `ZCARD` sampled later without pruning can include
expired records; dashboards should count scores greater than server time or prune first.

The script uses Redis 7+ effects replication: server time can drive writes because
replication transmits the resulting effects. The old blanket rule that a script may not
write after a nondeterministic command does not describe this baseline. Redis documents
[effects replication](https://redis.io/docs/latest/develop/programmability/lua-api/)
and [atomic script execution/cache lifetime](https://redis.io/docs/latest/develop/programmability/eval-intro/).
Scripts should remain small because execution blocks other server work.

All script keys share a hash tag derived from the trusted account:

```text
admission:{account-digest}:active
admission:{account-digest}:user:user-digest
admission:{account-digest}:rpm
admission:{account-digest}:attempt:operation-attempt-digest
admission:{account-digest}:flags
```

The braces force one Redis Cluster slot; account/user inputs are hashed so caller text
cannot inject a new tag. Every accessed key is passed via `KEYS`, rather than constructed
inside Lua. This conforms to Redis's [cluster multi-key constraints](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).
The lab runs standalone Redis. The same-slot layout prepares the script for Cluster,
but the lab does not test a Cluster rollout, resharding or failover.

One hot provider account still occupies one authority shard. Sharding a genuinely global
limit across unrelated slots without an allocation protocol changes its guarantee. At
higher scale, allocate conservative per-shard budgets or use a dedicated admission
service and document its consistency/failure contract.

## 3. A lost reply is not a failed mutation

Suppose Redis commits Q1/attempt0, but the client times out before seeing the reply.
Retrying with a new UUID can reserve twice and consume two starts. The fixture stores
an attempt record indexed by `(trusted user, operation_id, attempt_no)` and a separate
random **owner token** generated once for that context's acquisition/recovery.

Retrying the admission command uses the same attempt identity and owner token. If the
stored grant still has enough lease time for the complete hard attempt bound, Redis
returns `recovered` without changing counters. A different process presenting the same
attempt identity has a different owner token and is denied: replaying a grant must not
let two processes both dispatch it. A new owner needs higher-level recovery of the
operation, not a second execution based only on finding a granted record.

The release script removes only the matching token and marks the attempt released.
It also writes a released tombstone when acquisition is uncertain and no record is yet
visible. That prevents a delayed acquisition command from resurrecting a cancelled
attempt. An old token never removes a replacement lease's member.

Records remain for 24 hours in this laboratory. That is the maximum deduplication
horizon, not durable business identity: do not reuse an attempt identity after retention,
and do not retry an old operation blindly after a process restart. A long-lived operation
needs durable state and retention matching its reconciliation horizon. Parts 10 and 11
own those records.

## 4. Lease expiry restores liveness, not remote cancellation

The caller's hard attempt deadline is two seconds; the shared lease lasts five seconds.
The margin covers transport teardown and event-loop scheduling. Recovery refuses a
stored grant with less than two seconds remaining. There is no lease renewal in this
finite-attempt fixture; streaming needs a different owner with a bounded total lifetime
or carefully supervised renewal and cancellation.

When a process dies, expiry eventually frees capacity. A paused process or a provider
which continues after client cancellation can still be executing after the lease expires.
Redis cannot revoke a remote HTTP request. Therefore this is a bound on **valid leased
application owners**, not a mathematical guarantee that the provider has at most twenty
physical computations during crashes/network partitions. Strict provider enforcement
requires a provider-side limit or a fencing/coordinator contract the provider honors.

The expiry/replacement ordering is independent of whether the original process resumes.

```mermaid
sequenceDiagram
  participant A as Owner A token A
  participant R as Redis authority
  participant B as Owner B token B
  A->>R: reserve token A, expires at 120
  Note over A,R: A disappears; remote work may continue
  B->>R: at 121 prune expired A; reserve token B
  A->>R: late release token A
  R-->>A: token B remains owned by B
```

Reclamation restores available accounting while unique token removal protects the new owner.

Late release is safe because members are unique tokens. If A expires and B enters,
A's `ZREM token-A` cannot remove token-B. The fixture tests that state explicitly. A
negative counter implementation with generic `DECR` would not have the same property.

## 5. Wire admission into the accepted caller

Run the complete integration, including its fake 503 then 200 provider:

```bash
cd examples
python3.14 -m venv .venv
.venv/bin/pip install -r advanced_requirements.txt
docker compose -p advanced-notes-repair -f advanced_compose.yaml up -d --wait
.venv/bin/python advanced_admission_demo.py
.venv/bin/python -m pytest -q advanced_test_redis.py
```

Expected demo output includes `provider_attempts=2`, `rpm_entries=2`, `active=0` and
`{'ok': True}`. [The full executable](examples/advanced_admission_demo.py) supplies
finite Redis connect/socket timeouts, disables hidden client retry loops, and constructs:

```python
# Excerpt; redis/client lifespan and imports are supplied in advanced_admission_demo.py.
fleet = FleetAdmission(redis, account='provider-account', user='verified-tenant',
                       attempt_ms=2000, lease_ms=5000)
caller = BoundedCaller(client, attempt_timeout=2,
                       attempt_admission=fleet.attempt)
result = await caller.request_json('GET', '/inventory',
                                  operation_id='inventory-q1', max_attempts=2)
```

The core enters local/shared admission under its admission deadline, then exits that
timer before provider execution. The external context remains owned through response
close. Rejection raises `AdmissionTimeout`, which the core does not retry. A retryable
provider failure enters the hook again with the same operation ID and a new attempt
number. Do not add a second retry wrapper around the caller or invent an `on_reject`
argument: it would obscure attempt counts and total deadlines.

The fixture recovers one ambiguous Redis command with the same identity, then fails
closed. Its `finally` attempts release even if cancellation happened before `yield`.
Finite Redis socket timeouts bound cleanup; if Redis remains unavailable, the lease
expires and the host must emit a cleanup-failure metric. User quota is not refunded.

## 6. Outage, cache loss and operator controls

`register_script` reloads on `NOSCRIPT`; the test flushes the script cache and then
releases a lease. A cache miss is recoverable deployment state, not evidence that the
underlying reservation disappeared. An unavailable Redis connection instead prevents
provider dispatch. The outage test points at an unavailable local port and asserts zero
provider calls and zero local active owners.

A pause is real policy: operators set `paused=1` in the account's flags hash, and the
admission script reads it before granting. Protect this mutation with an operational
identity; end users must not select the account key or change its limits. Expose a
controlled pause/resume command in your deployment tooling and audit the change.

Redis asynchronous replication/failover can lose acknowledged writes. If admission state
is lost, the replacement authority can admit work while previous owners still run. The
lab does not promise a strict cap through that event. For an operation requiring stronger
safety, pause admission externally on authority replacement, wait the maximum old lease/
attempt horizon before resuming, or use a store/coordinator with the required consistency.
Durable financial quotas belong in a durable transaction boundary, not in an evictable
Redis counter. Never treat fail-open as a free availability improvement: specify a
conservative fallback allocation or reject.

## 7. Observe the decisions and retain the obligation

Measure grants/denials by bounded reason, admission latency, Redis errors, recovered
ambiguous replies, release failures, live leases, expired leases pruned and RPM starts.
Alert on active leases near capacity and on a rising gap between admissions and actual
provider sends. A high gap may indicate cancellations or dispatch failures; it does not
automatically justify refunding uncertain starts.

For production, verify:

- Every script key is in one intended slot and every application replica uses the same
  account partition and policy version.
- Logical operation IDs survive retries; owner tokens survive only one context's command
  recovery. Competing owners cannot both reuse a grant.
- Attempt deadlines fit within leases with measured cleanup margin; response close
  precedes release; failed cleanup is observable.
- Operator pause, missing script, unavailable Redis, stale release and ambiguous reply
  each have an exercised recovery path. Failover limitations are accepted explicitly.
- Durable quota windows and unresolved usage remain in Part 10's ledger; local date/time
  at completion never selects a replacement quota bucket.

If starts spike during Redis latency, inspect command retry identity before increasing
RPM. If concurrency appears permanently high, distinguish expired stored members from
live owners. If a midnight completion changes today's budget, fix reservation identity
and original-window settlement rather than adding more Redis counters.

## Recap

Fleet admission atomically decides one provider attempt using shared policy and server
time. Stable attempt identity plus an owner token recovers ambiguous replies without
duplicate dispatch. Leases restore liveness; durable user quota and external effects
require their own persistent contracts.

## Check yourself

<details><summary>Redis committed admission but the reply was lost. Is a new UUID harmless?</summary>
No. It can charge another start and reserve another slot. Recover the same attempt and
owner record, require sufficient lease time, and deny a different owner from dispatching
the same granted attempt.
</details>

<details><summary>Q1 retries once. How many user reservations and provider starts are there?</summary>
One logical user reservation covers Q1's full enforced attempt budget. Two admitted
provider attempts consume two provider starts and each owns/relinquishes a concurrency
lease. Settlement uses Q1's original durable quota window.
</details>

## Try it

Set global capacity to two and per-user capacity to one. Race two Alice operations and
one Bob operation through independent clients. Predict which constraint can reject each
request, then assert no partial reservation remains on denial. Next lose the successful
admission reply, repeat with the same owner, and verify the RPM set grows by exactly one.

Scaffold: create Alice and Bob `FleetAdmission` objects with the same account,
`global_limit=2`, `user_limit=1`, and different trusted user IDs. Race two Alice
acquisitions and one Bob acquisition; fill in the expected total grants and user-denial count.

Hint: Redis serializes the whole check-and-add. Alice cannot hold two permits even when
the account still has room.

<details><summary>Reasoned solution</summary>
Two grants are possible: one Alice and one Bob. The other Alice call is rejected by user
concurrency or global concurrency depending on script ordering, with no partial lease or
RPM charge. Replaying a successful admission with its same owner returns recovered and
adds zero RPM entries; a new owner cannot dispatch that same attempt.
</details>

**Next:** [Durable token economics](10_llm_token_economics.md). **Back:** [learning map](README.md).
