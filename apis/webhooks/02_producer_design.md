# Webhook Producer Design

> **Who this is for**: Teams building outbound webhook infrastructure that must survive transactions, endpoint failures, and fleet scale. Assumes [Delivery Model and Event Contracts](01_delivery_model_and_event_contracts.md).

> **Key insight**: A webhook producer owns a durable delivery state machine, not an HTTP call; transaction gaps and retry classification determine whether events disappear or duplicate.

---

## 1. Producer Responsibilities

A producer owns more than `httpx.post()`:

```text
event creation → subscription match → durable delivery → scheduling
→ safe endpoint resolution → signing → HTTP attempt → classification
→ retry/dead-letter/replay → customer visibility and support
```

Run this path outside the business request whenever possible. A slow customer endpoint must not hold open checkout, billing, or account updates.

---

## 2. Subscription Model

A subscription needs:

```text
id
owner tenant/account
HTTPS endpoint URL
selected event types
status: pending_verification | active | paused | disabled
signing key reference and rotation state
payload/schema version
created/updated metadata
failure counters and last delivery state
```

Subscription API controls:

- Authenticate and authorize owner/administrator.
- Allow only known event types and minimum required events.
- Validate URL syntax and run the **server-side request forgery (SSRF)** policy: a customer-controlled
  callback URL must not let the worker reach internal or cloud-metadata services. See
  [Signatures, Security, and SSRF](04_signatures_security_and_ssrf.md).
- Verify endpoint ownership with a challenge or first signed test event where appropriate.
- Return the signing secret once, then store it encrypted or in a secret manager.
- Audit endpoint, event selection, key rotation, pause, and deletion changes.
- Revalidate DNS/egress policy on every connection, not only registration.

Avoid placing credentials in callback URLs.

---

## 3. Transactional Outbox

The dual-write bug occurs when business state commits but publishing fails, or publishing occurs before the transaction later rolls back.

```text
❌ commit invoice ── process crashes ── webhook event never recorded
❌ send webhook ── database rollback ── consumer sees a fact that never committed
```

Write business state and an outbox event in one database transaction:

```sql
BEGIN;

WITH changed AS (
    UPDATE invoices
    SET status = 'paid', paid_at = now()
    WHERE tenant_id = :tenant_id
      AND id = :invoice_id
      AND status = 'open'
    RETURNING id
)
INSERT INTO webhook_events (
    id, tenant_id, event_type, schema_version, subject, occurred_at, payload
)
SELECT :event_id, :tenant_id, 'invoice.paid', 1,
       :subject, now(), CAST(:payload AS jsonb)
FROM changed;

COMMIT;
```

If the invoice was already paid or belongs to another tenant, `changed` has no row and no event is inserted. A real state transition is the source of the event, not merely receiving a command.

An outbox relay reads committed events and creates per-subscription deliveries. Make that step idempotent with a unique constraint:

```sql
CREATE UNIQUE INDEX webhook_deliveries_event_subscription_uq
ON webhook_deliveries (event_id, subscription_id);
```

The relay can run more than once without creating duplicate logical deliveries. HTTP attempts may still duplicate and keep the same event/delivery identity.

---

## 4. Delivery State Machine

```text
pending → attempting
             ├── 2xx → delivered
             ├── transient → retry_scheduled → attempting
             ├── terminal → failed
             └── exhausted → dead_letter

paused subscription holds pending/retry deliveries by policy
manual replay creates a new attempt, not a new business event
```

Persist at least:

- Event and subscription IDs
- Delivery ID and current state
- Attempt count, next attempt time, first/last attempt time
- Last response status, bounded/redacted response diagnostic
- Failure category and final reason
- Request duration and resolved destination metadata useful for audit

Do not store full customer response bodies indiscriminately. They may contain secrets or attacker-controlled high-volume content. Cap, sanitize, and restrict access.

---

## 5. Scheduler and Worker Concurrency

Claim due rows atomically:

```sql
SELECT id
FROM webhook_deliveries
WHERE state IN ('pending', 'retry_scheduled')
  AND next_attempt_at <= now()
ORDER BY next_attempt_at, id
FOR UPDATE SKIP LOCKED
LIMIT :batch_size;
```

Update claimed rows to an attempting state/lease within the transaction, then perform network I/O after commit. A lease timeout recovers work from crashed workers.

Partition or fairly schedule by destination/tenant so one failed endpoint cannot consume every worker. Apply:

- Global worker concurrency
- Per-tenant and per-destination concurrency
- Per-destination rate limit
- Connection pool limits
- Short connect and response-header/body limits
- Circuit/open-endpoint suppression with scheduled probes

Never hold a database transaction open during the customer HTTP request.

---

### A lease survives the claim transaction

For delivery `del_A`, W1 commits `owner=W1, generation=4, lease_until=10:00:30` before
sending HTTP. The row lock is gone after commit; the persisted lease prevents W2 from
starting another ordinary attempt during that interval. If W1 dies, W2 may claim at
10:00:31, atomically incrementing the generation to 5.

