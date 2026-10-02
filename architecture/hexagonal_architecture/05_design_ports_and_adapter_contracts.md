# Design Ports Around Caller Needs and Failure Decisions

> **Who this is for**: Engineers deciding whether an external dependency deserves a port and what that contract should contain.

A port has a cost: another name, type, implementation, and test seam. In this repository every
application I/O capability pays that cost so the action can describe execution without importing
technology. The decisions are how narrowly to shape that contract, which failures it exposes, and
who must own an atomic change. Pure decisions and optional outer-component interfaces follow
different rules.

---

## 1. Application I/O ports and optional collaborator Protocols answer different questions

A classifier can be remote, nondeterministic, costly, and capable of transient or invalid-output
failures. The application needs a capability contract describing the answer and failures it can
handle. A stable internal HTTP service with only one implementation needs the same boundary:
"unlikely to change" does not make HTTP responses or network failures domain values.

**Every I/O capability an action uses is a port**, one per capability rather than per table, SDK
client, or private helper. Persistence, object storage, remote classification, and publication have
technology owners outside the application. The action imports their caller-shaped contracts from
`ports/`; the concrete implementation lives in `db/`, `adapters/`, or `genai/`.

A capability covers one aggregate or lifecycle, not everything a main action happens to touch.
Split unrelated method groups rather than growing a service-wide store; roughly twelve methods
or four hundred lines are review signals, not automatic limits. Shared table handles belong in
`db/tables.py`; a store does not reach into a sibling store's private helpers. These rules apply
to action dependencies. Agent-only internals and integration-owned technical maintenance can
remain direct code, as explained in the GenAI and API/worker chapters.

Other collaborators require different treatment:

| Collaborator | Shape | Why |
|---|---|---|
| Action's external ticket reader or classifier | Mandatory application port | Keep database/SDK types and failures outside execution |
| Pure normalization or eligibility decision | Direct domain function | No external effect to isolate; test the calculation with values |
| Current time, new ID, random draw | Passed value or typed callable | Make nondeterminism explicit without inventing a clock interface |
| API or worker runtime view | Protocol beside its consuming entry point | The entry point may not import the concrete bootstrap runtime |
| Interface between two outer components | Optional Protocol with a current trigger | Isolate an actual substitution or forbidden dependency |

For an optional non-application Protocol, one current trigger is enough: a test must substitute a
collaborator it cannot call, a second implementation exists, a behavior-owning decorator wraps it,
or the consuming package may not import the implementation. A hypothetical future provider switch
alone is insufficient. Keep that Protocol beside its outer consumer, rather than in root `ports/`.
The application-port rule is unconditional; it is not an admission test requiring two traits.

For example, a pure expiry decision receives `now: datetime`. Its action may accept
`clock: Callable[[], datetime] = utc_now`, where `utc_now` is the named real-clock function defined
once in `core/clock.py`. The action calls `clock()` and passes the returned value to the decision.
Do not call `datetime.now()` inside the domain function or disguise it behind a `Clock` port. A
`Callable` names the effect without requiring a hierarchy for one function.

The public async action signature is the inbound application contract. HTTP, worker, or tool
adapters invoke it directly; they do not need another Protocol around that action. The contracts
in `ports/` here are outbound capabilities implemented by driven adapters.

> **Core:** separate mandatory application I/O contracts, direct pure logic, injected
> nondeterminism, and optional interfaces between outer collaborators before deciding abstractions.

---

## 2. Name the capability without assuming its implementation

`ClassificationModel` assumes a model. `OpenAIClient` assumes a provider.
`TicketClassifier` states what the caller needs:

```python
@dataclass(frozen=True)
class ClassificationCandidate:
    category: str
    confidence: float


class TicketClassifier(Protocol):
    async def classify(self, body: str) -> ClassificationCandidate: ...
```

