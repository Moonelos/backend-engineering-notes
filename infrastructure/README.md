# Infrastructure & Tools

> External services and tools your application depends on.

[![Redis](https://img.shields.io/badge/Redis-7.x-DC382D.svg?logo=redis&logoColor=white)](https://redis.io)
[![Apache Kafka](https://img.shields.io/badge/Apache_Kafka-4.3.x-231F20.svg?logo=apachekafka&logoColor=white)](https://kafka.apache.org/)
[![NATS](https://img.shields.io/badge/NATS-2.14.x-27AAE1.svg?logo=natsdotio&logoColor=white)](https://nats.io/)
[![Docker](https://img.shields.io/badge/Docker-latest-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-000000?style=flat&logo=opentelemetry)](https://opentelemetry.io)
[![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?style=flat&logo=prometheus)](https://prometheus.io)

---

## Contents

| Section | Description |
|---------|-------------|
| [redis/](redis/README.md) | Data structures, pub/sub, streams, caching patterns, Python clients |
| [kafka/](kafka/README.md) | Retained logs, Python clients, delivery semantics, reliability, and operations |
| [nats_jetstream/](nats_jetstream/README.md) | Durable subject messaging, pull consumers, Python workers, reliability, and operations |
| [observability/](observability/README.md) | OpenTelemetry primer, Python SDK setup, metrics export methods, OTel Collector config |
| [Messaging](messaging/README.md) | Broker selection, RabbitMQ, SQS and durable message contracts |
| [Secrets](secrets/README.md) | Retrieval, rotation, leases and emergency revocation |
| [Search](search/README.md) | PostgreSQL full-text, OpenSearch and vector-search tradeoffs |

---

## Prerequisites

- [fundamentals/concurrency/](../fundamentals/concurrency/README.md) — async/await before using async Redis clients
- [fundamentals/fastapi/](../fundamentals/fastapi/README.md) — dependency injection patterns for client setup
