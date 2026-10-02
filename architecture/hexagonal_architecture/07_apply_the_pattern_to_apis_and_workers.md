# Apply One Application Core to APIs and Workers

> **Who this is for**: Engineers building FastAPI routes, scheduled jobs, queue consumers, or a process that combines them.

The baseline's HTTP-shaped and worker-shaped handlers both call `classify_ticket` with explicit
collaborators. A real HTTP framework and broker add translation and lifecycle concerns; they do
not change where classification policy belongs. This chapter develops that separation through
explanatory excerpts, not a runnable FastAPI or SQS deployment.

## 1. A route reads one typed runtime view and calls one action

`api/dependencies.py` describes what routes read. Its Protocol does not import the bootstrap class;
bootstrap's frozen `Runtime` satisfies the view by providing the required fields.

```python
# api/dependencies.py — excerpt
class ApiRuntime(Protocol):
    @property
    def tickets(self) -> TicketRepository: ...

    @property
    def classifier(self) -> TicketClassifier: ...


def get_runtime(request: Request) -> ApiRuntime:
    runtime: ApiRuntime = request.app.state.runtime
    return runtime


RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]
```

The route uses this one dependency and passes the collaborators visibly:

```python
# api/routes.py — excerpt; imported action has a different name from the handler
@router.post("/tickets/{ticket_id}/classification", response_model=ClassificationResponse)
async def classify_ticket_route(ticket_id: str, runtime: RuntimeDep) -> ClassificationResponse:
    result = await classify_ticket(
        ticket_id=ticket_id, tickets=runtime.tickets, classifier=runtime.classifier
    )
    return ClassificationResponse(ticket_id=result.ticket_id, category=result.category)
```

The route owns HTTP fields and response shape. A stable not-found failure maps to `404` in the API's
exception-to-public-error table; provider failures map there too when they escape the action. The
mapper uses an allowlisted public message, not exception text that might expose prompts or credentials.
The route does not execute SQL, invoke a model SDK, or decide eligibility.

There is no provider per capability such as `get_classifier()` that only returns a runtime field.
Adding a required action collaborator changes the runtime view and every action call. Tests override
`get_runtime` with a view backed by fakes; routes never reach into app state themselves.

A separate `api/schemas.py` exists when HTTP shape differs from the deliberate public business
contract. Request bodies reject unexpected fields; response models describe what callers receive.
A business read such as `get_ticket` is still one public action, even if it calls one port method.
Health, readiness, metrics, and version endpoints are technical and call no business action.

## 2. A queue consumer has two owners

Suppose SQS supplies `{"ticket_id": "T-100"}` with a receipt handle. There are two translations:

```text
adapters/sqs_inbox.py: SQS body → validated ClassificationMessage + opaque delivery token
workers/classify_tickets.py: message.ticket_id → classify_ticket(...explicit collaborators...)
workers/classify_tickets.py: typed business result → Ack or Retry(delay)
adapters/sqs_inbox.py: settlement → delete or adjust visibility using the receipt handle
```

The **inbox adapter** owns polling, wire validation, trace-context extraction, visibility heartbeat,
receipt handles, acknowledgement, and dead-letter mechanics. It does not import an application action.
The **consumer worker** in `workers/` chooses the action and maps its result into settlement. It
receives a technology-neutral inbox; it neither imports boto3 nor constructs clients.

This inbound contract belongs to `workers/inbox.py`, because the worker is its caller:

```python
# workers/inbox.py — excerpt; Python 3.11-compatible generic form
T = TypeVar("T")


@dataclass(frozen=True)
class Delivery(Generic[T]):
    message: T
    message_id: str
    token: str  # opaque: only the inbox interprets it


@dataclass(frozen=True)
class Ack:
    pass


@dataclass(frozen=True)
class Retry:
    delay: timedelta


class Inbox(Protocol[T]):
    async def receive(self) -> Sequence[Delivery[T]]: ...
    async def settle(self, delivery: Delivery[T], settlement: Ack | Retry) -> None: ...
```

The worker's read-only runtime view names its inbox and the same two action collaborators:

```python
# workers/runtime.py — excerpt
class WorkerRuntime(Protocol):
    @property
    def classification_inbox(self) -> Inbox[ClassificationMessage]: ...

    @property
    def tickets(self) -> TicketRepository: ...

    @property
    def classifier(self) -> TicketClassifier: ...
```

A frozen bootstrap Runtime supplies those fields. This baseline iteration acknowledges a completed
classification:

```python
# workers/classify_tickets.py — excerpt
async def consume_classifications(runtime: WorkerRuntime) -> Iteration:
    deliveries = await runtime.classification_inbox.receive()
    for delivery in deliveries:
        result = await classify_ticket(
            ticket_id=delivery.message.ticket_id,
            tickets=runtime.tickets,
            classifier=runtime.classifier,
        )
        log.info("ticket_classified", ticket_id=result.ticket_id, category=result.category)
        await runtime.classification_inbox.settle(delivery, Ack())
    return Iteration.MORE_DUE if deliveries else Iteration.IDLE
```

`Iteration` is a worker-owned enum: `MORE_DUE` means another iteration may run immediately; `IDLE`
allows the supervisor's configured pause. The supervisor owns cadence, task creation, stop events,
and failure policy. For batched business work, the action decides whether more work is due and
returns that fact; the worker only translates it. A broker receive batch has no business policy of
its own, so the excerpt uses whether deliveries were received.

