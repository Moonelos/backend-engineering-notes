# Part 11: Recover one operation across competing owners

> **Role:** implementation tutorial. Prerequisites: [bounded retry policy](03_call_patterns.md), PostgreSQL transactions/unique constraints, and [durable reservation identity](10_llm_token_economics.md).
>
> **Outcome:** run a tenant-scoped payment ledger which replays one outcome, rejects changed request meaning, survives process death inside the effect transaction, and prevents an expired owner from finishing a replacement owner's work.

The client submits a payment, the server commits it, and the connection breaks before
the client receives the response. A timeout does not reveal whether the payment happened.
The client needs to ask about the **same operation**, not create a second payment and
hope that the first failed. An idempotency key supplies that operation identity; storage
and transaction boundaries determine what guarantee the key actually provides.

Our example records a local payment in PostgreSQL. It does not contact a card network.
We establish that atomic boundary first, then explain what changes for a remote provider.

## 1. Bind one key to one authorized meaning

The server scopes a client key by `(tenant, endpoint, key)` and stores a hash of the
validated canonical request. A key reused by another tenant does not reveal or replay
the first tenant's response. The same tenant/key with a different amount returns a
conflict, even after the original operation completed.

The client generates a high-entropy key once for a logical action and persists it if
that action must survive a page/process restart. A new intentional purchase gets a new
key. Each transport attempt can have its own request/trace ID while retaining the same
operation key. The key is identity, not authentication; authenticate and authorize the
request before reading a stored result.

| Stored state for the same scope | Same request hash | Server decision |
|---|---|---|
| No operation | N/A | Atomically create generation 1 claim |
| PENDING with live lease | Yes | 409 with a bounded retry/poll policy |
| PENDING with expired lease | Yes | Lock row, increment generation, acquire replacement lease |
| DONE | Yes | Replay stored status and response body |
| Any existing state | No | 422 key-meaning conflict; never execute new meaning |

Hash the validated semantic input with a documented canonical encoding. The fixture
uses a validated integer amount and sorted compact JSON; a byte hash of raw JSON would
consider harmless whitespace/key-order changes different. Real APIs must also include
currency, destination, relevant API version and other fields that affect the operation.
Do not omit a field because it was inconvenient to hash.

## 2. Commit the local effect and result together

[advanced_idempotency.py](examples/advanced_idempotency.py) and
[the SQL schema](examples/advanced_db.py) implement the complete local boundary:

1. `claim()` uses the unique scope constraint to create a short-lived PENDING claim,
   or locks the existing record and makes the decision in the table above.
2. `complete_local()` locks that claim, verifies generation, pending state, live lease
   and request meaning, then inserts the payment row.
3. In that **same transaction**, it writes DONE, response status 201 and response body.
   The commit makes both effect and replay result visible together.

```mermaid
sequenceDiagram
  participant C as Client with key K
  participant A as API owner generation 1
  participant D as PostgreSQL
  C->>A: POST amount 100, key K
  A->>D: create scoped PENDING claim; commit
  A->>D: lock claim; verify generation + meaning
  A->>D: INSERT payment amount 100
  A->>D: save 201 response; set DONE
  A->>D: COMMIT effect and result together
  Note over C,A: Response connection is lost
  C->>A: retry same key and amount
  A->>D: lookup scoped DONE record
  D-->>A: saved 201 and same payment ID
  A-->>C: replay stored result
```

