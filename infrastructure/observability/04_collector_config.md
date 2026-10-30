# OTel Collector Config

<!-- length-justification: This is the canonical Collector configuration reference; receivers, processors, exporters, service pipelines, deployment modes, and vendor routes remain together because a valid component is inert until the same config connects it into a signal pipeline. -->

> **Who this is for**: Engineers deploying the OpenTelemetry Collector and writing its YAML config — understanding what every section does, why it exists, and how to route traces and metrics to different backends.

---

## Minimal pipeline: receive one OTLP trace and print it

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317
exporters:
  debug:
    verbosity: detailed
service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [debug]
```

That YAML is for a native Collector bound to loopback. For Docker, use the checked-in
[collector-local.yaml](examples/collector-local.yaml), whose container listener is `0.0.0.0` but
whose published host port is loopback-only. The console-only SDK proof from chapter 2 does not
send OTLP: [otlp_sender.py](examples/otlp_sender.py) installs the required OTLP exporter.
Run from the repository root in two terminals:

```bash
docker run --rm --name notes-otel-local -p 127.0.0.1:14317:4317 \
  -v "$PWD/infrastructure/observability/examples/collector-local.yaml:/etc/otelcol-contrib/config.yaml:ro" \
  ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:0.151.0
```

```bash
uv run --with opentelemetry-sdk --with opentelemetry-exporter-otlp-proto-grpc \
  python infrastructure/observability/examples/otlp_sender.py
docker logs notes-otel-local
docker stop notes-otel-local
```

Require the Collector's detailed output to contain a span named `checkout`. The sender's flush
print proves that its queue drained, not that a backend stored the data. A connection-refused error
usually means the container is not ready or the wrong host port was used. Receiving bytes without
export output means the traces pipeline or exporter is missing. `verbosity: basic` summarizes batches
and does not promise to print individual span names.

> **Production:** bind beyond loopback only with authentication and verified TLS. Later sections
> add processors, batching, retries, and backend exporters.

> **Core:** A Collector component does nothing until a service pipeline connects its receiver,
> processors, and exporters for a specific signal.

---

## 1. What the Collector Is and Why You Need It

The OTel Collector is a standalone binary (or Docker image) that receives telemetry from your apps, applies transformations, and forwards to backends. It is not part of your application code.

**Without a Collector:**

```
App → OTLP → Groundcover
App → Prometheus scrape endpoint (pull)
```

Your app has to know every backend address, retry logic, and export format.

**With a Collector:**

```
App → OTLP → Collector → Groundcover       (traces)
                       → VictoriaMetrics   (metrics)
                       → S3                (logs)
```

The app knows one address: the Collector. The Collector handles everything else.

### What the Collector gives you beyond "just forwarding"

| Capability | Without Collector | With Collector |
|---|---|---|
| Multi-backend routing | Instrument N exporters in app | One exporter in app, N in Collector config |
| Retry / backpressure | App must implement | Collector handles it |
| Filtering / dropping | App code change | Collector config change |
| Attribute enrichment | App code change | Collector processor config |
| Backend migration | Redeploy all apps | Redeploy Collector config |
| Tail sampling | Not possible from SDK | Possible in Collector |

---

## 2. Collector Config Anatomy

A practical Collector config usually centers on four top-level sections. Each section is independent; the `service` section wires them together. Current Collector configs can also include optional `connectors` and `extensions`, but you do not need those for a standard app-ingest pipeline.

```yaml
receivers:    # 1. How data gets IN to the Collector
processors:   # 2. What the Collector does WITH the data in-flight
exporters:    # 3. Where the data goes OUT
service:      # 4. Which receivers/processors/exporters are active and how they connect
```

> **Key insight**: Defining a receiver, processor, or exporter in the config does nothing on its own. It only takes effect when referenced in a `service.pipelines` block. This is a common source of confusion.

---

## 3. Receivers — How Data Gets In

Receivers listen for incoming telemetry.

```yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317   # default gRPC port
      http:
        endpoint: 0.0.0.0:4318   # default HTTP/protobuf port
