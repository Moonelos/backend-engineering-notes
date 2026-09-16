# Kafka Incidents Need Broker and Business Signals Together

> **Who this is for**: teams defining dashboards, alerts, and first-response checks.

## Prove the alert path before trusting it

Lag alone cannot identify whether a consumer, dependency, broker, coordinator, or controller is
stuck. Correlate lag with record age, handler latency, errors, assignment changes, replica health,
control-plane queues, and disk. Then test the rule, reload path, firing state, and missing-metric path.

Assume the exporter normalizes metrics to the names below. Put this complete rule group in
`kafka-orders.rules.yml`:

```yaml
groups:
  - name: kafka-orders
    rules:
      - alert: KafkaOrdersFreshnessBreached
        expr: |
          max by (cluster, consumergroup, topic, partition) (
            kafka_consumergroup_lag{consumergroup="billing-v1",topic="orders.events.v1"}
          ) > 1000
          and on (cluster, consumergroup, topic, partition)
          max by (cluster, consumergroup, topic, partition) (
            orders_event_age_seconds{consumergroup="billing-v1",topic="orders.events.v1"}
          ) > 120
        for: 10m
        labels:
          severity: page
          service: billing
        annotations:
          summary: billing-v1 is more than 2 minutes stale

      - alert: KafkaOrdersFreshnessMetricMissing
        expr: absent(orders_event_age_seconds{consumergroup="billing-v1",topic="orders.events.v1"})
        for: 5m
        labels:
          severity: page
          service: telemetry
        annotations:
          summary: billing-v1 freshness metric is missing

      - alert: KafkaReplicaOrDiskRisk
        expr: |
          max by (cluster) (kafka_server_replicamanager_underreplicatedpartitions) > 0
          or on (cluster)
          (1 - min by (cluster) (
            node_filesystem_avail_bytes{mountpoint="/var/lib/kafka"}
            / node_filesystem_size_bytes{mountpoint="/var/lib/kafka"}
          )) > 0.85
        for: 15m
        labels:
          severity: page
          service: kafka
        annotations:
          summary: Kafka replicas are under-replicated or data disk exceeds 85%
```

Validate syntax and expressions before asking Prometheus to reload. A zero exit status and
`SUCCESS: 3 rules found` are the local gate:

```bash
promtool check rules kafka-orders.rules.yml
```

For deterministic CI, put the following in `kafka-orders.rules.test.yml`. The first case supplies one
hot partition long enough to satisfy `for: 10m`; the second deliberately supplies no freshness
series and crosses `for: 5m`:

```yaml
rule_files:
  - kafka-orders.rules.yml
evaluation_interval: 1m
tests:
  - name: sustained stale partition fires
    interval: 1m
    input_series:
      - series: 'kafka_consumergroup_lag{cluster="staging",consumergroup="billing-v1",topic="orders.events.v1",partition="7"}'
        values: '1201+0x12'
      - series: 'orders_event_age_seconds{cluster="staging",consumergroup="billing-v1",topic="orders.events.v1",partition="7"}'
        values: '121+0x12'
    alert_rule_test:
      - eval_time: 11m
        alertname: KafkaOrdersFreshnessBreached
        exp_alerts:
          - exp_labels:
              cluster: staging
              consumergroup: billing-v1
              topic: orders.events.v1
              partition: "7"
              severity: page
              service: billing
            exp_annotations:
              summary: billing-v1 is more than 2 minutes stale

  - name: missing freshness series fires
    interval: 1m
    alert_rule_test:
      - eval_time: 6m
        alertname: KafkaOrdersFreshnessMetricMissing
        exp_alerts:
          - exp_labels:
              consumergroup: billing-v1
              topic: orders.events.v1
              severity: page
              service: telemetry
            exp_annotations:
              summary: billing-v1 freshness metric is missing
```

`promtool test rules` must report `SUCCESS`; this exercises firing labels and `for:` timing without
waiting on a real incident.

```bash
promtool test rules kafka-orders.rules.test.yml
curl --fail --silent --show-error -X POST https://prometheus.example.com/-/reload
curl --fail --silent --show-error \
  'https://prometheus.example.com/api/v1/rules?type=alert' | \
  jq '.data.groups[] | select(.name=="kafka-orders") | .rules[] | {name,state,lastError}'
```

