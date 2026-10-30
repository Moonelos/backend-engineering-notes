# Core Python Concepts

Read unfamiliar Python code by tracing what names refer to, when functions run, how attributes
are resolved, and where data is validated. Use the runtime guides when you own application
configuration, resource lifetimes, logs or shutdown.

**Audience:** you can read basic literals, loops, simple functions/classes and imports.
No prior knowledge of descriptors, dataclasses or Pydantic is required.
**Baseline:** Python 3.11+ and Pydantic v2. Newer behavior is explicitly version-labeled.

## Start here

- **Understand sophisticated Python code:** [Names and mutability](language/names_and_mutability.md).
- **Learn dataclasses and Pydantic:** [Data models](data_models/README.md).
- **Understand getattr, properties or framework internals:** [Objects](objects/README.md).
- **Configure and operate a service:** [Application runtime](runtime/README.md).

## Contents

| Area | What you learn | Entry point |
|---|---|---|
| Language | Names, functions, scope, idioms, imports, decorators and standard-library tools | [Language](language/README.md) |
| Objects | Classes, methods, attributes, introspection, special methods and descriptors | [Objects](objects/README.md) |
| Typing | Static contracts, generics, protocols and a type-checker feedback loop | [Typing](typing/README.md) |
| Data models | Dataclasses, enums, named tuples, Pydantic validation and serialization | [Data models](data_models/README.md) |
| Control flow | Exceptions, lazy iteration and resource lifetimes | [Control flow](control_flow/README.md) |
| Runtime | Configuration, logging, signals and graceful shutdown | [Runtime](runtime/README.md) |

## Read everyday Python

1. [Names and mutability](language/names_and_mutability.md): assignment, aliases, copying and identity.
2. [Functions and scope](language/functions_and_scope.md): signatures, defaults and closures.
3. [Classes and methods](objects/classes_and_methods.md): shared/per-instance state and method binding.
4. [Attributes and introspection](objects/attributes_and_introspection.md): dynamic access and properties.
5. [Dataclasses](data_models/dataclasses.md): generated methods with explicit data ownership.
6. [Pydantic models and fields](data_models/pydantic/01_models_and_fields.md): validate external input.

**First milestone, after entry 2:** predict a shared-list bug and a closure's later result.
**Stop after entry 6** when you can explain which operation creates, changes or validates an
object. Continue through [validation and serialization](data_models/pydantic/README.md) when
input and output need different contracts.

Alongside this path, [idioms and collections](language/idioms_and_collections.md) makes dense
expressions readable. [Modules and imports](language/modules_and_imports.md) explains when
module-level code executes.

## Read framework internals

First complete names, functions, classes and attributes above. Then read:

1. [Modules and imports](language/modules_and_imports.md): import caching and registration.
2. [Protocols and descriptors](objects/protocols_and_descriptors.md): operator and attribute dispatch.
3. [Decorators](language/decorators.md): rebinding, wrappers, factories and registration.
4. [Typing](typing/README.md): interpret annotations in the resulting public interface.

**Stop** once you can trace a call or lookup to its owner. Metaclass authoring is a specialist
concern; recognizing one does not require implementing one.

## Operate a Python backend

This continuation assumes functions, classes and basic annotations are familiar.

1. [Exceptions](control_flow/exceptions.md): decide where failure is handled or translated.
2. [Iterators and generators](control_flow/iterators_and_generators.md), then
   [context managers](control_flow/context_managers.md): connect lazy execution with cleanup.
3. [Configuration](runtime/configuration.md): validate startup settings and own their lifetime.
4. [Logging](runtime/logging/README.md): trace records and configure one owned pipeline.
5. [Signals](runtime/signals.md): stop intake, drain work and close resources within a deadline.

**Stop** when your application owns those boundaries. Use [Concurrency](../concurrency/README.md)
for execution models, [packaging](../python_packaging/README.md) for build artifacts, and
[schema compatibility](../data_validation/README.md) when data outlives a deployment.

## What's changing

Checked 2026-10-30. These version bridges do not silently raise the 3.11 teaching baseline.

| Item | Status | Placement and consequence | Source |
|---|---|---|---|
| Generic parameters and `type` aliases, 3.12+ | GA | Typing distinguishes newer syntax from 3.11 `TypeVar` | [Python 3.12](https://docs.python.org/3.12/whatsnew/3.12.html) |
| `TypeIs`, 3.13+ | GA | Typing contrasts it with `TypeGuard` | [Python 3.13](https://docs.python.org/3.13/whatsnew/3.13.html) |
| Deferred annotations and `annotationlib`, 3.14+ | GA | Introspection may evaluate expressions; see the typing version bridge | [Annotation guidance](https://docs.python.org/3.14/howto/annotations.html) |
| Template strings, 3.14+ | GA | `t"…"` creates a template object; processing owns rendering/escaping | [Python 3.14](https://docs.python.org/3.14/whatsnew/3.14.html) |
| Pydantic v1-style methods/configuration | DEPRECATED | Extracted lessons retain a corrected migration guide | [Migration](https://docs.pydantic.dev/latest/migration/) |
| Pydantic experimental APIs | PREVIEW | Outside the stable foundation; evaluate documented limits before adoption | [Experimental features](https://docs.pydantic.dev/latest/concepts/experimental/) |

[Glossary](GLOSSARY.md) links unfamiliar vocabulary to its explanation.