```

**Why both grpc and http?**

- Both OTLP/gRPC and OTLP/HTTP-protobuf carry protobuf. Choose using proxy support, connection behavior and measured overhead; gRPC has no universal smaller-payload guarantee.
- HTTP/protobuf is useful for environments where gRPC is blocked (some proxies, service meshes)
- Most Python apps use gRPC by default (`OTLPSpanExporter` uses gRPC unless you import the HTTP variant)

Other common receivers:

```yaml
receivers:
  # Pull metrics from a Prometheus /metrics endpoint
  prometheus:
    config:
      scrape_configs:
        - job_name: "myapp"
          static_configs:
            - targets: ["myapp:9464"]

  # Receive logs from fluentd/fluentbit
  fluentforward:
    endpoint: 0.0.0.0:24224

  # Receive Jaeger-format traces (legacy migration)
  jaeger:
    protocols:
      grpc:
        endpoint: 0.0.0.0:14250
```

---

## 4. Processors — What Happens In-Flight

Processors sit between receivers and exporters. They transform, filter, or enrich data before it leaves the Collector.

### batch (always use this)

```yaml
processors:
  batch:
    timeout: 5s             # max time to wait before sending a batch
    send_batch_size: 1000   # flush trigger, not a hard maximum
    send_batch_max_size: 2000
```

The `batch` processor groups incoming data. `send_batch_size` triggers a flush, `timeout` bounds
waiting, and `send_batch_max_size` caps outgoing batches. Incoming SDK/exporter requests may already
contain many spans; omitting this processor does not imply one span per network call. Tune the
processor to balance latency, memory and backend request overhead.

### memory_limiter (always use this in production)

```yaml
processors:
  memory_limiter:
    check_interval: 5s
    limit_mib: 512          # hard threshold: force garbage collection
    spike_limit_mib: 128    # buffer for sudden spikes above the steady-state limit
```

With these values the soft threshold is `512 - 128 = 384 MiB`. Above it, the limiter refuses new
data with a non-permanent error so the upstream component can retry. Above 512 MiB it also forces
garbage collection. Loss depends on upstream retry support and finite queue capacity; the processor
does not guarantee either losslessness or immediate dropping. Put it early to propagate pressure
before expensive work, and leave runtime headroom below the container memory limit.
[0.151.0 memory limiter semantics](https://github.com/open-telemetry/opentelemetry-collector/blob/v0.151.0/processor/memorylimiterprocessor/README.md), checked 2026-10-30.

### resource (add/overwrite attributes)

```yaml
processors:
  resource:
    attributes:
      - key: deployment.environment.name
        value: "production"
        action: upsert          # insert if absent, overwrite if present
      - key: cloud.region
        value: "us-east-1"
        action: insert          # only insert if the key does not already exist
```

Use this to stamp attributes onto every span or metric from a particular Collector deployment — region, cluster, environment — without touching app code.

### attributes (add/drop/hash span-level attributes)

```yaml
processors:
  attributes:
    actions:
      - key: http.url
        action: delete          # remove a sensitive attribute from all spans
      - key: user.email
        action: hash            # hash PII rather than dropping it
      - key: team
        value: "platform"
        action: insert
```

`resource` operates on `Resource` attributes (service-level). `attributes` operates on span/metric-level attributes. They are different scopes.

> **Attribute names depend on the app's semconv setting.** The `http.url` key above is the *old* HTTP semconv name. If your services opt into the stable HTTP conventions (`OTEL_SEMCONV_STABILITY_OPT_IN=http`, see [02](02_python_sdk.md)), that attribute is instead `url.full` (with `url.path` / `url.query`), and `http.method` / `http.status_code` become `http.request.method` / `http.response.status_code`. Match your processor rules to whatever the apps actually emit, or they will silently no-op.

### filter (drop entire spans or metrics)

```yaml
processors:
  filter:
    error_mode: ignore   # ignore | silent | propagate (default). Use ignore: log OTTL errors and continue.
    traces:
      span:
        # Drop health check spans entirely
        - 'attributes["http.route"] == "/health"'
        - 'attributes["http.route"] == "/metrics"'