The HTTP reload endpoint is disabled unless Prometheus starts with `--web.enable-lifecycle`; if the
team intentionally leaves it disabled, send `SIGHUP` through the process supervisor instead. The
test-file schema and reload behavior are documented by Prometheus in its
[rule-unit-testing](https://prometheus.io/docs/prometheus/latest/configuration/unit_testing_rules/)
and [management API](https://prometheus.io/docs/prometheus/latest/management_api/) references.

The reload is successful only when the API shows all three rules with an empty `lastError`; an HTTP
200 from a proxy is not enough. In a disposable staging flow, delay `billing-v1` long enough to
cross both thresholds and ten-minute duration. Query the API and require `state: "firing"` with
`cluster`, `consumergroup`, `topic`, and `partition=7`, then restore the handler and require the alert
to resolve. Stop the freshness exporter separately and require the missing-metric alert to fire.
Do not inject delay or stop telemetry in production merely to test paging.

The first rule's conjunction avoids paging for a large but rapidly draining batch. The separate
`absent()` rule prevents a dead exporter from turning the conjunction into false green health.

## Diagnose from consequence toward the owning state

```text
freshness breached
  -> one partition: hot key, stuck record, or one slow handler
  -> all partitions in one group: dependency, coordinator, or deployment
  -> many groups/topics: broker, disk, network, or KRaft controller quorum
```

Preserve client ID, group ID, topic, partition, offset, and event ID in structured diagnostics,
without credentials or sensitive payloads. The first action is diagnosis, not restart: restarting a
healthy consumer can add another rebalance to an already unstable group.

### Coordinator: assignment and checkpoints stop progressing

Kafka 4.3 exposes group-coordinator partition states, event-queue size/time, thread idle ratio,
rebalance rate, and offset-commit rate. A useful branch is:

| Signal | Diagnose | Recover and verify |
|---|---|---|
| `num-partitions{state="failed"}>0` or loading persists | inspect broker logs for the affected `__consumer_offsets` partition; check its leader, ISR, disk, and broker metadata lag | restore replica/broker health or leadership; verify failed/loading returns to zero and commits resume |
| event queue/time rises while thread idle ratio falls | compare request rate, broker CPU, garbage collection, and coordinator append latency; identify a rebalance or commit storm | stop the offending rollout/client loop, restore capacity, then verify the queue drains and groups become stable |
| rebalance rate rises but coordinator queues are healthy | inspect member timeouts, poll duration, deployment churn, and assignment callbacks | fix the client lifecycle; verify stable membership and falling record age rather than bouncing brokers |

### KRaft controller: metadata changes stop committing

Across controller nodes, exactly one `ActiveControllerCount` should be 1. Page on no active
controller, offline partitions, sustained `LastAppliedRecordLagMs`, rising
`EventQueueOperationsTimedOutCount`, or repeated `NewActiveControllersCount` changes.

First establish whether the quorum has a leader and majority connectivity; then compare controller
disk/CPU/garbage collection, event-queue latency, timed-out broker heartbeats, and metadata error
counters. Restore quorum network/disk or the failed controller according to the deployment
procedure—do not delete or reformat controller storage as a first response. Recovery is complete
only when one controller is active, metadata commit/apply lag converges, brokers are active, offline
partitions are zero, and a bounded topic describe plus canary produce/consume succeeds.

The exact JMX names are listed in Apache Kafka 4.3's
[monitoring reference](https://kafka.apache.org/43/operations/monitoring/); exporter names vary, so
record the mapping in the dashboard repository.

## What breaks, and when not to page

⚠️ Topic-wide average lag hides one stuck partition behind many idle partitions. Conversely, a
momentary rebalance or small lag without breached freshness is usually not a page.

Use tickets for capacity trends. Reserve pages for urgent conditions with a named owner and a safe
first action. A green process dashboard is not evidence that a named event flow is fresh.

---

**Next**: [Deployment, Upgrades, and Disaster Recovery](04_deployment_upgrades_and_disaster_recovery.md)
