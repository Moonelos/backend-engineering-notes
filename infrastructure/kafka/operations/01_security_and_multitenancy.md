# Kafka Security Must Constrain Both Connection and Action

> **Who this is for**: engineers moving beyond a plaintext local broker.

## Prove one allowed flow and two denied flows

**Transport Layer Security (TLS)** encrypts traffic; the **Simple Authentication and Security
Layer (SASL)** or mutual TLS authenticates a service identity; **access-control lists (ACLs)**
authorize that identity to named resources. A successful TLS handshake proves only the first layer.

Use a disposable record and bounded identities to prove the whole policy. The procedure below needs:

- two reachable brokers in `bootstrap.servers` and the expected broker DNS names in their certificates;
- an authenticated `admin.properties` that may change ACLs;
- `/etc/kafka/ca.pem` and two mode-`0600` client property files, one for `orders-api` and one for
  `billing-worker`; and
- application-owned topic `orders.events.v1` and no production consumer using group `billing-v1-test`.

The client files use `SASL_SSL`, `SCRAM-SHA-512`, verified TLS, and credentials supplied by the
deployment secret store. Do not put passwords in shell history, source, images, logs, or events.

```properties
# /run/secrets/orders-api.properties (same shape for billing-worker.properties)
security.protocol=SASL_SSL
sasl.mechanism=SCRAM-SHA-512
sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required username="orders-api" password="REDACTED_BY_SECRET_MOUNT";
ssl.truststore.type=PEM
ssl.truststore.location=/etc/kafka/ca.pem
client.id=orders-api-acl-check
```

Grant only the intended actions. The test group has a separate name so the check cannot move a
production checkpoint.

```bash
kafka-acls.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --add \
  --allow-principal User:orders-api --operation Write \
  --topic orders.events.v1

kafka-acls.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --add \
  --allow-principal User:billing-worker --operation Read \
  --topic orders.events.v1

kafka-acls.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --add \
  --allow-principal User:billing-worker --operation Read \
  --group billing-v1-test
```

Choose a unique value such as `acl-check-20260916T120000Z`. Produce it, search for that exact value
with the permitted group for at most 30 seconds, then try one unrelated topic and one unrelated
group. This shell uses GNU `timeout`; use the platform's equivalent bounded-process runner elsewhere.

```bash
printf '%s\n' 'acl-check-20260916T120000Z' | \
  kafka-console-producer.sh --bootstrap-server broker-1.example.com:9093 \
    --producer.config /run/secrets/orders-api.properties \
    --topic orders.events.v1

set -o pipefail
timeout 30s kafka-console-consumer.sh \
  --bootstrap-server broker-1.example.com:9093 \
  --consumer.config /run/secrets/billing-worker.properties \
  --topic orders.events.v1 --group billing-v1-test --from-beginning | \
  grep --fixed-strings --max-count=1 'acl-check-20260916T120000Z'

printf '%s\n' 'must-not-write' | \
  kafka-console-producer.sh --bootstrap-server broker-1.example.com:9093 \
    --producer.config /run/secrets/orders-api.properties \
    --topic payments.events.v1

kafka-console-consumer.sh --bootstrap-server broker-1.example.com:9093 \
  --consumer.config /run/secrets/billing-worker.properties \
  --topic orders.events.v1 --group fraud-v1 \
  --max-messages 1 --timeout-ms 10000
```

The bounded consumer prints the unique value and the pipeline exits zero. The negative producer fails with a topic-authorization
error, and the negative consumer fails with a group-authorization error. A timeout is not proof of
denial: the client must report authorization failure. If either forbidden operation succeeds,
inspect the complete effective ACL set with the same authenticated endpoint:

```bash
kafka-acls.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --list

kafka-acls.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --list \
  --principal User:orders-api

kafka-acls.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --list \
  --principal User:billing-worker
```

The unfiltered command is important: a grant can come from `User:*`, a prefixed resource, or a
wildcard resource and therefore be absent from a narrow topic lookup. Save the output with the test
result, but never print a client properties file—ACL listings contain principals, not passwords.

## Rotate credentials as an explicit state transition

“Overlapping validity” is safe only when the overlap is short and observable. Create a second
principal, `orders-api-v2`, in the SCRAM or identity system, and copy only the old principal's
reviewed `Write` grant—not every ACL it happens to inherit.

| State | `orders-api` | `orders-api-v2` | Exit evidence | Rollback |
|---|---|---|---|---|
| A: before | credential + ACL active | absent | baseline positive/negative test passes | none |
| B: overlap | active | credential + same least-privilege ACL active | v2 writes intended topic and is denied unrelated topic | keep clients on v1; remove v2 ACL/credential |
| C: cut over | active but unused | all instances use v2 | broker/client auth metrics show no v1 use for the observation window | redeploy v1 secret |
| D: revoke | ACL and credential removed | active | v1 gets authentication or authorization failure; v2 still passes | recreate v1 credential and ACL from the change record |

Add and later remove the duplicated ACL with explicit principals:

```bash
kafka-acls.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --add \
  --allow-principal User:orders-api-v2 --operation Write \
  --topic orders.events.v1

kafka-acls.sh --bootstrap-server broker-1.example.com:9093 \
  --command-config admin.properties --remove --force \
  --allow-principal User:orders-api --operation Write \
  --topic orders.events.v1
```

Run the same allowed and denied producer checks using the v2 secret before deployment, and again
after cutover. Revoke the old credential in the identity backend only after the no-v1-use window.
After revocation, retry with the old properties file: an authentication failure proves the old
secret cannot reconnect. Kafka ACL deletion alone is insufficient if another broad grant remains.

The cheap rollback ends at state C. State D is deliberately a harder rollback: restore the old
credential and exact ACL from the recorded change, test it, and only then redeploy clients. Never
keep an undocumented emergency wildcard grant.

## Isolation has a boundary

⚠️ Wildcard ACLs turn one compromised client into a cluster-wide producer or consumer. A principal
that can create topics, alter configs, or administer Kafka Connect can redirect or disrupt data
without broker shell access.

ACLs isolate actions, not CPU, disk, network, encryption keys, or cluster failure. Add per-identity
quotas for noisy-neighbor control. Use separate clusters or a managed-service isolation boundary
when tenants require hard resource, key, compliance, or failure-domain separation.

The command forms and authorization model are versioned against Apache Kafka 4.3's
[security documentation](https://kafka.apache.org/43/security/security-overview/).

---

**Next**: [Capacity Planning and Performance](02_capacity_planning_and_performance.md)