```

> Without `error_mode: ignore`, any OTTL expression evaluation error causes the Collector to drop the span and propagate an error. For drop rules, `ignore` is almost always the right choice.

---

## 5. Exporters — Where Data Goes Out

Exporters send data to backends.

### OTLP exporter (to any OTLP-accepting backend)

```yaml
exporters:
  otlp/groundcover:                        # /groundcover is an alias — required when you have multiple OTLP exporters
    endpoint: "ingest.groundcover.com:443"
    headers:
      Authorization: "Bearer ${env:GROUNDCOVER_API_KEY}"   # env var substitution
    tls:
      insecure: false

  otlp/jaeger:
    endpoint: "jaeger:4317"
    tls:
      insecure: true
```

> The `/name` suffix (e.g., `otlp/groundcover`) is how you define **multiple instances** of the same exporter type. Without it, you can only have one OTLP exporter. With it, you can fan out the same signal to multiple backends.

### Prometheus Remote Write exporter

```yaml
exporters:
  prometheusremotewrite:
    endpoint: "https://victoria-metrics.internal/api/v1/write"
    headers:
      X-Scope-OrgID: "myorg"
    tls:
      insecure_skip_verify: false
    resource_to_telemetry_conversion:
      enabled: true   # converts Resource attributes into Prometheus labels
```

`resource_to_telemetry_conversion.enabled` is powerful but easy to overuse. Its default is `false`. Turning it on copies **all** resource attributes into metric labels, which is convenient for querying but can create expensive cardinality if attributes such as pod IDs, container IDs, or instance IDs vary frequently.

### Prometheus exporter (expose a scrape endpoint from the Collector)

```yaml
exporters:
  prometheus:
    endpoint: "0.0.0.0:8889"   # Prometheus scrapes this port on the Collector
    namespace: "otelcol"
    resource_to_telemetry_conversion:
      enabled: true
```

This makes the Collector a Prometheus scrape target. Useful when your metric backend can only pull (i.e., does not accept Remote Write).

By default, Prometheus exporters do **not** copy every resource attribute onto every metric. Instead, Prometheus target identity is carried through `job` / `instance`, and the remaining resource attributes are typically exposed via a `target_info` metric. Promote extra resource attributes to labels only when you actually need them for queries.

### Debug exporter (debug only)

```yaml
exporters:
  debug:
    verbosity: detailed   # normal | basic | detailed — dev/debug only, never production
```

> The `logging` exporter was removed in Collector v0.111.0. Use `debug` instead. `loglevel` is replaced by `verbosity`.

---

## 6. Service — Wiring It All Together

The `service` section declares which components are active and how they connect into pipelines.

```yaml
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/groundcover]

    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [prometheusremotewrite]

    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlp/groundcover]
```

**Rules:**

- Each pipeline is independent. Traces, metrics, and logs can have completely different receivers, processors, and exporters.
- Processors run in the order listed. Put `memory_limiter` first to protect against OOM before any enrichment.
- A component not referenced in `service.pipelines` is defined but never runs.

---

## 7. Full Production Config

This config matches **Method 1B** from [03 — Metrics Export Methods](03_metrics_export_methods.md): the app sends all signals via OTLP, the Collector routes traces to Groundcover and metrics to a Prometheus-compatible backend.

The client must trust the issuing CA, present a certificate accepted by `client_ca_file`, and use
the DNS name in the server certificate. Mount these files read-only; control network access and
client certificate issuance as well as encryption.

```yaml
# otel-collector-config.yaml

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
        tls:
          cert_file: /tls/tls.crt
          key_file: /tls/tls.key
          client_ca_file: /tls/ca.crt
      http:
        endpoint: 0.0.0.0:4318
        tls:
          cert_file: /tls/tls.crt
          key_file: /tls/tls.key
          client_ca_file: /tls/ca.crt

