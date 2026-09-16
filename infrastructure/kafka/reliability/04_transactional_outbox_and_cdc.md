# A Polling Outbox Turns Two Writes into One Recoverable Handoff

> **Who this is for**: services that update a database and publish a corresponding event.

## The dual-write gap

`COMMIT order` followed by `publish order.created` can crash between calls, leaving durable business
state with no event. Reversing the calls creates an event for a database change that may roll back.

---

## 1. Store business state and intent in one database transaction

```text
BEGIN → insert orders row → insert outbox(event_id, payload, unpublished) → COMMIT
                                      ↓
                         polling relay publishes to Kafka
```

The relay may publish twice around its own crash, so consumers still deduplicate by `event_id`.
This note completes the polling model. [CDC](06_cdc_outbox_relay.md) has a different actor and
checkpoint and therefore owns a separate production path.

PostgreSQL can own the business row and publication intent in one commit:

```sql
CREATE TABLE orders (
    order_id text PRIMARY KEY,
    total_minor bigint NOT NULL CHECK (total_minor >= 0)
);

CREATE TABLE outbox_events (
    event_id uuid PRIMARY KEY,
    aggregate_id text NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);

CREATE INDEX outbox_unpublished ON outbox_events (created_at)
WHERE published_at IS NULL;
```

The application uses parameters and one database transaction; no SQL string contains event data:

```python
import json
import uuid


def create_order(conn, order_id: str, total_minor: int) -> str:
    event_id = str(uuid.uuid4())
    payload = {"event_id": event_id, "order_id": order_id, "total_minor": total_minor}
    with conn.transaction():
        conn.execute(
            "INSERT INTO orders (order_id, total_minor) VALUES (%s, %s)",
            (order_id, total_minor),
        )
        conn.execute(
            """INSERT INTO outbox_events
               (event_id, aggregate_id, event_type, payload)
               VALUES (%s, %s, %s, %s::jsonb)""",
            (event_id, order_id, "order.created", json.dumps(payload)),
        )
    return event_id
```

After commit, either both rows exist or neither does. Querying `outbox_events` for the returned ID
is the success signal; an order with no matching outbox row means the writes escaped the shared
transaction.

---

## 2. Ownership decides between polling and CDC

Polling is simple and application-owned but adds query load and cleanup. CDC scales integration and
captures ordered database changes but introduces connector, log-retention, and schema-operational
dependencies.

A polling relay claims a small batch with `FOR UPDATE SKIP LOCKED`, publishes each event using
`aggregate_id` (`ord-42`) as the Kafka key, carries `event_id` inside the envelope for duplicate
collapse, waits for the broker acknowledgment, and only then sets
`published_at`. Keep claimed rows locked only for a bounded batch:

```text
t0  relay-a claims evt-101 (published_at=NULL)
t1  Kafka acknowledges evt-101
t2  relay-a crashes before UPDATE               → row remains unpublished
t3  relay-b claims and publishes evt-101 again  → possible duplicate, no loss
t4  relay-b sets published_at and commits        → cleanup may later archive the row
```

The key choice preserves the order of successive events for one aggregate:

```text
evt-101(order_id=ord-42, order.created) ┐
                                        ├─ key ord-42 → the same Kafka partition, in publish order
evt-109(order_id=ord-42, order.paid)    ┘
```

Keying by unique `event_id` would spread these two events independently and lose that ordering
relationship. `event_id` and `aggregate_id` solve different problems: deduplication and routing.

### Claim, acknowledge, mark, and reconcile

One relay transaction handles a bounded row like this:

```sql
BEGIN;
SELECT event_id, aggregate_id, event_type, payload
FROM outbox_events
WHERE published_at IS NULL
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 10;
-- publish each row with key=aggregate_id and wait for its broker delivery callback
UPDATE outbox_events SET published_at = now() WHERE event_id = $1;
COMMIT;
```

The database lock prevents two polling relays from claiming the same row concurrently, but it does
not make Kafka and PostgreSQL atomic. A crash after Kafka acknowledgment and before the update still
duplicates the record, which is why the consumer-effect store owns the `event_id` uniqueness
constraint. Do not hold a large batch transaction open while a broker is unhealthy: cap the batch,
delivery deadline, and lock timeout.

A reconciliation job compares old unpublished rows with the relay's delivery errors. Its first
action is to retry publication, not to mark a row published. Alert on the age of the oldest
unpublished row; row count alone misses one permanently stuck old event in a low-volume service.

The duplicate is intentional evidence of an uncertain acknowledgment boundary. A consumer's
unique `event_id` constraint collapses both deliveries to one effect. Retain published rows through
the maximum reconciliation window; deleting them immediately removes the evidence needed to
compare database intent with Kafka output.

**Success signal:** crash after database commit and before publish; the relay later emits the event.
Then crash after publish and verify a duplicate causes one downstream effect.

The collection executes those boundaries in a disposable PostgreSQL database. Keep the Kafka
quick-start broker running, then start PostgreSQL:

```bash
docker run --rm --name kafka-notes-postgres \
  -e POSTGRES_PASSWORD=postgres -p 55439:5432 -d postgres:17
until docker exec kafka-notes-postgres pg_isready -U postgres; do sleep 1; done
```

From `infrastructure/kafka/examples/python`, run the checked-in integration test and clean up:

```bash
uv sync --dev
uv run pytest -q tests/integration/test_outbox.py
docker stop kafka-notes-postgres
```

[`test_outbox.py`](../examples/python/tests/integration/test_outbox.py) creates an isolated schema
and performs four observed transitions:

1. An exception between the `orders` and `outbox_events` inserts rolls both rows back.
2. The successful transaction leaves exactly one domain row and one related outbox row.
3. A simulated process death after Kafka acknowledgment rolls back `published_at`, so restart claims
   and publishes the same event again with key `ord-42`.
4. The consumer sees two envelopes with one `event_id`; the durable effect store records one effect.

**Success signal:** `1 passed`. Connection refusal on port `55439` means PostgreSQL did not become
ready; a timeout creating the Kafka topic means the quick-start broker is not running.

These four observations distinguish atomic database intent, at-least-once relay delivery, and
downstream duplicate collapse. A query that checks only `published_at` proves none of the other two.

> **Key insight**: the outbox does not make database and Kafka atomic; it records a durable promise
> inside the database so publication can be retried until observed.

---

## 3. What breaks, and when not to use an outbox

⚠️ Deleting outbox rows before confirmed publication turns relay failure into permanent event loss.

Do not add an outbox when Kafka is already the authoritative input and all outputs remain inside one
Kafka transaction. Use the smaller atomic boundary.

---

**Next**: use [CDC Outbox Relay](06_cdc_outbox_relay.md) when database-log capture is justified, or
go directly to [Testing Kafka Services](05_testing_kafka_services.md) for a polling relay.