There is no arbitrary `execute()` callback between a committed claim and an independent
result update. Such a callback could commit elsewhere, making “effect happened but
result missing” unavoidable. Here, the local payment primary key is the operation ID,
and the operation row lock protects its effect/result transaction. PostgreSQL
[row locks](https://www.postgresql.org/docs/17/explicit-locking.html) keep competing
completion/takeover transactions from crossing that boundary concurrently.

The earlier claim transaction can survive even if execution never starts. That is safe:
a replacement can take over after lease expiry. If the process dies after inserting
the payment but before saving the result, PostgreSQL rolls back both uncommitted changes.
The integration test kills a child with `os._exit(17)` at exactly this point and checks
that zero payment rows survived before reclaiming the operation.

A database commit reply can itself be lost. Retry with the same scoped key and inspect
its durable state; do not infer rollback merely from a client-side connection error.
The stored result resolves the ambiguity after connectivity returns.

## 3. Expiry requires a new owner generation

A lease is permission to try work for a bounded time, not a permanent lock. An old worker
can pause long enough for its lease to expire, then resume after another worker takes
over. Checking only the row ID at completion would let the old worker overwrite the
new response. Every takeover increments `generation`; completion checks it under lock.

```mermaid
sequenceDiagram
  participant A as Owner A generation 1
  participant D as Operation row
  participant B as Owner B generation 2
  A->>D: claim K; lease expires at T
  Note over A,D: A pauses beyond T
  B->>D: lock expired K; generation becomes 2
  A->>D: complete with generation 1
  D-->>A: stale owner rejected before effect
  B->>D: complete with generation 2
  D->>D: payment + response commit atomically
  D-->>B: 201 stored result
```

A live lease check prevents an expired owner from starting completion even if nobody
has taken over yet. Once completion holds the row lock, a competing claimant must wait;
the short effect/result transaction cannot be overtaken midway. Keep that transaction
short and bound database lock/statement timeouts in production. Do not perform network
calls while holding it.

Generation fencing protects this database boundary. It cannot stop a remote HTTP effect
unless the provider honors a corresponding identity or fencing contract. A generation
number in your own table is not a universal distributed lock.

## 4. Run the local endpoint and failure fixtures

From `examples/`, with the environment from Part 9:

```bash
docker compose -p advanced-notes-repair -f advanced_compose.yaml up -d --wait
.venv/bin/python advanced_db.py
.venv/bin/python -m pytest -q advanced_test_postgres.py
.venv/bin/uvicorn advanced_idempotency_app:app --host 127.0.0.1 --port 8088
```

In another terminal, repeat the first command with the same body and key, then change
the amount:

```bash
curl -i -X POST http://127.0.0.1:8088/payments \
  -H 'Authorization: Bearer local-demo' -H 'Idempotency-Key: purchase-1' \
  -H 'Content-Type: application/json' -d '{"amount":100}'
curl -i -X POST http://127.0.0.1:8088/payments \
  -H 'Authorization: Bearer local-demo' -H 'Idempotency-Key: purchase-1' \
  -H 'Content-Type: application/json' -d '{"amount":100}'
curl -i -X POST http://127.0.0.1:8088/payments \
  -H 'Authorization: Bearer local-demo' -H 'Idempotency-Key: purchase-1' \
  -H 'Content-Type: application/json' -d '{"amount":200}'
```

Expect two 201 responses with the same payment ID, then 422. Missing authorization
returns 401 before record access. `local-demo` maps to a fixed laboratory tenant;
production must resolve tenant from verified identity, never a caller-supplied free-text
header. Amount is an integer in the product's documented unit; the fixture validates
positive bounds and rejects extra fields. This is a local payment ledger, not a complete
financial API or integration with a payment processor.

The synchronous FastAPI endpoint runs psycopg work in the framework's threadpool. It
uses one connection/transaction per storage operation; an async endpoint should use an
async database driver or bounded thread offload rather than blocking the event loop.
Map database outage to a sanitized availability response in the production exception
boundary, and leave an uncertain operation eligible for lookup/recovery.

The test suite uses real PostgreSQL barriers/connections for concurrent identical calls,
changed-body rejection, tenant key reuse, expired-owner takeover, stale completion and
process loss between local effect and response storage. It asserts exactly one effect
and a stable replay, not just that an `INSERT` returned a row.

## 5. Remote effects need a provider identity and recovery path

For a card network, your database cannot atomically commit the remote charge. Keep a
durable PENDING operation, derive a stable provider key from its authorized scope, call
the provider with that key, and reconcile an ambiguous result through the provider's
supported idempotency/lookup contract. Only then record the durable response. An outbox
can reliably schedule this work; it does not make the remote side effect atomic by itself.

The runnable source provides this derivation:

```python
# Callable helper in advanced_idempotency.py; no provider API call is implied.
remote_key = provider_key(tenant, 'POST /payments', client_key)
```

The helper hashes a namespace, tenant, endpoint and client key. It does **not** include
owner generation: generation 2 is recovering the same remote operation as generation
1, so both must use the same provider identity. It also avoids putting email addresses
or other sensitive identifiers in provider keys. Preserve the derived key and provider
operation ID durably; changing namespaces during rollout can accidentally create a new
remote operation for an old pending request.

Forwarding the raw client key alone can collide across tenants if your service shares
one provider account. Forwarding a fresh key after timeout creates a new operation.
Forwarding a stable key to a provider which does not support deduplication provides no
guarantee at all. In that case use an authoritative lookup/reconciliation workflow or
require manual resolution of ambiguous effects; a local Redis lock cannot fix the
provider's missing contract.

### What's changing: provider idempotency contracts are versioned

Checked 2026-10-30: Stripe **API v1** stores the first status/body once execution begins,
including a 500, and permits keys to be pruned after they are at least 24 hours old.
Reusing a pruned key can execute again. Validation failures and concurrent conflicts
before endpoint execution do not create the same saved result. This is not an exact
24-hour expiry promise. [Stripe API v1 idempotency](https://docs.stripe.com/api/idempotent_requests).

Stripe **API v2** has different recovery semantics: a retry can complete failed or
partially failed work and return an updated response while avoiding repetition of
successful operations. Record the API namespace/version and follow that endpoint's
retry policy; do not teach “all providers forever replay the first error” as a general
rule. [Stripe API v2 overview](https://docs.stripe.com/api-v2-overview#idempotency).
The local example deliberately promises stored-response replay for its own DONE state.

## 6. Redis can accelerate lookup; it does not erase the guarantees

A short-TTL Redis-only `SET NX` example often drops tenant scoping, hash validation,
generation checks or response durability. Dropping any of those changes the API's
contract. Loss of a Redis reservation during failover can permit a duplicate effect;
“clients can retry” does not make that safe.

Keep PostgreSQL as the source of truth for this local financial effect. If a replay cache
is useful, key it by the same tenant/endpoint/operation identity, retain the request hash
and stored response semantics, and fall back to the durable record on a miss. Populate
it only from committed DONE records. Do not authorize from cached response possession,
and do not let cache expiry delete durable business identity.

A Redis-only implementation may be appropriate for a low-impact short-window action
whose product explicitly tolerates duplicates under state loss. It still needs atomic
scope/hash/owner comparisons, bounded payloads and a documented failover/retention policy.
This lesson does not provide a weaker lock-only variant under the same payment guarantee.

## 7. Retry, retention and operation policy

The client must persist the same logical key across bounded retries. GET/HEAD are safe
HTTP methods, but retries still need total deadlines, rate/cost bounds and provider
contracts. PUT/DELETE idempotency describes intended effects, not identical response
codes. POST requires explicit server deduplication for safe repetition. The canonical
caller retries POST only when a key and an explicit provider-deduplication contract are
supplied; key presence alone is insufficient.

A 409 PENDING response invites bounded waiting/polling with the same key if the endpoint
contract says so. A key-meaning conflict is terminal for that request: correct the
client's operation tracking. A saved provider failure may replay indefinitely within
its retention window, so blindly increasing retry count cannot improve it. All retries
consume network, lookup, rate and possibly provider resources even when business effects
are deduplicated.

Retention must exceed the maximum retry/reconciliation horizon, and permanent business
uniqueness may need a separate durable natural key. Deleting an idempotency record means
a later identical key may look new. For payments, choose archival/tombstone semantics
that preserve the business guarantee rather than demonstrating automatic re-execution
as a harmless TTL feature. Keep response snapshots compatible with their original API
version or explicitly version the replay representation.

Monitor claim conflicts, replays, payload mismatches, pending age, lease takeovers,
stale completion rejections and remote-reconciliation backlog. Alert on old PENDING
operations even if request error rates look normal. Logs should include a safe operation
ID and generation, not card data, raw credentials or full sensitive request bodies.

Before production, verify:

- Authentication/tenant authorization precedes lookup; key/body limits prevent unbounded
  storage and hash work; per-tenant creation rates are bounded.
- Effect/result share the intended local transaction, or remote calls have a tested
  stable provider key and authoritative recovery path.
- Takeover increments generation; stale owners cannot mutate effects/results; database
  timeout settings fit the product deadline.
- Retention, backup/restore and migrations preserve operation identity and pending
  recovery. Test an old pending operation across a version rollout.
- Client retries are bounded, provider-specific and observable; duplicate effects are
  checked in the business ledger, not inferred from HTTP status alone.

## Recap

Idempotency binds an authorized operation identity to one request meaning and durable
outcome. Commit local effects with their replay result, fence replacement owners with
generations, and recover remote effects through the provider's actual deduplication
contract. A key or short-lived lock alone supplies none of those guarantees.

## Check yourself

<details><summary>Owner A expires, B takes generation 2, then A finishes. May A write the result by row ID?</summary>
No. Completion verifies the current generation under row lock before any effect. A's
stale generation cannot overwrite B or create an effect after losing ownership.
</details>

<details><summary>Why must a replacement owner reuse the remote provider key instead of adding generation 2?</summary>
It is recovering the same logical remote operation. Adding the generation changes
identity and can cause a second charge even though local ownership fencing is correct.
</details>

## Try it

Change the process-loss fixture to fail after the result commit but before returning to
the client. Predict whether reclaim should run. Retry the original tenant/endpoint/key
and assert it replays the saved result with one payment row. Then reuse the client key
under another tenant and explain why that is a distinct authorized operation.

Scaffold: in a child process call `complete_local(owner, 100)` and only then
`os._exit(17)`. In the parent fill in `assert claim(...).replay is _____` and assert the
payment count by operation ID is one.

Hint: the successful function return occurred after the transaction context committed,
even though the client never saw that result.

<details><summary>Reasoned solution</summary>
The assertion is `is not None`: the retry reads DONE and replays 201 with the original
payment ID. No takeover or second effect is needed. Another tenant's identical client
key has a different scoped identity; its independent payment is permitted after its own
authorization and validation.
</details>

**Previous:** [Token economics](10_llm_token_economics.md). **Back:** [learning map](README.md).