processors:
  memory_limiter:
    check_interval: 5s
    limit_mib: 384
    spike_limit_mib: 96

  batch:
    timeout: 5s
    send_batch_size: 1000

  resource:
    attributes:
      - key: deployment.environment.name
        value: ${env:ENVIRONMENT}      # injected via environment variable
        action: upsert

  filter/drop_health:
    error_mode: ignore
    traces:
      span:
        - 'attributes["http.route"] == "/health"'
        - 'attributes["http.route"] == "/readiness"'

exporters:
  # Traces → Groundcover
  otlp/groundcover:
    endpoint: "ingest.groundcover.com:443"
    headers:
      Authorization: "Bearer ${env:GROUNDCOVER_API_KEY}"

  # Metrics → VictoriaMetrics (or any Prometheus-compatible backend)
  prometheusremotewrite:
    endpoint: "https://victoria-metrics.internal/api/v1/write"
    resource_to_telemetry_conversion:
      enabled: true

  # Logs → Groundcover (same OTLP endpoint, different pipeline)
  otlp/groundcover_logs:
    endpoint: "ingest.groundcover.com:443"
    headers:
      Authorization: "Bearer ${env:GROUNDCOVER_API_KEY}"

service:
  telemetry:
    logs:
      level: WARN                # Collector's own log level — not your app's logs
    metrics:
      readers:
        - pull:
            exporter:
              prometheus:
                host: 0.0.0.0
                port: 8888

  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, filter/drop_health, resource, batch]
      exporters: [otlp/groundcover]

    metrics:
      receivers: [otlp]
      processors: [memory_limiter, resource, batch]
      exporters: [prometheusremotewrite]

    logs:
      receivers: [otlp]
      processors: [memory_limiter, resource, batch]
      exporters: [otlp/groundcover_logs]
```

### Processor order in the traces pipeline

```
memory_limiter → filter/drop_health → resource → batch → exporter
```

1. **memory_limiter first** — refuse with retryable pressure above the soft threshold; upstream capacity determines eventual loss
2. **filter** — drop health check spans before enriching them (no point enriching what you discard)
3. **resource** — stamp environment attributes onto spans
4. **batch** — group into efficient export batches
5. **exporter** — send

---

## 8. Where the Collector Runs

### Docker Compose for the local experiment

```yaml
services:
  otel-collector:
    image: ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:0.151.0
    volumes:
      - ./infrastructure/observability/examples/collector-local.yaml:/etc/otelcol-contrib/config.yaml:ro
    ports:
      - "127.0.0.1:14317:4317"
```

Run the same `otlp_sender.py` from the host. For production use the mTLS config above and mount
server/client trust material; exposing the local fixture outside loopback changes its trust boundary.

### Kubernetes (DaemonSet — one Collector per node)

```yaml
# collector-daemonset.yaml

apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: otel-collector
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app: otel-collector
  template:
    metadata:
      labels:
        app: otel-collector
    spec:
      containers:
        - name: otel-collector
          image: ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:0.151.0
          args: ["--config=/conf/config.yaml"]
          ports:
            - containerPort: 4317    # OTLP gRPC
            - containerPort: 4318    # OTLP HTTP
            - containerPort: 8888    # self-metrics
          volumeMounts:
            - name: config
              mountPath: /conf
            - name: tls
              mountPath: /tls
              readOnly: true
          env:
            - name: GROUNDCOVER_API_KEY
              valueFrom:
                secretKeyRef:
                  name: otel-secrets
                  key: groundcover-api-key
            - name: ENVIRONMENT
              value: "production"
          resources:
            limits:
              memory: 512Mi
              cpu: 500m
            requests:
              memory: 128Mi
              cpu: 100m
      volumes:
        - name: tls
          secret:
            secretName: otel-server-tls
        - name: config
          configMap:
            name: otel-collector-config