An LLM, rules engine, hybrid classifier, or remote API can implement this conversation. Avoid raw
`dict[str, Any]`, unvalidated JSON, SDK messages, and provider response objects when a stable typed
shape exists.

Keep the input narrow as well. Passing the entire FastAPI request or settings object makes the port
depend on the current edge instead of the caller's actual data need.

---

## 3. The port owns stable success and failure contracts

If application code catches an SDK exception, the provider already owns part of the use case.
Define failures in the port according to decisions the caller can make:

```python
# ports/ticket_classifier.py — bases belong to ports/errors.py.
from ticket_triage.ports.errors import DependencyRejectedError, DependencyUnavailableError


class ClassificationUnavailable(DependencyUnavailableError):
    """The capability is unavailable; the same request may succeed later."""


class InvalidClassification(DependencyRejectedError):
    """The provider answered, but no trusted candidate can be produced."""
```

The unavailable base declares `error_code` and optional `retry_after`; the rejected base declares
`error_code`. Each port owns its concrete errors. A family base is useful only if a caller actually
catches the whole family, not as another mandatory inheritance layer.

The concrete adapter translates a known timeout and rejects an invalid candidate. This excerpt
assumes the provider-facing schema has already checked field types:

```python
from math import isfinite


async def classify(self, body: str) -> ClassificationCandidate:
    try:
        output = await self._model.ainvoke(self._prompt(body))
    except ProviderTimeout as exc:
        raise ClassificationUnavailable(error_code="classifier_timeout") from exc

    if not isfinite(output.confidence) or not 0.0 <= output.confidence <= 1.0:
        raise InvalidClassification(error_code="invalid_confidence")

    return ClassificationCandidate(
        category=output.category,
        confidence=output.confidence,
    )
```

Only the owned known timeout is relabelled unavailable. An unrelated `AttributeError` or another
unknown programming failure propagates; pretending it is an outage would trigger the wrong retry
or fallback. Finiteness matters because NaN does not behave like a normal number in comparisons;
it must not reach a trusted confidence contract merely because two range comparisons are false.

The port's error message contains no prompt, token, API key, or raw provider body. Exception chaining
preserves diagnostics without making the inner layer import the provider type.

---

## 4. Give the caller only distinctions it can act on

An exhaustive copy of provider errors is not a stable application contract. Suppose the action has
three meaningful outcomes:

| Port result | Application decision |
|-------------|----------------------|
| Candidate with adequate confidence | Accept and persist |
| `ClassificationUnavailable` | Defer according to action policy |
| `InvalidClassification` | Route to human review |

If rate limits and provider timeouts produce the same action decision, they may share one stable
failure even though the adapter records different telemetry. Keep request refusal and invalid output distinct from availability; for GenAI the three
provider-failure classes retain distinct concrete errors even if a particular action chooses the
same fallback. [The GenAI chapter](08_treat_genai_as_an_external_capability.md) develops invocation
and request-refusal classification.

When the failure changes a business status or human-review reason, the action converts the port
error into a domain value, then calls a pure decision. This excerpt is a branch inside the action,
not a standalone runnable program:

```python
try:
    candidate = await classifier.classify(ticket.body)
except ClassificationUnavailable:
    decision = decide_classification_failure(
        failure=ClassificationFailure.UNAVAILABLE, policy=policy
    )
except InvalidClassification:
    decision = decide_classification_failure(
        failure=ClassificationFailure.INVALID_OUTPUT, policy=policy
    )
else:
    decision = decide_classification(candidate=candidate, policy=policy)
```

`ClassificationFailure` and the decision functions live in `domain/`. They see values such as
UNAVAILABLE, never SDK or port exception classes. The action owns failure translation into those
inputs; the pure decision chooses the resulting status and reason. An action that has no declared
business fallback lets the owned port error reach the API or worker handling boundary instead.

Conversely, do not return `None` for every failure. It erases whether the ticket was absent, the
classifier was unavailable, or output was rejected.

