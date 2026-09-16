# A Schema Registry Makes Contract Evolution an Enforced Deployment Gate

> **Who this is for**: teams whose Kafka contracts cross independently deployed applications.

## Register one contract and reject one breaking change

Assume a Schema Registry at `http://localhost:8081` and a subject named
`orders.events.v1-value`. A **subject** is the versioned name under which the registry stores a
schema. **Avro** is a schema-driven binary serialization format. Save this Avro schema as
`order-created-v1.avsc`:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.orders",
  "fields": [
    {"name": "event_id", "type": "string"},
    {"name": "order_id", "type": "string"},
    {"name": "total_minor", "type": "long"}
  ]
}
```

Set the subject to backward-transitive compatibility, then register v1:

```bash
curl --fail-with-body -X PUT http://localhost:8081/config/orders.events.v1-value \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  -d '{"compatibility":"BACKWARD_TRANSITIVE"}'

jq -Rs '{schema: .}' order-created-v1.avsc | \
  curl --fail-with-body -X POST \
    http://localhost:8081/subjects/orders.events.v1-value/versions \
    -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
    --data-binary @-
```

The success signal is a response containing an integer schema `id`. An HTTP `409` means the new
schema violates the subject's compatibility policy; a `200` from the compatibility endpoint or an
ID from registration is the gate, not a local parse alone. The complete endpoint behavior is in
the [Schema Registry API reference](https://docs.confluent.io/platform/current/schema-registry/develop/api.html).

---

## 1. A shared ID prevents consumers from guessing the writer schema

Plain JSON bytes do not identify which contract produced them. During a rolling deployment, a
consumer can parse valid JSON while interpreting the wrong generation. Registry-aware serializers
write a schema identifier with the record; deserializers fetch that exact writer schema and resolve
it against their reader schema.

The registry ID and the subject version answer different questions: the ID identifies schema
content on the wire, while the subject version records that contract's evolution. Do not embed the
subject version as if it were the wire ID.

> **Core:** configure serializers for the same subject-naming strategy in every language, and keep
> automatic registration disabled in production unless producer identities are explicitly allowed
> to evolve contracts.

---

## 2. Compatibility checks structural evolution before deployment

Adding an optional field with a default lets a new reader consume retained v1 records:

```bash
jq '.fields += [{"name":"coupon_code","type":["null","string"],"default":null}]' \
  order-created-v1.avsc > order-created-v2.avsc
```

The generated field is:

```json
{"name": "coupon_code", "type": ["null", "string"], "default": null}
```

Before registration, submit the candidate against all supported versions:

```bash
jq -Rs '{schema: .}' order-created-v2.avsc | \
  curl --fail-with-body -X POST \
    'http://localhost:8081/compatibility/subjects/orders.events.v1-value/versions?verbose=true' \
    -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
    --data-binary @-
```

The additive schema returns `{"is_compatible":true}`. Create a breaking candidate by changing the
existing field type, then send it to the same compatibility endpoint:

```bash
jq '(.fields[] | select(.name == "total_minor").type) = "string"' \
  order-created-v1.avsc > order-created-breaking.avsc
```

That candidate returns `{"is_compatible":false}` with diagnostics. The registry protects wire
structure; the semantic test in [Event Contracts](01_event_contracts_and_schema_evolution.md) must
still prove that “minor units” did not silently become major units.

Register the compatible v2 before running the client trace:

```bash
jq -Rs '{schema: .}' order-created-v2.avsc | \
  curl --fail-with-body -X POST \
    http://localhost:8081/subjects/orders.events.v1-value/versions \
    -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
    --data-binary @-
```

> **Key insight**: a registry can prove that readers can decode bytes; only contract tests can
> prove that independently deployed services assign the same meaning to those bytes.

---

## 3. Trace the schema ID from object to bytes and back

Save this as `schema_round_trip.py` beside both `.avsc` files. It invokes the same registry-aware
serializer and deserializer used around Kafka records, but keeps the bytes in files so the recovery
drill can prove that a fresh registry understands records created by the old one.

```python
import os
from pathlib import Path

from confluent_kafka.schema_registry import SchemaRegistryClient, topic_subject_name_strategy
from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext

