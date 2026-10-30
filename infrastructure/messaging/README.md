# Messaging choices and queue operation

Choose a delivery model and operate RabbitMQ or SQS while reusing the existing Kafka, Redis and JetStream courses.

## Reading path

Start with 01, then 05 for the transaction and identity foundation; follow only the broker branch your workload needs. The existing durable-task lessons provide the worker foundation. The broker branches reuse 05 instead of redefining the effect transaction. Chapter 04 is intentionally not duplicated: use the full [Kafka course](../kafka/README.md), alongside [Redis Streams](../redis/02_pubsub_and_streams.md) or [JetStream](../nats_jetstream/README.md).

## Contents

| Chapter | Outcome |
|---|---|
| [Choose a broker](01_broker_decision_guide.md) | Queues, fanout, retained logs, streams and transient notifications. |
| [RabbitMQ](02_rabbitmq.md) | Publisher confirms, consumer acknowledgements, bounded work and recovery. |
| [Amazon SQS](03_sqs.md) | Visibility leases, retry policy, FIFO boundaries and dead letters. |
| [Contracts and outbox](05_message_contracts_and_outbox.md) | Version messages and connect durable database effects to delivery. |