```mermaid
sequenceDiagram
 participant W1 as W1 generation 4
 participant DB as Delivery row del_A
 participant W2 as W2 generation 5
 participant C as Consumer inbox
 W1->>DB: Claim until t30; commit
 W1->>C: Signed evt_1 HTTP attempt
 Note over W1: Stops before recording result
 W2->>DB: t31 reclaim expired lease; generation 5
 W2->>C: Retry same evt_1
 C-->>W2: 204; one durable receipt
 W1->>DB: Late completion WHERE generation=4
 DB-->>W1: Zero rows; stale completion refused
```

The conditional completion must include delivery ID, owner, generation and active lease
under one transaction. The same check protects renewal. W1 may still have reached the
consumer before losing ownership: a lease fences local state writes, not an HTTP side
effect. Stable signed event identity and the consumer's durable inbox handle that ambiguity.

With 20 global slots and a limit of two per destination, one failing destination occupies
at most two slots while others proceed. Pick a due destination fairly, acquire its bounded
slot, and only then claim a short batch for it; claiming thousands of rows before capacity
is available strands leases in a local queue. On a destination's 429, store its next eligible
time and release the slot. A delayed retry does not hold worker capacity while sleeping.

## 6. HTTP Attempt Contract

Send exact signed bytes with explicit metadata:

```http
POST /hooks/billing HTTP/1.1
Host: consumer.example
Content-Type: application/json
User-Agent: Example-Webhooks/1
Webhook-Id: evt_01J8Q9M4D7...
Webhook-Timestamp: 1784716200
Webhook-Signature: v1,...

{"id":"evt_01J8Q9M4D7","type":"invoice.paid","schema_version":1,"occurred_at":"2026-07-22T10:30:00Z","producer":"billing","subject":"invoice/inv_123","data":{"invoice_id":"inv_123","amount_minor":4200,"currency":"EUR"}}
```

Recommended request behavior:

- HTTPS only, verified certificate and hostname.
- No automatic redirects, or an equally strict revalidation policy for every redirect hop.
- Explicit connect/write/read/pool timeouts.
- Fixed maximum response bytes; the response body is normally diagnostic only.
- Stable event/delivery headers and content type.
- Signature computed over the exact bytes transmitted.

Interpret responses under a published policy. A reasonable default is:

| Outcome | Producer action |
|---------|-----------------|
| Any documented `2xx` | Mark accepted/delivered |
| Network timeout/reset | Retry within policy; outcome may be ambiguous |
| `408`, `429`, selected `5xx` | Retry with bounded backoff; honor safe `Retry-After` policy |
| Other `4xx` | Usually terminal/configuration failure; provider policy may allow limited retries |
| `410 Gone` | Candidate to disable endpoint after explicit documented policy |

Do not assume every provider follows the same response policy. Publish yours.

---

## 7. Retry, Dead Letter, and Replay

Use exponential backoff with jitter, capped by maximum delivery age. A typical schedule spreads attempts from seconds to hours; the correct window follows the business need and capacity model.

After exhaustion:

- Keep a dead-letter record for a documented retention period.
- Notify endpoint owners through a separate channel.
- Expose delivery/attempt history and safe diagnostics.
- Allow authorized replay of selected failures.
- Preserve original event ID/body; generate new attempt identity and signature timestamp.

Manual replay must not bypass current endpoint security checks, subscription ownership, rate limits, or payload access policy.

---

## 8. Event and Schema Evolution

- Pin a subscription or endpoint to a documented payload version, or version event types explicitly.
- Make additive fields safe and instruct consumers to ignore unknowns.
- Never change units/meaning under the same field and version.
- Preserve the original event representation for replay; do not silently reserialize an old event using today's schema.
- Test old payloads through current signing and delivery code.

If sensitive fields become newly available, require an explicit subscription/version upgrade rather than adding them to every existing endpoint.

---

## 9. Producer Checklist

- Event creation shares a transaction with the business change.
- Delivery creation and worker claim are idempotent/leased.
- Customer endpoints never block the business request.
- SSRF policy and TLS verification run for every attempt.
- Queues, connections, retries, response sizes, and diagnostics are bounded.
- Fairness prevents one tenant/destination from exhausting the fleet.
- Replay preserves event identity and historical schema.
- Owners can inspect, test, rotate, pause, and diagnose safely.

---


## Recap

- Only a committed business transition should create its outbox event.
- Delivery uniqueness prevents relay restart from inventing another logical delivery.
- Persisted lease generations protect local completion while consumer deduplication protects repeated HTTP attempts.

## Check yourself

**the relay restarts after creating del_A for evt_1 but before advancing its cursor; how many logical deliveries should exist?**

<details><summary>Reasoned answer</summary>

One for that event/subscription, because the unique pair rejects a second delivery; its HTTP attempts may still repeat.

</details>

**W1 returns 204 after W2 reclaimed generation 5. May W1 mark the row delivered?**

<details><summary>Reasoned answer</summary>

Only a current owner with matching generation and valid lease may finish. W1’s stale conditional update must affect zero rows.

</details>

**Next**: [Webhook Consumer Design](03_consumer_design.md)
