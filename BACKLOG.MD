# Documentation Backlog

Last reconciled: 2026-10-30.

The July backlog has been implemented where it adds distinct learning value. Existing Kafka,
webhook, recovery and API-call material remains canonical. The tables below record where each
item landed, including intentional consolidation and changed filenames. No original topic was
silently dropped. Infrastructure-dependent examples still require the service checks described
in their chapters; documentation completion does not mean a production deployment was exercised.

## P0 — delivered

| Original item | Resolution |
|---|---|
| CI/CD and releases | [Release engineering](operations/deployment/02_ci_cd_and_releases.md): pipeline gates, GitHub Actions, environments/OIDC, immutable artifacts, compatible migrations, rollout strategies, verification and recovery. |

## P1 — delivered or integrated with existing courses

| Original item | Resolution |
|---|---|
| Messaging section | [Messaging](infrastructure/messaging/README.md): delivery-model selection, RabbitMQ, SQS, message contracts and outbox/inbox. Existing [Kafka](infrastructure/kafka/README.md), [Redis Streams](infrastructure/redis/02_pubsub_and_streams.md) and [JetStream](infrastructure/nats_jetstream/README.md) supply their full implementations. No duplicate `04_kafka.md`. |
| Alerting and SLOs | [Alerting and SLOs](infrastructure/observability/05_alerting_and_slos.md): user outcomes, budgets/burn rates, RED/USE, paging, dashboards, correlation and owned runbooks. |
| Query performance | [Query performance](fundamentals/database/11_query_performance.md): plans, scan/index choices, pagination, ORM query counts, locks, statistics and benchmark hygiene. Uses 11 because 07–10 already exist. |
| LLM architecture | [LLM systems](architecture/llm_systems/README.md): provider boundaries, prompts/schemas, authorized RAG, evals, least-privilege tools, budgets and telemetry. Reuses existing deterministic LLM testing and API-call controls. |

## P2 — delivered or consolidated

| Original item | Resolution |
|---|---|
| Load and performance testing | [Load testing](operations/testing/14_load_and_performance_testing.md): workload types/tools, open versus closed arrivals, percentiles, dependency ceilings and regression gates. |
| Incident response | [Incident response](operations/incident_response/README.md): severity/on-call, worked runbooks and blameless postmortems. |
| Kubernetes runtime | [Kubernetes runtime](operations/deployment/03_kubernetes_runtime.md): controllers, configuration/secrets, probes, resource/connection budgets, rollout/disruption, HPA and shutdown. |
| Data modeling and constraints | [Modeling](fundamentals/database/12_data_modeling_and_constraints.md): constraints, normalization, historical facts, soft deletes, temporal ranges, state transitions and JSONB. Uses 12 to preserve existing numbering. |
| Multi-tenancy | [Tenant isolation](fundamentals/database/13_multi_tenancy.md): isolation models, RLS, request/transaction context, noisy neighbors, cache/quotas and lifecycle operations. Uses 13 to preserve existing numbering. |
| Uploads and object storage | [Uploads](fundamentals/fastapi/12_file_uploads_and_object_storage.md): bounded bytes, temporary storage, untrusted MIME, quarantine/scanning, presigned URLs, immutable object versions, authorized downloads and cleanup. |
| Webhooks and integrations | Already developed in the six-chapter [webhook course](apis/webhooks/README.md), including signatures, timestamp windows, inbox/outbox, idempotency/retries/replay, delivery logs and tests. Added a FastAPI navigation bridge instead of duplicate `13_webhooks_and_integrations.md`. |
| Secrets | [Secret lifecycle](infrastructure/secrets/README.md): manager choices, workload identity, rotation, leases, revocation, scanning and leakage prevention. |
| Event-driven architecture | [Events and projections](architecture/event_driven_architecture/README.md): facts/commands, domain/integration contracts, choreography/orchestration, eventual consistency and replay. Reuses canonical outbox/inbox implementations. |
| Resilience | [Resilience](architecture/resilience/README.md): deadlines, retry/failure budgets, circuit breakers, bulkheads, backpressure, degradation, cells and regional recovery. |

## P3 — valuable focused additions

