# Webhook Consumer Design

> **Who this is for**: Teams receiving webhooks that must authenticate senders, absorb duplicates, and process events without request-time fragility. Assumes [Delivery Model](01_delivery_model_and_event_contracts.md).

> **Key insight**: A safe consumer authenticates and durably admits raw events before acknowledging them, then makes downstream effects idempotent.

---

## Run signed intake and recover a failed worker

The [lab files](../examples/webhook_inbox/) contain `app.py`, `webhook_security.py`,
`schema.sql`, `worker.py` and `test_lab.py`. Use only this disposable PostgreSQL database;
the test resets its tables and refuses a differently named database.

```bash
python -m venv /tmp/notes-webhook-env
source /tmp/notes-webhook-env/bin/activate
python -m pip install 'fastapi==0.162.0' 'httpx==0.28.1' asyncpg pytest
docker run --rm -d --name notes-webhook-lab -e POSTGRES_PASSWORD=local-lab-password -e POSTGRES_DB=webhook_lab -p 127.0.0.1:55439:5432 postgres:17
export DATABASE_URL='postgresql://postgres:local-lab-password@127.0.0.1:55439/webhook_lab'
export BILLING_WEBHOOK_SECRETS='local-test-only-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
# Wait until PostgreSQL is ready before running the test.
docker exec notes-webhook-lab pg_isready -U postgres
python -m pytest -q apis/examples/webhook_inbox
# Cleanup after the lab:
docker stop notes-webhook-lab
```

The test sends signed `evt_1`: 204 and one inbox row. A changed byte returns 401.
Two concurrent valid duplicates still leave one row. Before processing, the invoice effect
count is zero: acceptance has not completed the business work. The test then injects a
failure after the invoice update but before commit; both the effect and guard roll back.
Retry commits one effect, and replaying the worker leaves that count at one.

```mermaid
sequenceDiagram
 participant P as Billing producer
 participant API as Intake
 participant DB as PostgreSQL
 participant W as Worker
 P->>API: Signed evt_1 for inv_123
 API->>DB: Insert inbox and commit
 API-->>P: 204 accepted
 W->>DB: Lock receipt; insert effect guard; update invoice
 Note over W,DB: Crash before commit rolls back all three changes
 W->>DB: Retry same receipt; commit guard plus effect plus processed
```

The producer can stop once 204 arrives. Therefore the durable inbox takes responsibility
before that response, while the worker retains its own recovery path. This lab covers one
billing account and short local database effects. Remote effects require a transactional
outbox or a provider idempotency contract, as developed below.

The worker quarantines unsupported event schemas, unauthorized invoice identities and missing invoice rows with explicit reason codes. These terminal receipts no longer block the oldest-row selection; the regression queues a valid event behind a signed poison event and proves it still completes. A database outage remains retryable and rolls back the transaction. Quarantine requires an operator diagnosis and authorized replay after repair, not endless retries of unchanged bad input.

## 1. The Safe Ingress Pipeline

```text
HTTP request
  → enforce transport/body limits
  → read raw bytes
  → verify signature and timestamp over raw bytes
  → parse and validate event envelope
  → authorize expected producer/subscription/account
  → insert event into durable inbox with unique event ID
  → return 2xx quickly
  → worker claims inbox row
  → idempotent domain processing
  → processed or retry/dead-letter state
```

Do not perform slow business work, send emails, call dependencies, or hold a large transaction before acknowledgement. Provider timeouts create retries and duplicate pressure.

Return success only after the event is durably accepted under your contract. Enqueuing into an in-memory task is not durable.

---

## 2. Verify the Exact Raw Body

Cryptographic signatures are byte-sensitive:

```text
signed:   {"amount":4200,"currency":"EUR"}
changed:  {"currency": "EUR", "amount": 4200}
```

Both JSON objects have equivalent data but different bytes and signatures. Read the body once, cap it, verify it, then parse those same bytes. Framework body parsers or middleware that reserializes JSON before verification will break valid signatures.

Use the provider's official verification library where available. The next chapter provides a
complete **hash-based message authentication code (HMAC)** example that authenticates the exact
request bytes, plus rotation rules.

