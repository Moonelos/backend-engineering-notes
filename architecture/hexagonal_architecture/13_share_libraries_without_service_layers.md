# Share Libraries Without Duplicating Service Layers

> **Who this is for**: Engineers deciding what belongs in shared Python packages and how those packages connect to service-owned ports.

## 1. Sharing a database reader does not move the application's contract

Two services need data from the same external database. Copying the query implementation means
fixing it twice. Importing one service's private repository from the other couples their package
structures. A focused shared reader solves that problem while each service keeps its own contract.

The supplied worker uses this arrangement:

```text
InvestigateException needs ExceptionData or a stable source failure
  → worker.ports.investigation.exception_source defines that conversation
  → worker.db.ctc.exception_repository translates it
  → ctc_database fetches data using SQLAlchemy
  → worker adapter converts the library result into worker-owned ExceptionData
```

The adapter remains useful after extraction because it translates both types and failures.
If the library changes its result representation, the service can absorb that change here without
rewriting investigation policy. No second copy of the service port is required inside the library.

**Default:** keep each admitted library organized around one capability and one library kind,
with cohesive modules rather than service-shaped `application/`, `ports/`, or `adapters/` folders.
`libs/` states how code is packaged and reused; it does not declare that code to be domain logic.

This decision guide uses the supplied `temp/libs` and `temp/services` samples. Paths identify
those examples, but their temporary presence is not required to understand the excerpts below.

---

## 2. These three libraries have different architectural responsibilities

After following the reader call above, inspect the smaller package trees:

```text
libs/
├── ctc_database/
│   ├── pyproject.toml
│   ├── src/ctc_database/
│   │   ├── __init__.py
│   │   ├── engine.py
│   │   ├── candidates.py
│   │   ├── exceptions.py
│   │   ├── models.py
│   │   └── acceptance.py
│   └── tests/
├── platform_db/
│   ├── pyproject.toml
│   ├── src/platform_db/
│   │   ├── base.py
│   │   └── models/
│   └── tests/contract/
└── platform_observability/
    ├── pyproject.toml
    ├── src/platform_observability/
    │   ├── logging.py
    │   └── providers.py
    └── tests/
```

This is an abbreviated navigation tree. Each `pyproject.toml` declares the installable package's
dependencies and build configuration; `src/` contains its importable Python package. The libraries
have their own test responsibilities without acquiring process entry points or supervisors. These
are existing comparative source shapes, not an approved scaffold under the current library-kind rules.

| Library | Shared responsibility | Service responsibility that stays local |
|---|---|---|
| `ctc_database` | Read-only query mechanics, connection construction, data and error contracts | Which data an action needs, translation to its port, configuration and engine disposal |
| `platform_db` | SQLModel table mappings and database schema metadata | Use cases, transaction scope, repository queries, domain views |
| `platform_observability` | Logging and OpenTelemetry provider setup and shutdown mechanics | Service identity, resolved configuration, when to initialize and close providers |

SQLModel classes in `platform_db` are object-relational mappings, or **ORM models**: Python
representations of database tables. Sharing them does not make them pure domain objects.
OpenTelemetry providers configure tracing, metrics, and log export; their shared implementation
still belongs at the infrastructure edge of each process.

`ctc_database/exceptions.py` queries business exception records. The name is understandable in
that domain but can be mistaken for Python error definitions. `exception_reader.py` would improve
navigation if the project chooses to rename it; this is a naming preference, not an architectural
reason to add layers.

The current standard separates pure contracts, concrete clients, and persistence metadata.
`platform_db` illustrates persistence metadata; `platform_observability` illustrates observability
mechanics. The CTC package combines business queries, result/error contracts, and engine construction,
so it needs reconciliation before becoming a new canonical library. Separate neutral shared
vocabulary from concrete access mechanics; keep service-owned business SQL in its persistence
implementation. A repository-scoped database-runtime exception can admit technical engine/session
factories, transaction mechanics, and readiness SQL from resolved inputs. It does not admit
business queries, ORM business models, service policy, settings, or secrets. Merely naming that
exception cannot approve all of `ctc_database`.

> **Core:** classify a shared package by what it knows and does. An internal database library is
> just as concrete a database dependency as an external one.

---

