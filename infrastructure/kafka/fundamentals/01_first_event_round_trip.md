# One Kafka Record, End to End

> **Goal:** publish one `order.created` record, read it back, and explain the path it followed.

## First see the whole journey

An order service has accepted order `ord-42`. It wants other applications to learn that fact without
calling each one directly. It sends this record to Kafka:

```json
{"event_id":"evt-101","type":"order.created","order_id":"ord-42"}
```

Five things happen:

```text
1. PRODUCE          2. APPEND                 3. STORE

Order service ───► orders / partition 0 ───► [offset 0: evt-101]
   producer                broker                    log

4. FETCH                                      5. REMEMBER PROGRESS

[offset 0: evt-101] ───► console consumer      no durable group position yet
```

The **producer** is the client that sends the record. A Kafka **broker** is a server that stores and
serves records. The record is appended to one **partition**, an ordered log inside the `orders`
**topic**. Kafka assigns the record an **offset**, its numbered position in that partition. A
**consumer** fetches the stored record.

Do not memorize those terms separately yet. Use them to narrate the arrows: the producer sends,
the broker appends, the consumer fetches. The remaining chapters explain how Kafka chooses the
partition, preserves the data, divides consumer work, and survives broker failure.

## Run the smallest complete round trip

Start the official Kafka 4.3.1 image:

```bash
docker run --rm --name kafka-notes -p 9092:9092 -d apache/kafka:4.3.1
```

Wait until the broker is ready, then create a one-partition topic:

```bash
docker exec kafka-notes /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create \
  --topic orders \
  --partitions 1 \
  --replication-factor 1
```

The topic has one partition so the first record must land in partition `0`. Publish the record with
`ord-42` as its key:

```bash
printf '%s\n' \
  'ord-42:{"event_id":"evt-101","type":"order.created","order_id":"ord-42"}' | \
  docker exec -i kafka-notes /opt/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server localhost:9092 \
    --topic orders \
    --reader-property parse.key=true \
    --reader-property key.separator=:
```

Read one record from the beginning of the partition:

```bash
docker exec kafka-notes /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic orders \
  --from-beginning \
  --max-messages 1 \
  --formatter-property print.partition=true \
  --formatter-property print.offset=true \
  --formatter-property print.key=true
```

The exact separators are formatter-dependent, but the output must contain partition `0`, offset
`0`, key `ord-42`, and the JSON value. That is the observable proof of the five-step path:

| Observed field | What it proves |
|---|---|
| topic `orders` | The producer and consumer addressed the same named stream |
| partition `0` | The record belongs to one ordered log |
| offset `0` | It is the first append in that partition |
| key `ord-42` | The producer supplied routing identity |
| JSON value | The application payload survived the round trip |

If topic creation says no broker is available, the container is still starting or failed. Inspect
`docker logs kafka-notes`. If the consumer waits without output, first confirm that the producer
command completed and that both commands use topic `orders`.

## A record is more than its JSON value

The application supplied a key and value; Kafka and the client attach transport metadata:

```text
record
├── key:       ord-42                         application supplies
├── value:     {"event_id":"evt-101", ...}    application supplies
├── topic:     orders                         producer call supplies
├── partition: 0                              client chooses; trivial here
├── offset:    0                              broker assigns on append
└── timestamp: ...                            producer or broker assigns
```

Headers may carry small pieces of transport metadata such as a trace identifier. The business fact
belongs in the value, while a stable entity identity commonly belongs in the key. Later chapters
make the key's routing effect precise.

## Reading did not remove the record

Run the consumer command again. It reads `evt-101` again because `--from-beginning` starts another
consumer with no saved group position. The broker still has the record.

> **The near-miss:** Kafka is not a mailbox that hands one message to one reader and deletes it.
> Kafka stores a log. Readers move through that log independently.

That observation creates the next question: if the record remains stored, what exactly advances
when a consumer reads it?

## Check your model

Suppose a second console consumer runs the same command. Does it steal `evt-101` from the first
consumer?

No. Both commands are independent readers without a durable shared group position. Each asks for the
earliest retained record, so each can fetch offset `0`. Chapter 2 separates the stored log from
reader progress; Chapter 4 adds coordinated consumer groups.

## Boundary of this local setup

This container is intentionally disposable: one broker, one replica, plaintext networking, and no
mounted data volume. It demonstrates the record path, not production availability or security.
Stopping the container removes its local data.

Keep it running if you want to repeat the commands. When finished:

```bash
docker stop kafka-notes
```

**Success signal:** `docker ps` no longer lists `kafka-notes`.

---

**Next:** [The Retained Log: Topics, Partitions, and Offsets](02_log_topics_partitions_and_offsets.md)