---

## 3. Durable Inbox and Deduplication

```sql
CREATE TABLE webhook_inbox (
    producer text NOT NULL,
    event_id text NOT NULL,
    event_type text NOT NULL,
    occurred_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL,
    state text NOT NULL DEFAULT 'received',
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz,
    last_error_code text,
    processed_at timestamptz,
    PRIMARY KEY (producer, event_id)
);
```

Insert with conflict handling:

```sql
INSERT INTO webhook_inbox (
    producer, event_id, event_type, occurred_at, payload
) VALUES (
    :producer, :event_id, :event_type, :occurred_at, CAST(:payload AS jsonb)
)
ON CONFLICT (producer, event_id) DO NOTHING;
```

Return the same successful acknowledgement for a valid duplicate. If duplicates receive an error, the producer may retry indefinitely.

Scope uniqueness by provider/account when event IDs are not globally unique. Verify the documented identity property instead of assuming it.

---

## 4. Complete FastAPI Ingress

This endpoint uses PostgreSQL as a durable inbox. It imports the verifier implemented in [Signatures, Security, and SSRF](04_signatures_security_and_ssrf.md).

```python
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import asyncpg
from fastapi import FastAPI, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .webhook_security import VerificationError, verify_webhook


MAX_WEBHOOK_BYTES = 256 * 1024
SIGNING_SECRETS = [
    secret.encode("utf-8")
    for secret in os.environ["BILLING_WEBHOOK_SECRETS"].split(",")
]


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(min_length=1, max_length=200)
    type: str = Field(min_length=1, max_length=200)
    schema_version: int = Field(ge=1)
    occurred_at: datetime
    producer: str
    data: dict[str, Any]


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(
        dsn=os.environ["DATABASE_URL"],
        min_size=1,
        max_size=10,
        command_timeout=5.0,
    )
    try:
        yield
    finally:
        await app.state.pool.close()


app = FastAPI(lifespan=lifespan)


@app.post("/webhooks/billing", status_code=204)
async def receive_billing_webhook(request: Request) -> Response:
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            if int(declared_length) > MAX_WEBHOOK_BYTES:
                return Response(status_code=413)
        except ValueError:
            return Response(status_code=400)

    chunks: list[bytes] = []
    received_bytes = 0
    async for chunk in request.stream():
        received_bytes += len(chunk)
        if received_bytes > MAX_WEBHOOK_BYTES:
            return Response(status_code=413)
        chunks.append(chunk)
    raw_body = b"".join(chunks)

    message_id = request.headers.get("webhook-id")
    timestamp = request.headers.get("webhook-timestamp")
    signature = request.headers.get("webhook-signature")

    try:
        verify_webhook(
            body=raw_body,
            message_id=message_id,
            timestamp=timestamp,
            signature_header=signature,
            secrets=SIGNING_SECRETS,
        )
    except VerificationError:
        return Response(status_code=401)

    try:
        event = EventEnvelope.model_validate_json(raw_body)
    except ValidationError:
        return Response(status_code=422)

    if event.id != message_id or event.producer != "billing":
        return Response(status_code=400)

    payload = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
    async with request.app.state.pool.acquire() as connection:
        await connection.execute(
            """
            INSERT INTO webhook_inbox (
                producer, event_id, event_type, occurred_at, payload
            ) VALUES ($1, $2, $3, $4, $5::jsonb)
            ON CONFLICT (producer, event_id) DO NOTHING
            """,
            event.producer,
            event.id,
            event.type,
            event.occurred_at,
            payload,
        )

    return Response(status_code=204)
```

Do not trust a compressed request's `Content-Length` as the decompressed size. Prefer disabling content encoding for webhook endpoints or enforce a streaming decompressed limit at the trusted edge/application.

The database command timeout and pool are deliberately bounded. If durable storage is unavailable, return failure so the producer retries; do not acknowledge and lose the event.

---

## 5. Inbox Worker

