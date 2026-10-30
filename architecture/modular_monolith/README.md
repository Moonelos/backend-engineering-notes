# Modular monoliths: business boundaries inside one application

Build an application where agents, conversations and usage have clear owners, public contracts and
enforced dependencies. Combine modules with use-case slices and ports where they pay for themselves.

**Audience:** readers comfortable with typed Python, imports, context managers and basic SQL.
**Baseline:** Python 3.11+ and standard-library SQLite; verified with Python 3.14.6. The example
uses a deterministic fake provider and a temporary database, without a live HTTP server or broker.

## Learning path

| Order | Note | Role | Outcome |
|---|---|---|---|
| Optional | [Choose a code structure](../01_architecture_decision_guide.md) | Decision guide | Compare layers, slices, modules, ports and services on the same problem |
| 1 | [Define module boundaries](01_define_module_boundaries.md) | Foundation | Trace public APIs, private implementation and data ownership |
| 2 | [Build and test the monolith](02_build_and_test_a_modular_monolith.md) | Tutorial | Run three modules, replay a request, test rollback and reject forbidden imports |
| 3 | [Operate and evolve boundaries](03_operate_and_evolve_boundaries.md) | Decision guide | Diagnose failures, choose communication and plan migration or extraction |

**Working result by entry 2:** one accepted answer and one usage unit, even when the same request
is replayed. Stop after entry 2 if you need a local model of module ownership and transactions.
Continue to entry 3 before adapting it to external providers, multiple replicas or independent
services. It supplies design and operational checks; it does not claim a production deployment.

The [example source](examples/modular_app/demo.py) is intentionally small. Public persistence
facades use concrete SQLite. The provider is behind a port because that is the changing external
capability in this example. This is a different policy from the
[hexagonal course's selected convention](../hexagonal_architecture/README.md), which mandates
application I/O ports. Both approaches can organize a modular monolith; choose deliberately.

## What's changing

Checked **2026-10-30**. The ownership principles are stable; enforcement tooling evolves.

- **GA:** Import Linter's maintained contracts include protected modules and acyclic siblings.
  Its 2.14 release added guidance for broken contracts; 2.15 added lazy-import support to its
  exploration tools. These help teams understand violations; they do not establish database
  ownership. See [release notes](https://import-linter.readthedocs.io/en/stable/release_notes/).
- **DEPRECATED:** Python 3.7 support was removed in Import Linter 1.10. Check tool/runtime
  compatibility before adopting an old configuration or pin; this example needs no linter package.
  See the same [compatibility history](https://import-linter.readthedocs.io/en/stable/release_notes/).
- **GA, comparative ecosystem:** [Spring Modulith](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
  explicitly models module APIs and internal components and supports structural verification.
  It is a Java option, not a Python dependency or a reason to add a framework here.
- **PREVIEW context:** the [Spring Modulith release stream](https://github.com/spring-projects/spring-modulith/releases)
  includes prereleases as well as stable releases. This path does not depend on those previews.

## Continue only for the requirement you have

- Infrastructure-independent application policy: [Hexagonal Architecture](../hexagonal_architecture/README.md).
- Work must survive process loss: [Minimal durable task](../../background_work/foundations/03_minimal_durable_task.md).
- Independent consumers need reliable delivery: [Message contracts and outbox](../../infrastructure/messaging/05_message_contracts_and_outbox.md).
- Real database concurrency and isolation: [Database foundations](../../fundamentals/database/README.md).
- Runtime-managed HTTP clients and pools: [FastAPI](../../fundamentals/fastapi/README.md).