> **Key insight**: a port is complete only when its success types and failure types let the caller
> make every required decision without importing implementation details.

---

## 5. A persistence port owns an atomic business capability

A repository returning domain types shields its caller from database rows, but importing the
SQLAlchemy implementation into `application/` still creates an outward source dependency. Even an
annotation creates that edge. Declare the application-facing persistence contract in `ports/` and
inject its implementation explicitly at the entry point's action call. A concrete class satisfies
Python's `Protocol` structurally; inheritance is unnecessary.

### Prefer one atomic operation when one store can complete the transition

Suppose a reviewer approves ticket T-100 only while it is awaiting review. Two requests can observe
that same pending state. Splitting `get()` and `save()` into separate transactions lets both decide
from an old observation; moving the calls into folders does not remove the race.

The preferred port method promises a complete transition. This explanatory excerpt shows its
application-facing shape and owner; observation mapping, SQL imports, and driver error translation
are omitted:

```python
# ports/ticket_store.py
class TicketStore(Protocol):
    async def approve(self, *, ticket_id: str, actor: Actor) -> ApprovalResult: ...


# application/approve_ticket.py
async def approve_ticket(
    *, ticket_id: str, actor: Actor, tickets: TicketStore
) -> ApprovalResult:
    return await tickets.approve(ticket_id=ticket_id, actor=actor)


# db/tickets.py — method of SqlTicketStore
async def approve(self, *, ticket_id: str, actor: Actor) -> ApprovalResult:
    async with transaction(self._sessions, errors=_ERRORS) as session:
        row = await session.scalar(
            select(TicketRow).where(TicketRow.id == ticket_id).with_for_update()
        )
        if row is None:
            raise TicketNotFound(ticket_id)
        decision = decide_approval(observed=to_observation(row), actor=actor)
        row.status = decision.status
        row.approved_by = decision.approved_by
        return ApprovalResult(ticket_id=ticket_id, status=decision.status)
```

`decide_approval` is a pure function imported from `domain/`. It chooses the permitted status and
approver from business values, including the actor's authority. The store holds the row lock from
read through commit and applies the returned decision; it does not invent a status or choose an
approval policy. The transaction context commits on successful exit before the method returns and
rolls back on an exception. Its implementation also owns driver-to-port error translation.

Trace the race: request A locks T-100 in PENDING_REVIEW and commits APPROVED. Request B waits for
the lock, then observes APPROVED rather than A's old state. The domain rule now returns or raises
the explicitly defined already-approved outcome. A real database test must confirm that contract;
a dictionary fake cannot prove locking. Concurrent creation is a different case: there is no
existing row to lock, so enforce a unique key and map a duplicate to its named replay/conflict result.

The one-call `approve_ticket` action is intentional. It remains the public catalog operation for
HTTP and worker callers. Do not add a coordinator that opens a transaction and merely calls a
same-named implementation method; the port implementation already owns the behavior.

A conditional write is an alternative concurrency contract: include `expected_version` and update
only `WHERE version = expected_version`. No matching row means a named stale-version outcome, not
success. An application `get()` followed by `save()` without a lock or version condition silently
loses that protection. A Unit of Work alone does not fix the problem; it too needs locks, guarded
writes, or explicitly chosen isolation.

### Choose the owner from what execution must interleave

| Actual operation | Transaction owner | Action body |
|---|---|---|
| One cohesive read/decide/write, including its outbox row | One port method | One call; store locks, calls pure decision, writes, commits |
| Action must interleave distinct writes with its own domain decisions | UoW port entered by the action | Observe, decide, apply, continue, explicitly commit |
| Remote read or model answer, then one database write | Short database operation after the read | Call external capability first; write once; no intermediate state required |
| Database update plus external write | No transaction spans both | Commit durable intent/outbox, then deliver and recover |