The lab worker holds `FOR UPDATE SKIP LOCKED` only for a short database transaction.
It inserts the effect guard with `RETURNING event_id`, updates the invoice **only if that
insert returned a row**, and marks the receipt processed in the same transaction. Another
worker either skips the locked row or sees the committed processed state. An exception
rolls back the guard, effect and completion together.

Long or remote work uses a persisted owner/lease/generation and short claim transaction,
as in the producer lesson. It cannot hold this local transaction across network I/O.

Handler design:

- Route by exact event type and supported schema version.
- Treat payload as untrusted even after signature verification.
- Load internal objects through tenant/account scope.
- Prefer state assignment/upsert over non-idempotent increments.
- Record provider event ID with each resulting side effect.
- Use an internal outbox for emails/messages triggered by the event.
- Mark processed in the same transaction as local state changes where possible.

```sql
INSERT INTO processed_provider_events (producer, event_id, processed_at)
VALUES (:producer, :event_id, now())
ON CONFLICT DO NOTHING
RETURNING event_id;
```

The caller must branch on the returned row before applying any effect. A uniqueness constraint without that branch still lets a duplicate run the following code. See the complete transactional branch in [worker.py](../examples/webhook_inbox/worker.py).

---

## 6. Ordering and Authoritative State

Do not assume arrival order. Options:

- Ignore a stale version/sequence already superseded locally.
- Partition processing by subject while accepting gaps.
- Buffer briefly while waiting for a missing sequence, then reconcile.
- Fetch current provider state and treat webhook as an invalidation hint.

For payments, subscriptions, or access rights, retrieving the authoritative object is often safer than applying a delta from a possibly delayed event.

```text
receive invoice.paid for inv_123
  → deduplicate event
  → GET provider invoice inv_123 with authenticated client
  → set local projection to returned version/status
```

Still authenticate and store the webhook; otherwise an attacker can force arbitrary provider API reads.

---

## 7. Poison Events and Internal Retry

Separate producer delivery retry from consumer processing retry. Once durably accepted, your worker owns processing failures.

Classify:

- Unsupported/invalid schema: terminal quarantine and alert
- Missing dependency/transient timeout: retry with backoff
- Domain conflict: reconcile/current-state policy
- Code bug: bounded retries, quarantine, fix and replay
- Permanent authorization/configuration: terminal with operator action

Keep raw or normalized payload only for the required retention and protect it as customer data. Redact exception logs and cap last-error text.

---

## 8. Consumer Checklist

- Body limits apply before expensive parsing.
- Signature and timestamp cover exact raw bytes.
- Event identity and expected producer/account agree with the route/secret.
- Durable inbox insert precedes `2xx` acknowledgement.
- Duplicate valid events return success.
- Worker effects are idempotent and transactionally guarded.
- Ordering assumptions have a sequence/reconciliation strategy.
- Unsupported and poison events become visible quarantine, not infinite retry.
- Payload retention, encryption, and access follow data classification.

---


## Recap

- Verify the exact bytes before parsing and durable inbox admission.
- A committed receipt permits 204 even though processing has not happened yet.
- The effect guard, local effect and completion share one transaction and rollback together.

## Check yourself

**two verified copies of evt_1 arrive together; what prevents two inbox rows?**

<details><summary>Reasoned answer</summary>

PostgreSQL enforces PRIMARY KEY(producer,event_id), and ON CONFLICT makes the losing insert a successful no-op before 204.

</details>

**The guard insert conflicts but the handler still increments a counter. Is the guard sufficient?**

<details><summary>Reasoned answer</summary>

No. Branch on INSERT RETURNING; only its winner may perform the guarded effect. A constraint by itself does not skip later statements.

</details>

**Try it:** In examples/webhook_inbox/test_lab.py, inject a worker failure after the invoice update but before commit. Leave the expected effect_count and processed-event row count blank.

Hint: The effect, deduplication guard and completion marker share one transaction.

<details><summary>Solution</summary>
Both counts remain zero after rollback. A later worker attempt commits exactly one effect and one guard, and replay does not increment either.
</details>

**Next**: [Webhook Signatures, Security, and SSRF](04_signatures_security_and_ssrf.md)
