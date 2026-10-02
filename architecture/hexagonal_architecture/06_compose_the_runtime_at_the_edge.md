# Compose the Runtime at the Process Edge

> **Who this is for**: Engineers wiring settings, database engines, clients, model handles, capability implementations, and deterministic shutdown.

Moving constructors out of an action is incomplete if concrete dependencies become module globals
spread across routes and workers. A **composition root** is the one ordinary runtime location that
knows which implementations satisfy which application needs.

---

## 1. Import-time construction hides failure and disposal

This module opens a client as a side effect of import:

```python
# Wrong owner: importing the module starts runtime construction.
settings = Settings()
http_client = httpx.AsyncClient(timeout=settings.timeout)
model = build_model(settings=settings.ticket_classification)
classifier = LLMTicketClassifier(model=model)
```

Tests importing one symbol now require configuration. Reload behavior can duplicate handles.
Shutdown ownership is unclear, and startup failures happen before the process can report readiness
cleanly.

Construct resources explicitly inside `bootstrap/runtime.py`, after configuration is validated and
before the process accepts work.

> **Core:** configuration describes policy, factories construct technology-specific objects, and
> bootstrap decides when construction and disposal occur.

---

## 2. A typed runtime exposes implementations and policies

The baseline's `Runtime` contains `tickets` and `classifier`, not a constructed action. Keep that
shape when memory becomes a database and keyword matching becomes a model. This is an explanatory
excerpt: imports, validated settings, and the concrete implementations belong to the packaged service.

```python
# bootstrap/runtime.py — excerpt
@dataclass(frozen=True, slots=True, kw_only=True)
class Runtime:
    tickets: TicketRepository
    classifier: TicketClassifier


@asynccontextmanager
async def build_runtime(settings: Settings) -> AsyncIterator[Runtime]:
    async with AsyncExitStack() as stack:
        engine = create_async_engine(settings.database_url)
        stack.push_async_callback(engine.dispose)
        model = build_model(settings=settings.ticket_classification)
        yield Runtime(
            tickets=SqlAlchemyTicketRepository(sessions=async_sessionmaker(engine)),
            classifier=LLMTicketClassifier(model=model),
        )
```

The database engine has a cleanup owner immediately after acquisition. If model construction
fails, the stack disposes the engine; the same cleanup runs after a successful runtime exits.
The model integration builds its own SDK clients from the settings passed to its factory. Do not
create a separate HTTP or boto3 client for the model when its integration accepts the required
settings. A custom client is an exception only when a required option cannot be expressed through
the integration; document that option and register the custom client's cleanup immediately.
Other adapters may still borrow bootstrap-owned clients; borrowing does not transfer disposal.

`Runtime` exposes port-shaped implementations, not raw sessions, clients, the entire settings object,
or prebound actions. A route calls `classify_ticket(ticket_id=id, tickets=runtime.tickets,
classifier=runtime.classifier)`. A worker makes the same explicit call. Adding a collaborator requires
updating each call site, so no entry point can silently skip the dependency. Bootstrap constructs
technology; it neither wraps actions in handler classes nor binds them with `partial`.

Domain policy values can join these fields when the action actually requires them. Request-specific
transactions stay inside the persistence implementation or a fresh Unit of Work; one shared runtime
does not mean one mutable session shared by concurrent requests.

---

## 3. Factories retain technology-specific construction knowledge

Bootstrap coordinates factories; it should not absorb their internals:

```python
# genai/ticket_classification/llms.py — provider factory excerpt
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel


def build_model(*, settings: TicketClassificationSettings) -> BaseChatModel:
    return init_chat_model(
        settings.model_name,
        model_provider="openai",
        timeout=settings.timeout_seconds,
        max_retries=0,
        temperature=settings.temperature,
        max_tokens=settings.max_output_tokens,
    )
```

