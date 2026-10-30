# Glossary

Lookup for the production extensions; linked chapters teach the mechanisms and their limits.

For code-design vocabulary, use the [Python design-pattern glossary](architecture/design_patterns/GLOSSARY.md).

For language and data-model vocabulary, use the [Python concepts glossary](fundamentals/core_concepts/GLOSSARY.md).

| Term | Meaning and owner |
|---|---|
| Approximate nearest neighbor (ANN) | [Similarity search that trades some recall for lower query cost.](infrastructure/search/01_search_decision_guide.md) |
| At-least-once delivery | [One logical message may be delivered repeatedly, so durable effects need duplicate handling.](infrastructure/messaging/01_broker_decision_guide.md) |
| Backfill | [A bounded migration that populates new representations for existing records.](operations/deployment/02_ci_cd_and_releases.md) |
| Backpressure | [A capacity signal that slows upstream arrival rather than accumulating unlimited work.](architecture/resilience/01_failure_budgets_and_isolation.md) |
| Blue-green rollout | [Preparing a second fleet and switching traffic between complete environments.](operations/deployment/02_ci_cd_and_releases.md) |
| Bulkhead | [A bounded resource pool that prevents one workload from consuming another workload’s capacity.](architecture/resilience/01_failure_budgets_and_isolation.md) |
| Burn rate | [Error-budget consumption speed relative to the rate allowed by the SLO.](infrastructure/observability/05_alerting_and_slos.md) |
| Canary | [A bounded production exposure used to evaluate a release before wider promotion.](operations/deployment/02_ci_cd_and_releases.md) |
| Cell | [A bounded service stack owning a subset of tenants to reduce shared failure impact.](architecture/resilience/01_failure_budgets_and_isolation.md) |
| Choreography | [Independent consumers react to facts without one central process coordinator.](architecture/event_driven_architecture/01_events_and_projections.md) |
| CI / continuous delivery | [Frequent automated integration checks, followed by keeping verified artifacts deployable.](operations/deployment/02_ci_cd_and_releases.md) |
| Circuit breaker | [A stateful permission gate that rejects calls while a dependency is predictably failing.](architecture/resilience/01_failure_budgets_and_isolation.md) |
| Command / event | [A request for a decision versus a fact already committed by its owner.](architecture/event_driven_architecture/01_events_and_projections.md) |
| Compensation | [A new business action that offsets an earlier effect without erasing history.](architecture/event_driven_architecture/01_events_and_projections.md) |
| Consumer acknowledgement | [A consumer signal that the broker may settle one delivery after its effect is safe.](infrastructure/messaging/02_rabbitmq.md) |
| Coordinated omission | [A load measurement gap when a waiting generator fails to represent arrivals during slow responses.](operations/testing/14_load_and_performance_testing.md) |
| Dead-letter queue | [Restricted storage for work removed from ordinary retry processing and awaiting repair or disposition.](infrastructure/messaging/03_sqs.md) |
| Deadline | [An end-to-end time boundary shared by every phase and retry of an operation.](architecture/resilience/01_failure_budgets_and_isolation.md) |
| Deployment / Service | [Kubernetes desired-replica controller and stable network destination with selected Pod endpoints.](operations/deployment/03_kubernetes_runtime.md) |
| Discriminated union | [A schema union whose tagged field selects the applicable variant.](fundamentals/data_validation/01_schema_compatibility.md) |
| Domain / integration event | [An internal model fact versus a versioned published contract for other services.](architecture/event_driven_architecture/01_events_and_projections.md) |
| Embedding | [A numeric representation of content used to propose similarity matches.](architecture/llm_systems/03_retrieval_augmented_generation.md) |
| Entitlement | [A tenant’s permission to use a product feature, distinct from user authorization and consumption quota.](architecture/saas_patterns/01_tenant_lifecycle_and_entitlements.md) |
| Error budget | [The allowed fraction or count of bad outcomes over the SLO window.](infrastructure/observability/05_alerting_and_slos.md) |
| Eval | [A versioned measurement of sampled model behavior under a defined configuration and rubric.](architecture/llm_systems/04_evals_and_regression.md) |
| Exclusion constraint | [A database rule rejecting row pairs whose specified relations conflict, such as overlapping intervals.](fundamentals/database/12_data_modeling_and_constraints.md) |
| Expand/contract | [A release sequence adding compatibility before later removing the old representation.](operations/deployment/02_ci_cd_and_releases.md) |
| Fencing | [Destination-enforced rejection of effects from an owner whose authority is obsolete.](architecture/resilience/01_failure_budgets_and_isolation.md) |
| Holdout set | [Evaluation cases kept separate from routine prompt development to reduce test-set overfitting.](architecture/llm_systems/04_evals_and_regression.md) |
| HPA | [HorizontalPodAutoscaler, a Kubernetes controller adjusting replica count from observed metrics.](operations/deployment/03_kubernetes_runtime.md) |
| Inbox | [A durable per-consumer event record committed atomically with a local effect to collapse duplicates.](infrastructure/messaging/05_message_contracts_and_outbox.md) |
| Incident commander | [The responder coordinating roles, priorities, decisions and handoffs during an incident.](operations/incident_response/01_on_call_and_severity.md) |
| Ingress | [A Kubernetes HTTP-routing description that requires an installed implementation.](operations/deployment/03_kubernetes_runtime.md) |
| Keyset pagination | [Advancing by the last ordered key tuple instead of skipping an increasing row offset.](fundamentals/database/11_query_performance.md) |
| Lease | [Time-bounded permission or reservation whose expiry does not itself stop a paused process.](infrastructure/messaging/03_sqs.md) |
| Load shedding | [Rejecting new work that cannot meet the service promise within available capacity.](architecture/resilience/01_failure_budgets_and_isolation.md) |
| Lockfile | [A resolved dependency/artifact selection for a declared set of environments.](fundamentals/python_packaging/01_reproducible_builds.md) |
| N+1 queries | [One initial query followed by a separate related-data query for each result.](fundamentals/database/11_query_performance.md) |
| Normalization | [Giving independently changing facts one authoritative relational owner.](fundamentals/database/12_data_modeling_and_constraints.md) |
| Open / closed workload | [Arrivals scheduled independently of completion versus a fixed client population waiting for responses.](operations/testing/14_load_and_performance_testing.md) |
| Orchestration | [A durable coordinator owns a multi-step process, its replies, deadlines and compensations.](architecture/event_driven_architecture/01_events_and_projections.md) |
| Outbox | [Publication intent stored in the same transaction as the business change and relayed later.](infrastructure/messaging/05_message_contracts_and_outbox.md) |
| Partial index | [An index containing only rows satisfying its predicate.](fundamentals/database/11_query_performance.md) |
| PodDisruptionBudget | [A Kubernetes limit on supported voluntary evictions, not a guarantee against failure or rollout disruption.](operations/deployment/03_kubernetes_runtime.md) |
| Poison message | [A message that repeatedly fails for a deterministic reason and requires repair or explicit disposition.](infrastructure/messaging/01_broker_decision_guide.md) |
| Prefetch | [A broker/client bound on deliveries held unacknowledged by push consumers.](infrastructure/messaging/02_rabbitmq.md) |
| Presigned URL | [A time-limited bearer capability for a specified object-storage operation.](fundamentals/fastapi/12_file_uploads_and_object_storage.md) |
| Projection | [Derived state optimized for reading and rebuilt or updated from an authoritative source.](architecture/event_driven_architecture/01_events_and_projections.md) |
| Prompt injection | [Untrusted input attempts to redirect model behavior or exercise unintended tool authority.](architecture/llm_systems/05_safety_cost_and_observability.md) |
| Publisher confirm | [RabbitMQ’s acknowledgement of the publication handoff under the queue’s durability rules.](infrastructure/messaging/02_rabbitmq.md) |
| Quarantine | [Storage/state that withholds an uploaded object from use until verification and policy checks pass.](fundamentals/fastapi/12_file_uploads_and_object_storage.md) |
| Quota | [A consumption limit distinct from permission to use a feature.](architecture/saas_patterns/01_tenant_lifecycle_and_entitlements.md) |
| RAG | [Retrieval-augmented generation supplies retrieved evidence to a model without making it authoritative.](architecture/llm_systems/03_retrieval_augmented_generation.md) |
| Recall@k | [The fraction of known relevant evidence retrieved among the first k candidates.](architecture/llm_systems/03_retrieval_augmented_generation.md) |
| RED / USE | [Rate-errors-duration for request services; utilization-saturation-errors for resources.](infrastructure/observability/05_alerting_and_slos.md) |
| RLS | [PostgreSQL row-level security policies constrain visible and writable rows for applicable roles.](fundamentals/database/13_multi_tenancy.md) |
| RPO / RTO | [Recovery-point objective bounds acceptable data loss; recovery-time objective bounds restoration duration.](architecture/resilience/01_failure_budgets_and_isolation.md) |
| Runbook | [A bounded diagnostic and recovery decision procedure with success and stop conditions.](operations/incident_response/02_runbooks.md) |
| Selectivity / bitmap scan | [Match fraction and a scan that groups indexed row locations into page-oriented fetches.](fundamentals/database/11_query_performance.md) |
| Selectivity | [The fraction of rows matched by a predicate, which influences access-path cost.](fundamentals/database/11_query_performance.md) |
| SLI / SLO / SLA | [A measured service indicator, its target, and a contractual service commitment respectively.](infrastructure/observability/05_alerting_and_slos.md) |
| Soft delete | [Hiding a retained row through explicit state/predicates rather than physically deleting its data.](fundamentals/database/12_data_modeling_and_constraints.md) |
| Tombstone | [A durable deletion marker preventing stale replicas, indexes or replays from serving deleted content.](architecture/llm_systems/03_retrieval_augmented_generation.md) |
| Upcaster | [A deterministic transformation from a historical message schema to a current internal representation.](fundamentals/data_validation/01_schema_compatibility.md) |
| Visibility timeout | [The SQS interval during which a received message is normally hidden from other receives.](infrastructure/messaging/03_sqs.md) |
| Wheel | [An installable Python distribution whose tags identify interpreter/platform compatibility.](fundamentals/python_packaging/01_reproducible_builds.md) |