## 3. A local adapter earns its place through translation

The worker's CTC adapter imports both `ctc_database` and worker-owned port types. The shared reader
does not need to know the worker exists. An explanatory excerpt from the adapter's failure
translation is:

```python
try:
    result = await self._reader.fetch(exception_id, rec_schema=rec_schema)
except ctc_database.ExceptionNotFoundError as exc:
    raise ExceptionNotFoundError(exception_id) from exc
except ctc_database.NoLinkedRecordsError as exc:
    raise NoLinkedRecordsError(exception_id) from exc
except ctc_database.ExceptionSourceUnavailableError as exc:
    raise ExceptionSourceUnavailableError(
        f"Failed to fetch CTC exception {exception_id!r}"
    ) from exc
```

The unqualified errors come from `worker.ports.investigation.exception_source`, not from the
library. Successful results are also mapped: the adapter copies the exception identity, version,
view, and linked records into the worker's `ExceptionData` and `LinkedRecord` types.

Both error classes may currently have the same name and message. Their separate ownership still
has value: one describes the library API, while the other describes outcomes the worker promises
to understand. The adapter is the place where that compatibility is maintained.

```text
library raises source unavailable
  → adapter raises worker-owned source unavailable
  → InvestigateException classifies a transient failure
  → failure recorder and delivery adapter arrange the next attempt
```

Do not wrap every shared function automatically. A pure calculation with a stable, suitable
signature can be called directly. If a concrete library already satisfies an application-owned
protocol, bootstrap may inject it directly when the type and error semantics also match.
A forwarding wrapper with no translation, isolation, or behavior adds navigation without value.

**Success signal:** replacing the shared reader with a deterministic fake tests investigation
policy without SQLAlchemy objects; adapter tests separately prove result and failure conversion.
If the action must catch `ctc_database` errors, the service has accepted that library's contract
directly and no longer has the isolation described above.

---

## 4. Shared table models create a compatibility obligation

The orchestrator writes investigations that the worker later updates. Both use `platform_db`,
and the migration process imports its metadata. That is a shared schema contract across
deployables, even though each service's application remains behind ports.

In the worker repository, the distinction is visible in these imports:

```python
from platform_db import Investigation
from platform_db import InvestigationStatus as DatabaseStatus
from worker.domain.investigation import InvestigationState, InvestigationStatus
```

`Investigation` carries persistence mapping details. `InvestigationState` carries the state the
worker needs to reason about execution. The repository converts between them so application code
does not depend on an ORM session or a table model's loading behavior.

Now consider a proposed schema change, not an existing sample migration:

```text
old worker reads statuses: queued, processing, completed, failed
new writer starts persisting status: paused
old worker receives paused → its status conversion may fail
```

Adding a value to a shared model is not enough to make independently running old code understand
it. Rollout compatibility must account for the database schema, library versions, and readers and
writers already deployed. A coordinated change might deploy compatible readers before enabling
new writes; a column change might first add an optional field, then populate it, and only later
enforce stricter constraints after old consumers are gone.

The migration process owns schema changes; service startup should not silently mutate tables
because a library was imported. Keep schema compatibility checks and integration tests close to
that contract. In the sample, `platform_db/tests/contract/test_model_ddl.py` inspects generated
table definitions, while `platform_migrations/tests/integration/test_schema_parity.py` checks the
migrated schema against model metadata. Neither alone proves every mixed-version rollout safe.

⚠️ Sharing models prevents duplicated definitions but also couples releases through their data.
The first symptom may be an old worker rejecting a new enum value or requiring a column that has
not been migrated. Clean Python imports cannot prevent that failure.

Do not treat shared tables as a default for independently owned services that require separate
data evolution. A service API or versioned event contract can provide a narrower integration
boundary when that independence is the actual requirement.

---

## 5. The caller controls resource lifetime even when construction is shared

A library can know how to create a database engine without knowing how long a worker should live.
`ctc_database` explicitly leaves configuration and engine disposal to its consumers. Bootstrap
supplies settings, calls its factory, and registers cleanup.

For telemetry, the sample's ownership chain is:

```text
worker.config.Settings
  → worker.bootstrap.observability maps selected settings into TelemetryConfig
  → platform_observability configures providers and logging
  → worker bootstrap registers shutdown for the process lifecycle
```