registry = SchemaRegistryClient({"url": os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081")})
topic = "orders.events.v1"
context = SerializationContext(topic, MessageField.VALUE)
v1_schema = Path("order-created-v1.avsc").read_text()
v2_schema = Path("order-created-v2.avsc").read_text()
schemas = {"oldest": v1_schema, "newest": v2_schema}
records = {
    "oldest": {"event_id": "evt-101", "order_id": "ord-42", "total_minor": 2590},
    "newest": {
        "event_id": "evt-102", "order_id": "ord-43", "total_minor": 3100,
        "coupon_code": "AUTUMN10",
    },
}

wire_dir = Path(os.getenv("WIRE_DIR", "wire"))
read_only = os.getenv("READ_ONLY") == "1"
wire_dir.mkdir(exist_ok=True)

if not read_only:
    for name, schema in schemas.items():
        serializer = AvroSerializer(
            registry,
            schema,
            conf={
                "auto.register.schemas": False,
                "subject.name.strategy": topic_subject_name_strategy,
            },
        )
        encoded = serializer(records[name], context)
        if encoded[0] != 0:
            raise AssertionError("unexpected Schema Registry framing")
        schema_id = int.from_bytes(encoded[1:5], "big")
        (wire_dir / f"{name}.bin").write_bytes(encoded)
        print("wrote", name, "schema-id", schema_id, "bytes", len(encoded))

# Supplying v2 here makes it the reader schema. For oldest.bin, Avro resolves the exact v1 writer
# schema fetched by its embedded ID against v2 and supplies coupon_code's default.
deserializer = AvroDeserializer(registry, v2_schema)
for name in schemas:
    encoded = (wire_dir / f"{name}.bin").read_bytes()
    schema_id = int.from_bytes(encoded[1:5], "big")
    decoded = deserializer(encoded, context)
    print("read", name, "writer-id", schema_id, "coupon", decoded["coupon_code"])
```

Run the trace only after the v1 and v2 registrations have succeeded:

```bash
uv run --with 'confluent-kafka[avro,schemaregistry]' python schema_round_trip.py
```

**Success signal:** two `wrote` lines show the IDs found in bytes 1–4, and two `read` lines repeat
those writer IDs. The oldest record prints `coupon None`; the newest prints `coupon AUTUMN10`.
Byte 0 is the framing marker, bytes 1–4 are the big-endian schema ID, and the remaining bytes are
the Avro payload. On read, that ID selects the exact writer schema; Avro then resolves it against
the supplied v2 reader schema. A `404`/schema-not-found error proves why substituting “latest
subject version” cannot recover a missing writer ID. The Python client API and reader-schema
behavior are documented in the
[Confluent Python client reference](https://docs.confluent.io/platform/current/clients/confluent-kafka-python/html/index.html).

This is a Schema Registry integration path, not a local-only test. It was not executed for this
note unless a registry was actually available at the configured URL; Python parsing alone does not
establish the printed signals.

---

## 4. Restore into a fresh registry without changing wire IDs

Export subjects, versions, compatibility settings, references, and ID mappings with the Kafka data
they describe. Restore them before consumers resume. Re-registering schemas in a fresh registry can
assign different IDs, so copied records may point at the wrong or missing schema even though every
topic exists.

The bounded drill below migrates this one subject from the source registry on `8081` to a genuinely
fresh destination on `18081`. The destination must have been started with `mode.mutability=true`;
that prerequisite is what permits subject-level `IMPORT` mode. First preserve the old wire bytes,
export every subject version with its original ID/version, and export compatibility:

```bash
export SRC_SR=http://localhost:8081 DST_SR=http://localhost:18081
export SUBJECT=orders.events.v1-value
test ! -e registry-backup || { echo 'registry-backup already exists; move it aside'; exit 1; }
mkdir -p registry-backup/versions
uv run --with 'confluent-kafka[avro,schemaregistry]' python schema_round_trip.py
curl --fail-with-body -s "$SRC_SR/config/$SUBJECT" > registry-backup/config.json
for version in $(curl --fail-with-body -s "$SRC_SR/subjects/$SUBJECT/versions" | jq -r '.[]'); do
  curl --fail-with-body -s "$SRC_SR/subjects/$SUBJECT/versions/$version" \
    > "registry-backup/versions/$version.json"
done
test "$(curl --fail-with-body -s "$DST_SR/subjects" | jq length)" -eq 0
```

The first guard refuses to overwrite an earlier backup. The final `test` must return zero: this
drill requires an empty destination and stops rather than merging unknown registry state.

Restore the original IDs and versions, restore the compatibility policy, return the subject to
normal writes, and decode the *pre-restore* bytes against the destination:

```bash
curl --fail-with-body -s -X PUT "$DST_SR/mode/$SUBJECT" \
  -H 'Content-Type: application/json' -d '{"mode":"IMPORT"}' | jq -e '.mode == "IMPORT"'
for file in registry-backup/versions/*.json; do
  jq '{id,version,schema,schemaType:(.schemaType // "AVRO"),references:(.references // [])}' "$file" | \
    curl --fail-with-body -s -X POST "$DST_SR/subjects/$SUBJECT/versions" \
      -H 'Content-Type: application/json' --data-binary @- | jq -e '.id > 0'
done
jq '{compatibility: .compatibilityLevel}' registry-backup/config.json | \
  curl --fail-with-body -s -X PUT "$DST_SR/config/$SUBJECT" \
    -H 'Content-Type: application/json' --data-binary @-
curl --fail-with-body -s -X PUT "$DST_SR/mode/$SUBJECT" \
  -H 'Content-Type: application/json' -d '{"mode":"READWRITE"}' | jq -e '.mode == "READWRITE"'
SCHEMA_REGISTRY_URL="$DST_SR" READ_ONLY=1 \
  uv run --with 'confluent-kafka[avro,schemaregistry]' python schema_round_trip.py
```

**Success signal:** the final read-only run decodes `wire/oldest.bin` and `wire/newest.bin`, prints
their unchanged writer IDs, and produces the same `coupon None` / `coupon AUTUMN10` values as the
source run. A conflicting ID stops import, while `schema not found` on the final run means the Kafka
data and registry state were not restored as one unit. Confluent documents that
[subject-level migration preserves an explicit ID and version](https://docs.confluent.io/platform/current/schema-registry/installation/migrate.html)
and requires mutable modes. For a whole production registry, use its supported migration/Schema
Linking procedure rather than treating this one-subject drill as a complete backup system.

> **Production:** restrict schema registration and deletion, monitor compatibility failures and
> lookup latency, cache schemas in clients with bounded refresh, and test the registry-unavailable
> behavior before shipping.

---

## 5. What breaks, and when not to add a registry

⚠️ Deleting a schema version that retained records still reference makes otherwise healthy Kafka
data undecodable. Prefer soft deletion, retention-aware review, and a restore test before permanent
deletion.

Do not add a network registry to a single-process, short-lived stream when schemas never cross a
deployment boundary and local validation already owns the contract. The additional service earns
its cost when centralized compatibility, many languages, or retained historical schemas matter.

---

**Next**: [Kafka Reliability](../reliability/README.md)