| Original item | Resolution and scope decision |
|---|---|
| Python packaging | [Packaging](fundamentals/python_packaging/README.md): dependency intent, resolved locks, build backends, wheels and tested artifacts. A decision guide avoids imposing a new package manager on this notes repository. |
| Data validation | [Schema evolution](fundamentals/data_validation/README.md) adds compatibility, nullable/missing semantics, version dispatch and upgrade order. [Existing Pydantic](fundamentals/fastapi/03_pydantic.md) remains the deeper API/model reference. |
| Search | [Search selection](infrastructure/search/README.md): PostgreSQL lexical/trigram, OpenSearch, vectors, filtered recall, freshness and index lifecycle. Managed-cluster installation is outside this selection lesson. |
| Standalone object storage | Consolidated into [uploads/object lifecycle](fundamentals/fastapi/12_file_uploads_and_object_storage.md), where authorization, metadata and bytes form one lesson. No redundant directory. |
| Cost management | [Unit costs and budgets](operations/cost_management/README.md): allocation/tags, accepted-task cost, cloud/LLM spend, Redis/PostgreSQL sizing and immediate admission versus delayed alerts. |
| Multi-region | Consolidated into [resilience](architecture/resilience/01_failure_budgets_and_isolation.md): active/passive, active/active ownership, replication lag, fencing, failover/failback and tested RPO/RTO. A full multi-region database deployment course is not needed for this decision scope. |
| SaaS patterns | [Tenant lifecycle](architecture/saas_patterns/README.md): provisioning, entitlements, quotas, billing notification reconciliation, suspension and deletion. Provider-specific tax/invoice implementation is excluded. |
| Developer experience | [Local workflows](operations/developer_experience/README.md): bootstrap, command wrappers, CI parity, hooks, containers and synthetic idempotent seeds. No new publishing or application tooling was installed in this repo. |

## Already covered enough for now

| Topic | Canonical location |
|---|---|
| FastAPI request handling and dependency injection | [FastAPI](fundamentals/fastapi/README.md) |
| Pydantic construction, validators and serialization | [Pydantic](fundamentals/fastapi/03_pydantic.md) |
| JWT/OAuth and authentication | [Authentication](fundamentals/auth/README.md) |
| Error responses, streaming and SSE | [FastAPI](fundamentals/fastapi/README.md) and [safe API calls](fundamentals/fastapi/safe_and_scalable_api_calls/README.md) |
| Background jobs and workflow recovery | [Background work](background_work/README.md) |
| Async SQLAlchemy, pools, migrations, backup and privileges | [Databases](fundamentals/database/README.md) |
| Redis patterns and persistence | [Redis](infrastructure/redis/README.md) |
| OpenTelemetry setup and export | [Observability](infrastructure/observability/README.md) |
| LLM deterministic code testing | [Testing LLM code](operations/testing/13_testing_llm_code.md) |

## Architecture and design-pattern integration

The supplied Python architecture/design-pattern outline is integrated through the
[Python design-pattern path](architecture/design_patterns/README.md). New lessons teach callable
Strategy and factories, Adapter/Facade/Anti-Corruption Layer, commands, wrappers/chains,
Specification/State, and conditional Builder/Template Method/Singleton choices. The
[event-driven path](architecture/event_driven_architecture/README.md) adds local event dispatch and
same-database CQRS. Existing hexagonal, modular-monolith, resilience, outbox and idempotency lessons
remain the detailed owners for mechanisms already covered. The architecture decision guide and
investigation case study connect the code patterns to deployment and recovery boundaries.

## Maintenance rules

- Add a future item only with a concrete learner gap, intended outcome and canonical owner.
- Prefer extending one coherent lesson over creating a parallel introduction.
- Preserve existing chapter numbers and update learning paths when adding prerequisites.
- Recheck primary sources for security, infrastructure and provider-specific behavior.
- Record actual execution separately from syntax checks and expected results.

## Audit maintenance — 2026-10-30

The October audit corrections are integrated into the canonical lessons: request mapping and
validation, token profiles, middleware/stream lifetimes, durable webhook processing, bounded
provider calls, worker fencing, broker recovery, database ownership and process shutdown.
Worked failure traces, diagrams and retrieval exercises accompany the repaired mechanisms.

Runnable local fixtures now cover signed durable receipt, duplicate/poison events, cancellation,
shared admission races, durable usage and idempotency, and container/process lifecycle. Version
migration notes distinguish the pinned teaching stacks from current FastAPI, Pydantic, HTTPX2,
SQLAlchemy, PostgreSQL and broker behavior. Independent maintenance reviews resolved their
observed critical/high findings. Live cloud provisioning, production cluster rollouts, real
provider billing contracts and deployment-specific TLS/load checks remain explicit continuations.