For the model-read case, do not hold a row lock while waiting on the model. Read the input, obtain
its candidate, then let the store validate the current revision and apply the domain decision in
one short transaction. If another request changed the ticket meanwhile, return a named conflict;
never persist a candidate against an unrelated new body. A model lookup that changes nothing
outside the service does not require a durable PENDING state merely because it is slow.

For a genuinely interleaved example, admitting a batch may require the action to observe available
capacity, decide and apply the first reservation, then use the transaction's updated capacity to
decide whether the next item is admitted or deferred. Pure `decide_admission` selects each outcome;
the UoW supplies observations and writes in one locked transaction. If this whole batch is instead
one cohesive store capability, prefer `store.admit_batch(...)`. Choose UoW because the application
needs to own the intermediate sequence, not because several tables happen to change.

```python
# Excerpt: typed AdmissionWork operations share one fresh transaction.
async def admit_batch(
    *, items: tuple[AdmissionRequest, ...], policy: AdmissionPolicy,
    work_factory: Callable[[], AdmissionWork]
) -> tuple[AdmissionResult, ...]:
    results: list[AdmissionResult] = []
    async with work_factory() as work:
        for item in items:
            observed = await work.observe_for_update(item=item)
            decision = decide_admission(observed=observed, item=item, policy=policy)
            await work.apply(decision=decision)
            if decision.event is not None:
                await work.append_outbox(event=decision.event)
            results.append(decision.result)
        await work.commit()
    return tuple(results)
```

The `observe_for_update` contract includes the shared capacity row, not only the item row, so
competing batches cannot both consume the same capacity. `apply()` makes this transaction's prior
reservation visible to its next observation; leaving the context without commit rolls everything
back. No remote call occurs while those locks are held. Production code must define lock order and
duplicate-request behavior and test them against the production database engine.

**Changed condition:** approval now also inserts an outbox event whenever it succeeds. Does this
force an action-level UoW? **Worked reasoning:** no. The store already owns one complete atomic
transition; the domain decision can return the event, and the store writes it in the same
transaction before commit. Several tables do not imply several transaction owners. A broker send
inside that transaction would be a different operation: the broker cannot roll back with the row,
so delivery follows the durable outbox commit instead.

---

## 6. A Unit of Work makes several repositories one transaction

**Historical case-study shape:** the supplied investigation snapshot uses class-based actions and
repository-exposing Unit of Work objects. The trace below explains that existing code; it is not the
current function-based scaffold taught above. The same transaction reasoning applies when a current
action receives a `work_factory` explicitly.

Accepting an investigation can require a request row, an investigation row, a link between them,
and a pending event. If each repository commits independently, a failure writing the event can
leave an accepted investigation that nobody will execute.

A **Unit of Work** is the application's contract for a group of persistence operations that commit
or roll back together. In the supplied orchestrator, `InvestigationUnitOfWork` exposes `requests`,
`investigations`, `outbox`, async context-manager methods, and `commit()`. The **outbox** is a table
of events owed to the broker, written in the same transaction as the business state.

Trace a new investigation with illustrative IDs:

```text
one Unit of Work / one database session
  requests.add(...)                         → request R-1
  investigations.insert_or_attach(...)     → investigation I-1, created=True
  outbox.add_investigation_requested(...)  → pending event E-1
  requests.attach_investigation(...)       → R-1 linked to I-1 at position 0
  commit()                                 → all four writes become durable together
```

This existing action coordinates the operations that form one business transaction. For a new
feature, first ask whether one cohesive store method can own the complete transition; table count
alone does not justify exposing repositories through a UoW. In this historical form, the concrete Unit of Work
supplies the session and implements commit, rollback, cleanup, and database-error translation.
Its repositories issue queries through that same session; they do not commit independently.

An explanatory excerpt from the concrete constructor shows why a single commit reaches them all:

```python
def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
    self._session = session_factory()
    self.requests = RequestRepository(self._session)
    self.investigations = InvestigationRepository(self._session)
    self.outbox = OutboxRepository(self._session)
```

