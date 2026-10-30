# Architecture and Code Organization

> Choose code boundaries, compose application capabilities, and carry their guarantees into production.

[![FastAPI](https://img.shields.io/badge/FastAPI-async-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Redis](https://img.shields.io/badge/Redis-pub%2Fsub%20%2F%20streams-DC382D.svg?logo=redis&logoColor=white)](https://redis.io)
[![Dramatiq](https://img.shields.io/badge/Dramatiq-workers-7B4EA6.svg)](https://dramatiq.io)

These guides assume familiarity with the fundamentals. They show how the pieces compose into production systems.

---

## Contents

| Topic | Description |
|-------|-------------|
| [Choosing a code structure](01_architecture_decision_guide.md) | Compare layers, vertical slices, modular monoliths, ports/adapters, domain models and service boundaries |
| [Python design patterns](design_patterns/README.md) | Runnable choices for Strategy, factories, Adapter/Facade, commands, wrappers, Specification, State and construction |
| [Modular Monolith](modular_monolith/README.md) | Business modules, public APIs, selective ports, an executable three-module workflow, transaction tests and evolution |
| [Hexagonal Architecture](hexagonal_architecture/README.md) | A 13-part path from one runnable vertical slice through ports, transactions, runtime composition, GenAI, testing, migration, and a service/shared-library case study |
| [Long-Running Tasks](long_running_tasks/README.md) | Handling requests that take seconds to hours: orchestration, worker patterns, client delivery, infrastructure, sagas/outbox |
| [LLM systems](llm_systems/README.md) | Provider boundaries, schemas, RAG, evals and bounded authority/spend |
| [Event-driven architecture](event_driven_architecture/README.md) | Local dispatch, domain events, CQRS, projections, consistency and replay |
| [Resilience](resilience/README.md) | Deadlines, retry budgets, cells and regional recovery |
| [SaaS patterns](saas_patterns/README.md) | Tenant lifecycle, entitlements and quotas |

---

## Choose a learning path

**Organizing a growing application:** start with [Choose a code structure](01_architecture_decision_guide.md),
then [define module boundaries](modular_monolith/01_define_module_boundaries.md) and
[run the modular monolith](modular_monolith/02_build_and_test_a_modular_monolith.md). The module path
produces a working result by entry 2: one answer and one usage record, with replay and rollback tests.
Continue to [production evolution](modular_monolith/03_operate_and_evolve_boundaries.md) for failure
recovery, migration and extraction decisions.

**Choosing abstractions inside a use case:** read [Choose the smallest abstraction](design_patterns/01_choose_the_smallest_abstraction.md),
then [run interchangeable retrieval strategies](design_patterns/02_select_behavior_and_build_dependencies.md).
Continue to the pattern matching your next change: vendor translation, command handlers, wrappers
or state-dependent rules. [Local events](event_driven_architecture/02_local_events_and_dispatch.md)
and [CQRS with one database](event_driven_architecture/03_cqrs_read_and_write_models.md) are
independent continuations when reactions or read models need different owners.

**Separating business policy from frameworks and providers:** begin with
[Why Hexagonal Architecture](hexagonal_architecture/01_why_hexagonal_architecture.md), then
[Build one vertical slice](hexagonal_architecture/02_build_one_vertical_slice.md). Follow the
[hexagonal index](hexagonal_architecture/README.md) for dependency direction, ports, runtime
composition and testing.

These paths compose: a modular monolith can use hexagonal boundaries inside selected modules.
Deployment structure, business ownership and dependency direction are separate decisions.

**Stop after the runnable baseline** when it establishes the boundaries your application needs.
Continue into [Long-Running Tasks](long_running_tasks/README.md) when work must outlive an HTTP
request, or [event-driven architecture](event_driven_architecture/README.md) when independent
consumers need durable delivery and explicit consistency.

---

## Prerequisites

The code-organization guide assumes Python functions and imports; the modular-monolith tutorial also uses context managers and basic SQL. The deeper runtime paths draw on:

- **[fundamentals/concurrency/](../fundamentals/concurrency/)** — async/await, threading, multiprocessing, the GIL
- **[background_work/](../background_work/)** — Dramatiq, task queues, scheduling
- **[infrastructure/redis/](../infrastructure/redis/)** — caching, pub/sub, data structures
- **[fundamentals/fastapi/](../fundamentals/fastapi/)** — HTTP APIs, dependency injection, middleware
