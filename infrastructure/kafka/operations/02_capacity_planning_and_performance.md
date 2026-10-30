# Capacity Starts with Bytes, Retention, and the Slowest Consumer

> **Who this is for**: engineers sizing topics and diagnosing throughput ceilings.

## Build a rough envelope before tuning knobs

For ingress `20 MB/s`, retention `7 days`, replication factor `3`, raw replicated storage is about
`20 × 604800 × 3 ≈ 36 TB`, before indexes, headroom, and compaction behavior. Network also includes
replication and consumer egress.

Complete the same `orders.events.v1` envelope with measured limits:

| Input | Measured or required value |
|---|---:|
| Peak ingress | 20 MB/s |
| Safe leader write per partition | 5 MB/s |
| Handler rate per partition | 4 MB/s |
| Maximum burst to recover | 1 hour at 20 MB/s = 72 GB |
| Required catch-up time | 30 minutes |
| Independent consumer groups | 2 |
| Brokers / replication factor | 3 / 3 |

Steady-state writes need `ceil(20 / 5) = 4` partitions, and steady consumers need
`ceil(20 / 4) = 5`. The recovery objective dominates: draining 72 GB in 30 minutes needs 40 MB/s
*in addition to* 20 MB/s live traffic, so consumers need `ceil(60 / 4) = 15` partitions. Start the
load test at 15, not 5.

At replication factor 3, brokers receive 20 MB/s from clients and copy about 40 MB/s to followers.
Two full consumer groups add about 40 MB/s egress, for roughly 100 MB/s cluster data traffic before
protocol and rebalance overhead. Seven-day replicated storage is 36 TB; 30% operating headroom
makes the allocation about 47 TB, or 15.7 TB per broker. To keep disks below 70%, provision roughly
22.5 TB usable per broker.

During one broker loss, the remaining two brokers must carry the leaders and replication traffic.
The estimate is invalid if either broker cannot sustain that measured network/disk load, if records
compress differently from the fixture, if a hot key dominates one partition, or if the handler's
4 MB/s falls when its database is under concurrent load.

---

## 1. Partitions are parallel capacity with fixed overhead

Measure producer bytes/sec per partition and consumer processing rate, then choose enough partitions
for peak load plus failure headroom. Batch size, linger, and compression trade latency and CPU for
fewer requests and better sequential I/O.

Capacity must cover a broker outage: a cluster that works only when every broker is healthy has no
failure budget.

**Success signal:** a load test at expected record sizes sustains peak ingress while lag returns to
zero within 30 minutes after the one-hour burst and a one-broker-loss run stays below 70% disk and
the measured broker ceiling. Tiny synthetic records, one consumer group, or a healthy-brokers-only
run can silently validate the wrong envelope. The [Kafka service test harness](../reliability/05_testing_kafka_services.md)
shows where load tests fit relative to contract and crash tests.

> **Key insight**: Kafka performance is a pipeline budget across producer batching, partition
> leaders, replicas, disks, networks, and consumers; the tightest stage sets throughput.

---

## 2. What breaks, and when not to add partitions

⚠️ Disk nearly full makes recovery and rebalancing slower precisely when extra space is required.

Do not add partitions to fix a slow handler or hot key without measuring placement and downstream
capacity. More shards cannot parallelize one dominant key.

---

## Recap

- Storage includes record bytes, retention and replication, plus operational headroom.
- Recovery throughput must drain backlog while keeping up with new arrivals.
- The largest bottleneck across storage, network and handlers determines useful capacity.

## Check yourself

**Q: Live input is 20 MB/s and backlog is 72 GB. At 4 MB/s per partition, what lower bound meets a 15-minute recovery?**

<details><summary>Answer</summary>

The backlog requires 72,000/900 = 80 MB/s; add 20 MB/s live input for 100 MB/s. ceil(100/4)=25 partitions before skew and failure headroom. The four-partition write minimum does not dominate.

</details>

**Q: Will 25 partitions suffice if one key carries 30 MB/s?**

<details><summary>Answer</summary>

Not with a 4 MB/s serial handler for that key. Aggregate arithmetic assumes useful distribution; partitioning cannot split a strict same-key sequence automatically.

</details>


**Next**: [Observability and Incident Response](03_observability_and_incident_response.md)