`flush()` may send a repository's pending changes to the database before `commit()`. It does not
make them independently durable. If the final attachment fails before commit, rollback removes
the new request, investigation, and event together. If I-1 already existed, rollback leaves that
previously committed investigation intact and discards only this transaction's changes.

### A factory gives every execution a fresh session

The historical snapshot constructs one long-lived action object; a current service calls a plain
async action with the factory as a keyword argument. Neither form lets concurrent requests share
one mutable transaction. [SQLAlchemy requires a separate AsyncSession for each concurrent task](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncsession-with-concurrent-tasks). The injected `Callable[[], InvestigationUnitOfWork]` means “a function that takes no
arguments and returns a fresh Unit of Work.” This explanatory excerpt shows its construction:

```python
def investigation_uow() -> SqlAlchemyInvestigationUnitOfWork:
    return SqlAlchemyInvestigationUnitOfWork(session_factory)


action = RequestInvestigations(
    unit_of_work_factory=investigation_uow,
    max_batch_size=100,
    subject="investigations.requested",
)
```

Inside `execute()`, `async with self._unit_of_work_factory() as unit_of_work` calls that factory,
awaits `__aenter__()`, and later awaits `__aexit__()` on either success or failure. In this sample,
commit is explicit: exiting the block successfully does not automatically commit. The concrete
implementation rolls back on a body exception and closes the session on either path.

**Success signal:** each execution receives a different session, all repositories within one
execution share it, and a failure before commit leaves no partially accepted batch. A unit fake
can verify sequencing, but only a real database test proves rollback and concurrent uniqueness.
The sample's acceptance fake mutates dictionaries immediately and has a no-op commit; it does
not simulate transactional rollback.

### Keep the transaction shorter than the external work

An LLM call or object-store upload cannot be rolled back by the platform database. Holding its
session open during those calls consumes a connection without making the external effects atomic.
The worker therefore loads state in one Unit of Work, closes it, performs external work, and opens
another to persist the result. A **checkpoint**, a durable record of completed progress, makes
that separation resumable; [the case study](12_trace_an_investigation_across_services.md) follows it.

⚠️ A lost connection during commit can leave the outcome unknown: the database may have committed
before the client lost the response. A translated “unavailable” error does not prove rollback.
Recovery needs a durable lookup or an idempotency contract, as explained in
[atomic transitions and outbox](../../background_work/reliability/01_atomic_transitions_and_outbox.md).

Do not add a multi-repository Unit of Work merely for a single read or because a transition touches
several tables. A narrow reader port or one atomic state-transition capability is the default. Use
the grouping when the action genuinely owns an interleaved sequence and needs one transaction view.

---

## 7. Contract tests and observability reveal translation mistakes

**Success signal:** an application unit test can drive each meaningful success and failure outcome
using a tiny fake, while the action imports no SDK exceptions. Separately, adapter tests prove each
provider outcome maps to the intended port outcome.

⚠️ The first failure is “leaky typing”: a port looks abstract but exposes `BaseMessage`,
`AsyncSession`, SQS receipt handles, or raw response dictionaries. The leak often appears later
when a fake must reconstruct provider objects just to test one business branch.

Do not create a port for a pure domain function. An action's I/O capability still requires a port
with one stable implementation; only optional outer-collaborator Protocols use the current-trigger
test from section 1.

> **Production:** preserve safe diagnostics through exception chaining or per-attempt telemetry;
> do not log and re-raise the same failure at every layer. The handling boundary logs once. A
> narrow known provider failure translates to the port contract; an unknown programming error
> must not be labelled “dependency unavailable.” The application receives stable owned failures,
> and telemetry excludes secrets and sensitive payloads.

---

**Next**: [Part 6 — Compose the Runtime at the Edge](06_compose_the_runtime_at_the_edge.md)