The task settings slice owns defaults for timeout and tuning; the factory owns provider policy,
including disabled SDK retries. Bootstrap passes that slice without constructing SDK clients.
The [LangChain model guide](https://docs.langchain.com/oss/python/langchain/models) describes
`init_chat_model`; the [OpenAI integration](https://docs.langchain.com/oss/python/integrations/chat/openai)
defines this provider's timeout and retry options. Another provider must verify its own options.
Move identical reused construction policy to `genai/shared/llms.py` when a second task needs it.
One-line structured binding stays in the runner constructor, as shown in
[GenAI](08_treat_genai_as_an_external_capability.md). Neither application code nor a module import
chooses the provider.

---

## 4. FastAPI lifespan enters the same runtime

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with build_runtime(load_settings()) as runtime:
        app.state.runtime = runtime
        yield


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.include_router(ticket_router)
    return app
```

`bootstrap/app.py` owns the FastAPI instance, lifespan, router registration, and framework
instrumentation. `api/dependencies.py` exposes one typed runtime dependency; routes pass its fields to function actions.

A worker process can enter the same `build_runtime()` context without importing FastAPI. That is
why runtime composition belongs above process adapters rather than inside a route.

---

## 5. Supervisors own loops; actions own work

A long-running worker needs task creation, stop events, health, and graceful shutdown. Put those
mechanics in `bootstrap/supervisor.py`:

A `TaskGroup` supplies **fail-together** concurrency: when one child fails, its siblings are
cancelled immediately. That is useful for one operation whose parallel parts cannot succeed alone.
A process supervisor that promises graceful shutdown needs a different sequence:

```text
external stop signal → set shared stop event → loops stop accepting new work
                     → wait up to grace deadline for in-flight actions
                     → cancel and await any remaining tasks
                     → leave build_runtime() → close clients and engine
```

If a classifier is halfway through a call, closing HTTP first causes a use-after-close. Waiting
forever avoids that error but prevents deployment shutdown. The grace deadline bounds the trade-off;
unfinished durable deliveries remain unsettled so the broker can redeliver them.

This shutdown excerpt assumes `tasks` contains every loop task started by the supervisor:

```python
async def drain(tasks: list[asyncio.Task[None]], stop: asyncio.Event, grace: float) -> None:
    stop.set()
    try:
        async with asyncio.timeout(grace):
            await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                log.warning("worker_shutdown_failure", error_type=type(result).__name__)
```

The process owner catches the timeout to record unfinished work; it propagates external cancellation
and unexpected loop defects. The supervisor contains declared dependency outages with stop-aware
backoff, and fails fast on defects. It must track and await every task; a detached `create_task()`
can keep using resources after their owner exits. Production cleanup that can hang needs its own
bounded, cancellation-aware treatment, beyond this sequencing excerpt.

The supervisor controls process lifetime. An inbox translates deliveries, a worker invokes the
function action, and `classify_ticket` owns business execution. Business stage order does not belong
in the supervisor merely because the supervisor starts several loops.

> **Key insight**: bootstrap may know every concrete object while knowing no business decision; its
> job is to create, connect, start, and dispose the graph.

---

## 6. Partial startup needs cleanup before a runtime exists

Suppose the worker creates database engines and an HTTP client, then fails to connect to the
broker. There is no completed runtime for the caller to close. Each successfully acquired resource
must already have a cleanup owner before the next acquisition can fail.

`AsyncExitStack` is a standard-library cleanup registry: callbacks run in reverse registration
order when the stack closes. The sample worker registers cleanup during `_build_resources()`,
then uses `pop_all()` to transfer those callbacks to the runtime without executing them. If
`_compose_runtime()` fails afterward, `build_runtime()` closes the resource bundle instead.

This standalone Python example demonstrates that ownership transfer using recorded events instead
of live clients. Run the whole block as a script; it needs only the standard library:

```python
import asyncio
from contextlib import AsyncExitStack


async def build(events: list[str], *, fail: bool) -> AsyncExitStack:
    async def close(name: str) -> None:
        events.append(f"close {name}")

    async with AsyncExitStack() as pending:
        for name in ("database", "http"):
            events.append(f"open {name}")
            pending.push_async_callback(close, name)
        if fail:
            raise RuntimeError("broker unavailable")
        return pending.pop_all()


async def main() -> None:
    failed: list[str] = []
    try:
        await build(failed, fail=True)
    except RuntimeError:
        pass
    assert failed == ["open database", "open http", "close http", "close database"]

    succeeded: list[str] = []
    runtime_cleanup = await build(succeeded, fail=False)
    assert succeeded == ["open database", "open http"]
    await runtime_cleanup.aclose()
    assert succeeded == failed
    print("startup failure and runtime shutdown both clean up in reverse order")


asyncio.run(main())
```

The printed line is the success signal. The first assertion detects leaked partial startup;
the second detects premature cleanup caused by returning clients without transferring ownership.
This verifies the lifecycle mechanism, not connectivity or graceful worker draining.

Returning a resource bundle makes ownership explicit; it does not make concurrent work stop.
The supervisor must first stop intake and resolve or cancel in-flight tasks within the shutdown
budget, then close the stack. Cancellation and provider-specific close operations still need
bounded handling; see [signals and shutdown](../../fundamentals/core_concepts/signals.md).

### Several supervisors can share resources without owning business stages

The following is a source-tour comparison of the supplied investigation worker, not the current
service scaffold. Under the current standard, business admission and batch decisions belong in
actions or pure domain policy; the generic supervisor owns cadence, stop, health, and drain.
In the investigation worker, `AdmissionSupervisor` controls how much work enters, `AimdSupervisor`
adjusts the concurrency target, and `ReconcilerSupervisor` runs periodic checks. **AIMD**, additive
increase and multiplicative decrease, means raising capacity gradually during stable operation
and cutting it proportionally under pressure. Its pure decisions live in `domain/admission.py`;
the supervisor supplies observations and timing.

```text
current target 4; stable window; chosen increase 1 → target 5
current target 4; pressure window; decrease factor 0.5 → target 2
```

These are illustrative policy inputs, not the sample's configured defaults. Changing the target
controls future admission; it does not undo work already running. The investigation's analysis,
write-back, and checkpoint order remains in `application/investigate_exception.py`.

⚠️ A supervisor can be alive while repeatedly failing its useful work. Readiness needs progress
evidence, and shutdown needs tests for a stalled action, not just a successful cleanup callback.
The sample's `tests/unit/bootstrap/test_runtime.py` exercises composition failure; its
`test_supervisor.py` exercises drain timeout and interruption handling. Those are different claims.

---

## 7. Readiness and shutdown prove lifecycle ownership

**Success signal:** startup builds one shared graph, readiness becomes true only after required
dependencies initialize, and shutdown stops intake before closing those dependencies. Tests can
replace constructors and assert creation/disposal without executing business behavior.

⚠️ The first failure is a use-after-close during shutdown: the database engine or HTTP client closes
while a consumer task is still processing. The symptom is a burst of connection or cancellation
errors exactly when the deployment terminates.

Do not centralize short-lived request transactions in the process runtime. Bootstrap owns the
session factory or engine lifetime; the persistence implementation or a fresh Unit of Work owns each transaction's
narrower lifetime. API dependencies expose a runtime view, never raw sessions.

> **Production:** give graceful shutdown a bounded deadline. Once it expires, record unfinished work
> and rely on durable redelivery or reconciliation instead of waiting forever.

---

**Next**: [Part 7 — Apply the Pattern to APIs and Workers](07_apply_the_pattern_to_apis_and_workers.md)
