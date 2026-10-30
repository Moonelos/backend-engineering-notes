# Design patterns for Python backend decisions

Choose a small abstraction because it protects a changing decision. Build an investigation feature
with explicit collaborators, then learn how to select behavior, translate vendors, dispatch actions,
wrap operations and model rules without turning every function into a class hierarchy.

**Audience:** readers comfortable with Python functions, classes, exceptions, basic annotations and
dataclasses. Pattern vocabulary is introduced here. Use the [typing bridge](../../fundamentals/core_concepts/typing/typing.md)
for `Callable` and `Protocol`, and [context managers](../../fundamentals/core_concepts/control_flow/context_managers.md)
for resource lifetime. SQL is only needed for the linked CQRS branch, which supplies a short bridge.

**Baseline:** Python 3.11+ syntax and standard library. The examples use local data and deterministic
fakes; no accounts, provider calls or running infrastructure are needed. The local verification
runtime is Python 3.14.6. Real database, worker and provider guarantees belong to the linked
production continuations; a local object pattern does not establish those guarantees.

## Choose a path

**First time:** read 01, then run 02. By entry 2 you can change retrieval behavior without changing
the investigation action, reject unknown construction settings, and explain who owns each object.
Stop there if selecting a collaborator solves the problem. Chapters 03–06 branch from that base;
follow the one matching the next change in your application.

| Order | Lesson | Role | What you can decide or demonstrate |
|---|---|---|---|
| 1 | [Choose the smallest abstraction](01_choose_the_smallest_abstraction.md) | Foundation | Find the changing decision, pass a function, and distinguish an interface from its behavioral contract |
| 2 | [Select behavior and build dependencies](02_select_behavior_and_build_dependencies.md) | Tutorial | Strategy through callables/configured objects; explicit factories, registries and lifetimes |
| 3 | [Adapt, translate and simplify](03_adapt_translate_and_simplify.md) | Tutorial | Adapter versus Facade versus Anti-Corruption Layer around the same integration |
| 4 | [Commands and application handlers](04_commands_and_application_handlers.md) | Tutorial | One action reached through different entry points, with explicit transaction and retry boundaries |
| 5 | [Wrap and chain behavior](05_wrap_and_chain_behavior.md) | Tutorial | Decorator ordering, unwind, pipelines and short-circuiting chains |
| 6 | [Model rules and state](06_model_rules_and_state.md) | Tutorial | Specification predicates, state transitions and when State objects are useful |
| Conditional | [Construction and inheritance trade-offs](07_construction_and_inheritance_tradeoffs.md) | Decision guide | Builder, Template Method and shared resource lifetimes versus global Singletons |

**Events and read models:** use [local event dispatch](../event_driven_architecture/02_local_events_and_dispatch.md)
for Observer-style reactions, then [CQRS with one database](../event_driven_architecture/03_cqrs_read_and_write_models.md)
for different write/read needs. Each has a standalone runnable result. Read the event chapter's
failure trace before introducing a broker; local handler invocation has no durable delivery promise.

**Construction choices:** read 01 → 02 → the conditional comparison. Stop when you can justify a
constructor, factory, builder or shared scope from the work it owns. Full Factory Method and
Abstract Factory hierarchies are comparative vocabulary here, not required application structure.

## Locate the pattern's complete implementation

Several patterns already have deeper owners elsewhere. This map keeps transaction and distributed
failure behavior attached to the chapters that teach and verify it.

| Need | Canonical continuation |
|---|---|
| Keep business logic independent of transports and vendors | [Hexagonal vertical slice](../hexagonal_architecture/02_build_one_vertical_slice.md) and [dependency direction](../hexagonal_architecture/03_dependencies_point_toward_business_policy.md) |
| Design an I/O port or a repository around business needs | [Ports and adapter contracts](../hexagonal_architecture/05_design_ports_and_adapter_contracts.md) |
| Make several persistence operations atomic | [Unit of Work mechanism](../hexagonal_architecture/05_design_ports_and_adapter_contracts.md#6-a-unit-of-work-makes-several-repositories-one-transaction) and [runnable shared transaction](../modular_monolith/02_build_and_test_a_modular_monolith.md) |
| Construct, share and close dependencies | [Runtime composition](../hexagonal_architecture/06_compose_the_runtime_at_the_edge.md); [FastAPI dependencies](../../fundamentals/fastapi/02_dependency_injection.md) for framework integration |
| Understand Python decorator evaluation and function metadata | [Decorator language mechanisms](../../fundamentals/core_concepts/language/decorators.md) |
| Put request-wide wrappers in an HTTP application | [Middleware and ordering](../../fundamentals/fastapi/05_middleware.md) |
| Coordinate work across restarts or concurrent workers | [State-machine design](../../background_work/workflows/01_state_machine_design.md) |
| Publish a durable event after a business change | [Atomic transitions and outbox](../../background_work/reliability/01_atomic_transitions_and_outbox.md) and [integration contracts](../../infrastructure/messaging/05_message_contracts_and_outbox.md) |
| Handle repeated delivery or an ambiguous external effect | [Idempotency and recovery](../../background_work/reliability/03_idempotency_and_external_effects.md); [HTTP idempotency](../../apis/restful/06_concurrency_idempotency_and_retries.md) for request keys |
| Bound retries and stop hammering a failing dependency | [Retry budgets and circuit breakers](../resilience/01_failure_budgets_and_isolation.md) |
| Relate patterns to a complete AI backend | [Annotated investigation case study](../hexagonal_architecture/12_trace_an_investigation_across_services.md#8-map-the-patterns-to-the-problem-they-solve) and [provider boundaries](../llm_systems/01_provider_abstraction.md) |

This sequence implements the general pattern lessons with functions and explicit collaborators.
The [hexagonal course](../hexagonal_architecture/README.md) requires application I/O ports as its
selected convention; the [modular-monolith path](../modular_monolith/README.md) uses ports selectively.
A callable used as an internal Strategy is not automatically an application I/O port. Choose the
course's policy deliberately rather than inferring it from the existence of a Protocol.

## What's changing

Checked **2026-10-30** against primary Python documentation. The examples keep the 3.11+ baseline;
these are compatibility considerations, not requirements to adopt another runtime.

- **GA:** [Python 3.14 deferred annotations](https://docs.python.org/3.14/whatsnew/3.14.html#deferred-evaluation-of-annotations)
  matter to containers that infer dependencies by reading annotations. Explicit wiring here needs
  no annotation inspection; review a container's supported introspection before a runtime upgrade.
- **GA:** [Python 3.15 explicit lazy imports](https://docs.python.org/3.15/whatsnew/3.15.html)
  defer module execution. Chapter 02 explains why registration by import side effect needs care;
  the baseline builds an explicit registry.
- **DEPRECATED:** older collection aliases in `typing` have replacements in built-ins and
  `collections.abc`. The examples use those forms; see the
  [typing documentation](https://docs.python.org/3.14/library/typing.html#deprecated-aliases).
- **PREVIEW:** [Python 3.16 alpha](https://www.python.org/downloads/release/python-3160a1/)
  is compatibility-testing context, not the tested teaching environment. No alpha-only feature
  is needed for these patterns.

For terms, use the [pattern glossary](GLOSSARY.md). For the broader structural choice, begin with
the [architecture decision guide](../01_architecture_decision_guide.md).
