# Logging

> Python's `logging` module — from the first record to hierarchy mechanics,
> handler routing, async-safe queues, framework integration, and production
> ownership.

---

## Contents

| File | Topic | Description |
|------|-------|-------------|
| [01_basics.md](01_basics.md) | Basics | Record mental model, module loggers, levels, lazy formatting, exceptions, destinations |
| [02_hierarchy_and_propagation.md](02_hierarchy_and_propagation.md) | Hierarchy & Propagation | Effective levels, direct ancestor-handler propagation, `propagate`, duplicate diagnosis |
| [03_handlers_and_formatters.md](03_handlers_and_formatters.md) | Handlers & Formatters | Full pipeline, stream/file behavior, filters, buffering, async `QueueHandler` lifecycle |
| [04_patterns.md](04_patterns.md) | Patterns | `basicConfig` vs `dictConfig`, dedicated subtrees, libraries, frameworks, multi-process limits |
| [structlog_guide.md](structlog_guide.md) | Structured logging | Processor pipelines, shared stdlib output, request context and field-based tests |

---

## Reading Order

1. **Basics** — understand what a log call creates and who owns configuration
2. **Hierarchy & Propagation** — learn the admission gate and ancestor-handler walk
3. **Handlers & Formatters** — route, filter, render, queue, and shut down records
4. **Patterns** — choose a topology for scripts, services, frameworks, and libraries
5. **Structured logging** — represent events as fields and connect structlog to the owned pipeline

**Milestone:** after entry 1, the program emits `INFO __main__ application started`. Stop there for a
small script with one destination. Continue when logger hierarchy, multiple destinations, queued
delivery, or framework-owned configuration is part of the process.

---

## Prerequisites

- [exceptions.md](../../control_flow/exceptions.md) — know where failures should be handled and logged
- For production structured logging, continue to [structlog_guide.md](structlog_guide.md)

[Back to Application runtime](../README.md)
