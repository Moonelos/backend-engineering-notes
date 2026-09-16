# Produce and Consume Your First Kafka Event

> **Who this is for**: backend engineers running Kafka for the first time.

## Quick start: one broker, one topic, one record

Run the official Kafka 4.3.1 image as a single local **broker**—a server that stores and serves
records. This follows the [Apache Kafka Docker quick start](https://kafka.apache.org/43/getting-started/docker/):

```bash
docker run --rm --name kafka-notes -p 9092:9092 -d apache/kafka:4.3.1
docker exec kafka-notes /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --topic orders --partitions 1 --replication-factor 1
```

Publish one JSON record and read it back:

```bash
printf '%s\n' '{"event_id":"evt-101","type":"order.created","order_id":"ord-42"}' | \
  docker exec -i kafka-notes /opt/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server localhost:9092 --topic orders

docker exec kafka-notes /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic orders --from-beginning \
  --max-messages 1 \
  --formatter-property print.partition=true \
  --formatter-property print.offset=true
```

**Success signal:** the consumer prints partition `0`, offset `0`, and the `ord-42` event. If the
topic command reports that no broker is available, inspect `docker logs kafka-notes`; the usual
cause is that the broker has not finished starting.

> **Production:** this is a disposable, plaintext, single-replica cluster. It proves the record
> path, not availability or security. Those belong in [Operations](../operations/README.md).

---

## 1. The broker preserves the event after the consumer exits

A queue-shaped intuition says consumption removes a message. Run the consumer command again: Kafka
returns the event again because `--from-beginning` starts a new consumer without a saved position.
Kafka stores records for a configured retention period; consumers separately track their position.

The path is:

```text
console producer → orders partition 0, offset 0 → console consumer
                         │
                         └── record remains in the log
```

That separation enables replay, multiple independent consumers, and rebuilding derived data.

---

## 2. Three identifiers answer three different questions

- `orders` is the **topic**, the named stream to which producers publish.
- `0` is the **partition**, one ordered shard of that topic.
- `0` is the **offset**, the record's position inside that partition.

An offset is not a global event identifier. Partition 1 can also contain offset 0, and retention can
remove the record formerly addressed by an old offset.

> **Key insight**: Kafka consumption advances a reader's position; it does not transfer ownership
> of a record or remove the record from storage.

---

## 3. What breaks first

⚠️ Stopping the container deletes this local broker's data because the command did not mount a
volume. The symptom is a missing `orders` topic after restart, not a consumer bug.

⚠️ Port `9092` can be reachable while advertised broker addresses are wrong in a custom Docker
setup. Metadata succeeds, then producers time out connecting to the address returned by the broker.
Use the official default command here before introducing custom listeners.

---

## 4. When not to use this setup

Do not use this one-node command for performance tests, failure tests, shared development, or
production. It has replication factor one, no authentication, no encryption, and no durable volume.
Use it only to learn the protocol or run a disposable local test.

Clean up with `docker stop kafka-notes`. Success is `docker ps` no longer listing the container.

---

**Next**: [Logs, Topics, Partitions, and Offsets](02_log_topics_partitions_and_offsets.md)