## Code organization

| Term | Meaning and owner |
|---|---|
| Modular monolith | [Business capabilities with public contracts and owned implementation, released together.](architecture/modular_monolith/01_define_module_boundaries.md) |
| Module API / facade | [The supported call surface for a capability; a facade groups access to its owned behavior.](architecture/modular_monolith/01_define_module_boundaries.md) |
| Vertical slice | [Code grouped around one use case and its changes, within or across the necessary technical concerns.](architecture/01_architecture_decision_guide.md) |
| Port / adapter | [A consumer-owned capability contract and a translation from a concrete implementation to it.](architecture/modular_monolith/01_define_module_boundaries.md) |
| Composition root | [The process edge that constructs concrete implementations and connects their dependencies.](architecture/modular_monolith/01_define_module_boundaries.md) |
| Transaction script / service layer | [A procedure implementing one business operation, and the application call boundary exposed to entry points.](architecture/01_architecture_decision_guide.md) |
| Bounded context | [A boundary within which a business model and its language have consistent meaning.](architecture/01_architecture_decision_guide.md) |
| CQRS | [Separate models for changing state and reading it; not inherently separate services or event sourcing.](architecture/event_driven_architecture/03_cqrs_read_and_write_models.md) |
| Unit of Work | [One owner deciding whether a group of related persistence changes commits or rolls back.](architecture/modular_monolith/02_build_and_test_a_modular_monolith.md) |
| Idempotency | [Repeating the same logical request preserves its intended effect within an explicitly scoped guarantee.](architecture/modular_monolith/02_build_and_test_a_modular_monolith.md) |

## Terms used in the repaired runtime paths

| Term | Meaning and canonical owner |
|---|---|
| Admission deadline | [Maximum wait to obtain permission to start; it ends before execution begins.](fundamentals/fastapi/safe_and_scalable_api_calls/02_concurrency_and_timeouts.md) |
| Response start | [The outgoing ASGI event that commits HTTP status and headers before later body messages.](fundamentals/fastapi/05_middleware.md) |
| MISSING | [Pydantic's explicit absent-value sentinel, distinct from a submitted null.](fundamentals/fastapi/03_pydantic.md) |
| QUERY | [A safe, idempotent HTTP method for queries expressed in request content, subject to client/proxy support.](apis/restful/02_http_semantics.md) |
| Unknown usage | [A durable provider-spend obligation retained until authoritative usage evidence allows settlement.](fundamentals/fastapi/safe_and_scalable_api_calls/10_llm_token_economics.md) |