```

A `containerPort` is documentation for the pod; it does not bind the node IP. Expose a private
Service and have applications use its DNS name, which must also appear in the server certificate:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: otel-collector
  namespace: monitoring
spec:
  selector:
    app: otel-collector
  ports:
    - name: otlp-grpc
      port: 4317
      targetPort: 4317
```

Application environment (mount its client certificate/key and CA at these paths):

```yaml
env:
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: "https://otel-collector.monitoring.svc:4317"
  - name: OTEL_EXPORTER_OTLP_CERTIFICATE
    value: "/otel-client/ca.crt"
  - name: OTEL_EXPORTER_OTLP_CLIENT_CERTIFICATE
    value: "/otel-client/tls.crt"
  - name: OTEL_EXPORTER_OTLP_CLIENT_KEY
    value: "/otel-client/tls.key"
```

Verify Service endpoints, DNS, TLS name/chain, client authentication and one canary span before
calling the deployment ready. The ConfigMap, TLS Secret and namespace are deployment prerequisites;
these manifests are not a certificate-issuing system. An ordinary ClusterIP may route across nodes;
node-local delivery needs an explicit tested traffic policy or host-port design.

**DaemonSet vs Deployment for the Collector:**

| Mode | When to Use |
|---|---|
| DaemonSet | One pod per node; local routing needs an explicit policy, while a normal Service may cross nodes |
| Deployment | Single central Collector — simpler config, useful for tail sampling which needs to see all spans from a trace |
| Sidecar | Collector runs per pod — maximum isolation, high resource overhead at scale |

---

## 9. Environment Variable Substitution in Config

The Collector supports environment-variable substitution throughout the YAML. The documented syntax is `${env:VAR_NAME}`. This is how you avoid hardcoding secrets and environment-specific values.

```yaml
exporters:
  otlp/groundcover:
    endpoint: "${env:GROUNDCOVER_ENDPOINT}"
    headers:
      Authorization: "Bearer ${env:GROUNDCOVER_API_KEY}"
```

Pass the variables via your container's environment:

```bash
docker run \
  -e GROUNDCOVER_ENDPOINT="ingest.groundcover.com:443" \
  -e GROUNDCOVER_API_KEY="${GROUNDCOVER_API_KEY:?set-a-test-key}" \
  -v ./config.yaml:/etc/otelcol-contrib/config.yaml \
  ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib:0.151.0
```

In Kubernetes, use `secretKeyRef` for secrets and `configMapKeyRef` for non-sensitive values, as shown in the DaemonSet example above.

> **Version-sensitive note**: `service.telemetry.metrics.address` was deprecated and, as of Collector `v0.123.0`, ignored. Use `service.telemetry.metrics.readers` for Collector self-metrics in current configs.

## Recap

- Receiver/exporter declarations become active only through a signal pipeline.
- Batch triggers, maximum batch size and memory refusal are distinct controls.
- Network routing, verified transport and observed canary output complete a deployment check.

## Check yourself

**Q: The receiver accepts OTLP but metrics is absent from service.pipelines. Does declaring a metrics exporter elsewhere activate it?**

<details><summary>Answer</summary>

No. No metrics pipeline connects the receiver to that exporter. Add the signal-specific receivers/processors/exporters wiring and send a known metric to prove it.

</details>

**Q: At limit_mib=512 and spike_limit_mib=128, what happens above 384 MiB?**

<details><summary>Answer</summary>

The limiter starts refusing incoming data with non-permanent errors. Upstream retries/queues determine whether it is eventually recovered or lost; above the hard threshold it also forces garbage collection.

</details>

## Try it

Keep the local trace fixture, remove debug from the traces pipeline and predict the evidence; then restore it and send checkout again.

Hint: Listening on a socket is not the final assertion.

<details><summary>Worked solution</summary>

An empty exporters list may fail configuration validation; an unreferenced exporter cannot produce the detailed checkout output. Restore a valid connected pipeline, restart the Collector and require that named span in its log.

</details>