Malformed wire input is rejected and dead-lettered by the inbox before it becomes a typed delivery.
Inbound events tolerate unrelated fields added by a producer (`extra="ignore"`); missing or invalid
required fields still fail validation. A database or queue outage without a declared business outcome
escapes to the supervisor's unavailable-error boundary: it logs once and backs off. The delivery
stays unsettled and becomes visible again. An unknown exception is a defect, not a made-up outage;
it fails the process. Broker redrive limits prevent one poison message from crash-looping forever.

## 3. Typed outcomes make retry ownership visible

Now change a real requirement: classification unavailability should become a deliberate later
attempt. This evolves the baseline action's simple `Classification` result into a closed outcome
union; it is not a hidden change in queue code. For example, `Classified` carries the accepted result
and `RetryScheduled` carries a domain-selected delay. The action catches its classifier's unavailable
error only because this operation declares what that failure means.

```python
# workers/classify_tickets.py — excerpt for the evolved outcome contract

def settlement_for(outcome: ClassificationOutcome) -> Ack | Retry:
    match outcome:
        case Classified() | AlreadyClassified() | ClassificationRejected():
            return Ack()
        case RetryScheduled(delay=delay):
            return Retry(delay=delay)
        case _:
            assert_never(outcome)
```

A recorded rejection is complete business work, so ACK does not mean the classifier accepted the
input. `RetryScheduled` in this variant delegates the next delivery to the broker; the inbox applies
the delay. If the action instead commits a durable `DEFERRED` state and a scheduler owns the next
attempt, the current delivery is ACKed. Applying both strategies schedules two attempts:

```text
classifier unavailable → action persists DEFERRED → worker ACK → scheduler sends next attempt
classifier unavailable → action returns RetryScheduled → worker Retry → broker redelivers
```

Choose one owner for that retry. Provider-call retries inside GenAI are another bounded mechanism;
account for their attempts when sizing visibility and shutdown deadlines. A receipt handle never
reaches `application/`, `domain/`, or `ports/`; a delivery attempt count may cross as a plain business
retry-policy input when the action needs it. The [reliability notes](../../background_work/reliability/04_retries_timeouts_and_cancellation.md)
cover durable redelivery, idempotency, and cancellation guarantees. Hexagonal boundaries expose
these decisions; a port alone cannot prevent duplicate effects.

## 4. Scheduled and hybrid processes share construction

A scheduled one-shot business job enters `build_runtime()`, calls one function action or worker function,
maps the outcome to an exit code, and exits. It has no repeated intake to supervise. A long-running
worker adds the supervisor described in [Runtime Composition](06_compose_the_runtime_at_the_edge.md).

A technical retention purge, orphan cleanup or expired-lease sweep stays in the integration that
owns its data, for example `db/retention.py`. Bootstrap builds it once; its `run_once()` performs
one pass and returns whether more work is due. A generic worker iteration maps that signal while
the supervisor owns cadence and shutdown. It needs no action, application port or domain module
until another entry point uses it, it chooses business outcomes, or its rule needs a database-free
test. This exception keeps technical maintenance out of the business action catalog.

```text
main.py
bootstrap/       runtime.py, supervisor.py; app.py for HTTP
api/             typed dependency and routes
workers/         typed runtime view, inbox contract, consumer iterations
application/     public async business actions
domain/          pure decisions
ports/           action-facing I/O capabilities
adapters/        concrete broker inbox and other external integrations
db/              concrete persistence
genai/           classifier implementation when AI is used
```

The tree is a placement map: create only owners that exist. In a hybrid process, FastAPI lifespan
may own startup and shutdown of both API and supervisor. `main.py` and lifespan must not each
construct the same resources. API and worker share implementations and policies, not bound action
objects or transport wrappers. Split deployables when scaling, release, security, or failure isolation
needs differ; extract stable shared contracts rather than importing another deployable's private code.

## 5. Authorization and progress belong to explicit owners

Authentication extraction is transport work. Authorization based on ticket ownership or tenant
policy is a business precondition. Pass trusted immutable actor/tenant values into the action; the
action or its pure domain decision checks access before calling the relevant port. An HTTP dependency
may reject earlier, but it cannot be the only guard: a worker or AI tool would otherwise skip it.
Never turn a queue payload's or prompt's claimed tenant identity into trusted context.

Liveness reports process health. Readiness needs initialized dependencies, compatible schema, and
recent useful worker progress; an idle queue differs from a failed loop. Probes call a port method
when required and never execute business actions. A healthy API alone cannot establish consumer progress.

**Changed-condition check:** the route currently denies closed tickets but a queue message succeeds.
Adding another queue check duplicates the policy again. Move eligibility into the shared pure domain
decision called by `classify_ticket`; both entry points now see the same result, and one action test
proves the rule. If the API accepts durable investigation work and the worker later performs it,
those are two distinct actions connected by persisted state and an event, as in the
[investigation case study](12_trace_an_investigation_across_services.md).

**Success signal:** one deterministic action test covers shared policy; API tests prove HTTP mapping;
worker tests prove outcome-to-settlement mapping; inbox tests prove wire parsing and broker mechanics.
No one test is evidence for all four owners.

**Next**: [Part 8 — Treat GenAI as an External Capability](08_treat_genai_as_an_external_capability.md)