The library accepts its own explicit configuration type instead of importing the worker's settings.
This lets the orchestrator use the same mechanics with a different service identity. Although the
library tracks process-wide provider state internally, the consumer chooses when initialization
and shutdown happen. The process-singleton SDK state is a narrow exception to the usual prohibition
on mutable library globals: configuration and shutdown must be idempotent and tests need a reset hook.

If provider setup succeeds but logging setup fails, the service's configuration adapter closes
the acquired providers before propagating the failure. That prevents partial initialization from
leaking resources. [Runtime composition](06_compose_the_runtime_at_the_edge.md#6-partial-startup-needs-cleanup-before-a-runtime-exists)
demonstrates the same cleanup principle with a runnable standard-library example.

**Success signal:** two services can supply different configuration values through the same
public library API, and setup-failure tests observe cleanup. If importing the library starts a
consumer loop or reads one deployable's settings, process ownership has leaked into reuse.

---

## 6. A neutral contract and a concrete client protect different boundaries

Suppose both services use `TicketCategory.BILLING`. If that enum lives in a dependency-light
`ticket_contracts` package, an action or domain decision can import it directly. Creating a second
identical enum in every port would add conversion without changing meaning. A **contract library**
contains stable values and wire contracts; it does not run I/O or import a database, SDK, or web
framework. Its allowed dependencies are the standard library and Pydantic.

Now put the enum inside a client module importing HTTP transport and provider models. Importing
that module from `domain/` would pull a concrete dependency inward even though the enum looks
pure. Split neutral vocabulary into a contract library when it is genuinely shared. The concrete
client remains outside the core; the service adapter translates its provider types and failures
into the conversation the action owns, as the CTC excerpt demonstrates.

The source edges in this explanatory excerpt make the distinction visible:

```python
# domain/classification.py: public pure vocabulary, no client transport import.
from ticket_contracts import TicketCategory

# adapters/documents.py: concrete client stays at the integration edge.
from document_client import DocumentClient, DocumentUnavailableError
from ticket_triage.ports.documents import DocumentSourceUnavailableError
```

This is a distinction of dependencies and meaning. A port can directly import a suitable neutral
contract type. A provider's `Document` may instead become a service-owned `SourceDocument` because
its fields, failure behavior, or meaning differ. Do not mirror neutral types solely for isolation.

Every admitted library has exactly one kind:

| Kind | Contents | Permitted service importers |
|---|---|---|
| Contract | Pure enums, values, validation, wire documents | Any layer; inner layers explicitly allow the external contract package |
| Client | One external system's typed async transport, models, auth, errors | `adapters/`, `genai/`, and construction in `bootstrap/` |
| Persistence | Shared SQLModel/SQLAlchemy metadata and column types | `db/` and migrations |
| Configuration | File discovery and source mechanics from explicit caller inputs | `config/` and `bootstrap/` |
| Observability | Provider lifecycle, propagation, processors, redaction | `observability/` and `bootstrap/` |
| GenAI | Shared model factories, middleware, provider construction | `genai/` |
| Testing | Test plugins and disposable infrastructure support | Tests, as a development dependency |

A persistence library does not contain queries, sessions, engines, or one service's migrations.
The declared database-runtime exception above permits only its named technical scope and imports
from `db/` or `bootstrap/`. A configuration library does not own a service's settings schema, final
settings instantiation, ambient environment/secrets lookup, or startup policy. Observability
libraries own mechanics, while services own their business span names and metrics. GenAI libraries
do not collect business prompts or task schemas. Mixing kinds forces pure consumers to inherit
concrete dependencies; split by kind rather than hiding the mixture behind an export.

### Follow the change in consumers before extracting

Two identical copies do not automatically require another package. Start by comparing semantics,
lifecycle, and dependencies, then apply the first matching condition:

| Current condition | Decision |
|---|---|
| Similar code has different meaning, lifecycle, or dependencies | Keep it local |
| An identical module exists in three or more deployables | Extraction is required |
| Two copies intended to stay identical have diverged | Extract, or document why their semantics differ in each copy |
| Two identical non-business helpers already have a suitable library depended on by both | Move the helper into that library |
| Two identical copies have no suitable library | May extract if both intend identical behavior and workspace admission passes |
| One independently valuable wire contract, schema, or client has a concrete compatibility/isolation need | May extract; state that reason in its README or module docstring |
| Only future consumers would justify the package | Keep it local |

For example, two services serialize the same versioned event. A contract library can own that
wire shape because changing only one copy would make their conversation diverge. If a third
deployable copies the identical module, extraction becomes required. If one service instead needs
a materially different event meaning, a flag for every difference would conceal two contracts;
keep that behavior local or name the distinct contract. Packaging does not authorize standardizing
business semantics during a structure-only migration.

### Public imports and enforcement make the boundary reviewable

An abbreviated current contract-library tree can remain flat:

```text
libs/ticket-contracts/
├── pyproject.toml
├── src/ticket_contracts/
│   ├── __init__.py       # Supported exports and __all__, no definitions
│   ├── py.typed         # Declares that consumers can use the shipped annotations
│   └── events.py        # Pure typed event values and validation
└── tests/               # Public behavior and wire compatibility
```

Consumers use names exported from the package root or a documented public subpackage, never
private modules or undocumented fields. Public signatures are fully annotated without `Any`;
the library runs strict type checks and declares every imported runtime dependency. Inside one
workspace, a breaking API change migrates all consumers in the same change. Truly non-atomic
consumer migration instead needs an additive API with a removal condition.

The import graph must enforce both directions of isolation:

```text
service domain/ports/application → neutral contract library only when admitted
service adapter → concrete client → external transport
library ──X──→ any deployable's private package, settings, tests, or bootstrap
```

Each library has an import-linter independence contract forbidding every service package and
`pydantic_settings` unless it is a configuration library. Each consumer has kind-specific importer
contracts enforcing the table above. Run them in pre-commit and the same CI hooks; a forbidden
client import into an action must fail there rather than await a careful reviewer. Library static
audit checks declarations and obvious violations; semantic review still checks meaning, admission,
borrowed resources, and the scope of a database-runtime exception. Behavioral tests separately
prove public behavior and translation. A client unit test uses transport stubs, while each service
fakes its port in action tests and proves library-to-port mapping in adapter tests.

### Construction does not silently transfer ownership

If bootstrap injects an HTTP client into a library client, it remains borrowed: the library must
not close it. Otherwise a library call could unexpectedly invalidate another adapter sharing that
client. Bootstrap's resource stack closes it once when its owned process scope ends. If a library
creates a resource itself, expose an async context-manager factory so acquisition and owned cleanup
form one visible scope; ownership transfer requires a distinct explicit API.

A client makes one attempt per call and reports retry information; the consuming boundary chooses
retry policy. Only protocol-required refresh or documented idempotent resume justifies an internal
retry, with explicit configured attempts and injectable clock/sleep, and the consumer must not
retry again around it. Libraries take explicit typed options rather than a service settings object,
do not read environment variables or start work at import, and translate transport failures into
their own error vocabulary before the service adapter maps those errors once into its port errors.

### Predict the boundary when another consumer appears

A third service copies a document client identically. Its domain also imports a document-status
enum from that client's module, which imports HTTP transport. Should you extract everything into
one library and recreate `ports/` and `adapters/` inside it? Who closes its injected HTTP client?

**Worked reasoning:** three identical deployable copies require extraction, but the import needs
reveal two responsibilities. Share the concrete client as a client kind and move genuinely neutral
status vocabulary to a contract kind. Domain can import the admitted pure contract directly;
service adapters/bootstrap are the permitted client importers and retain meaningful result/error
translation. Cohesive modules are enough; service-shaped folders would not repair the mixed
dependency graph. The injected HTTP client stays borrowed and bootstrap closes it. If the third
service's intended behavior actually differs, that behavior stays local rather than being forced
into options just to make the copies look identical. Independence/importer contracts verify the
source edges; tests verify the meanings and cleanup that an import graph cannot establish.

> **Key insight**: share one admitted capability, keep each caller's decisions local, and judge
> library boundaries by their dependencies, public meaning, and explicit resource owner.

---

**Next**: return to the [service-code reading path](README.md#read-the-service-and-library-samples),
or use [the migration review](11_migrate_and_review_an_existing_service.md) to assess one proposed extraction.
