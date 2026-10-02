# Map Code to the Boundary That Owns Its Decisions

> **Who this is for**: Engineers deciding where files belong in a deployable Python API, worker, consumer, or hybrid service.

A folder name is useful only when it predicts what changes there and what it may import. Start with
the smallest folders the current service needs; use this chapter's full tree as a placement policy,
not as permission to scaffold empty packages.

---

## 1. One mixed module contains several owners

A module named `ticket_service.py` often validates HTTP input, runs policy, queries SQLAlchemy,
calls a model, and publishes a message. “Service” says none of those responsibilities aloud, so each
new function makes ownership harder to infer.

For the running example, classify each operation before moving it:

| Operation | Why it changes | Owner |
|-----------|----------------|-------|
| Parse `POST /tickets/{id}/classify` | HTTP contract changes | `api/` |
| Decide whether a closed ticket is eligible | Business policy changes | `domain/` |
| Describe the required classification capability | Caller need changes | `ports/` |
| Build prompts and invoke a model | AI implementation changes | `genai/` |
| Execute ticket queries | Persistence changes | `db/` |
| Choose ACK or retry for an action outcome | Business delivery boundary changes | `workers/` |
| Decode SQS envelopes and perform settlement | Broker behavior changes | `adapters/` |
| Construct and dispose all of the above | Process lifecycle changes | `bootstrap/` |

> **Core:** place code by the decision it owns, not by the library it happens to import or the order
> in which it runs.

---

## 2. A representative hybrid AI service uses specialized outer boundaries

```text
src/ticket_triage/
├── __init__.py
├── main.py
├── bootstrap/
│   ├── app.py
│   ├── runtime.py
│   └── supervisor.py
├── config/
│   ├── settings.py
│   └── secrets.py
├── api/
│   ├── dependencies.py
│   └── tickets.py                  # Routes and their HTTP schemas
├── workers/
│   ├── inbox.py                    # Typed delivery and transport contract
│   └── classification.py           # Delivery → one action → ACK/retry
├── application/
│   ├── classify_ticket.py
│   └── replay_ticket.py
├── domain/
│   ├── ticket.py
│   └── classification.py
├── ports/
│   ├── ticket_classifier.py
│   ├── ticket_store.py
│   └── classification_publisher.py
├── db/
│   ├── models.py
│   └── tickets.py
├── adapters/
│   ├── sqs_inbox.py                # Envelopes, receipt handles, visibility
│   └── sqs_publisher.py
├── genai/
│   └── ticket_classification/
│       ├── llms.py                 # Model factory, settings-owned tuning
│       ├── runner.py               # Port implementation and provider translation
│       ├── schemas.py
│       └── prompts.py
└── observability/
    └── telemetry.py
```

Logically, `api/`, `db/`, and `genai/` are adapters. Physically, they receive specialized roots
because HTTP transport, persistence, and generative AI each develop recognizable ownership and
testing needs. Other external integrations remain under `adapters/`, initially in cohesive flat modules.
A provider subpackage earns its place only after actual growth, independent lifecycle, distinct
test setup, or naming pressure; the presence of AWS alone is not enough.

The supplied orchestrator and worker use this general shape. Follow
[one investigation across their files](12_trace_an_investigation_across_services.md) to see how
the owners cooperate. Shared `libs/` packages are a separate packaging choice: a database library
remains an outer implementation dependency, as explained in
[Shared Libraries](13_share_libraries_without_service_layers.md).

Do not add root `messaging/`. A business queue handler lives in `workers/`; its inbox adapter
lives in `adapters/`. The worker chooses ACK or retry from the action outcome, and the adapter
performs receipt-handle and visibility mechanics. The adapter also rejects malformed wire envelopes
before delivering typed data; it does not know which business action handles a valid message.
Do not place model code in general `adapters/`;
this repository standardizes every prompt, model, agent, AI schema, tool, and graph under `genai/`.

---

## 3. Nine questions place most ambiguous code

Ask what decision the code makes, then choose its owner:

1. Does it execute an understandable business operation and sequence effects? Put it in **`application/`**.
2. Is it a business value, invariant, or pure decision? Put it in **`domain/`**, even with one caller.
3. Does it describe an I/O capability an action needs? Put it in **`ports/`**.
4. Does it expose HTTP validation, responses, middleware, or routing? Put it in **`api/`**.
5. Does it run a worker iteration or map a business outcome to ACK/retry? Put it in **`workers/`**.
6. Does it execute queries or own persistence transactions? Put it in **`db/`**.
7. Does it implement LLM invocation, prompts, agents, AI tools, or graphs? Put it in **`genai/`**.
8. Does it translate another external technology, including broker wire mechanics? Put it in **`adapters/`**.
9. Does it construct, run, or dispose the runtime? Put it in **`bootstrap/`**.

These questions identify responsibilities, not a first-match escape hatch for a mixed function.
A route that also decides ticket eligibility contains two owners: HTTP translation belongs to the
route, and the eligibility decision belongs to a domain function called during the action. A
supervisor runs workers but never selects a business outcome. A broker adapter implements the
worker's `Inbox` conversation, not the worker's action call.

For example, a Pydantic request containing `callback_url` belongs beside the route in `api/tickets.py` when it exists
only for HTTP validation. A `ClassificationCandidate` shared by the action and classifier port is
an application-facing contract, not an HTTP schema.

---

## 4. Application and domain are related but not synonyms

`application/` owns executable business actions and effect sequencing. It answers “what does this
service do?” Examples include `classify_ticket`, `replay_ticket`, and `submit_batch`, each a public async function.
Even a read whose body is one store call remains an action so the catalog is complete.

`domain/` owns business meaning and every pure business decision: ticket eligibility, classification
status, reason codes, policy limits, and invariant failures. A rule does not wait for a second caller
to belong here. Private rules can still be tested directly as pure functions; placing them in an I/O
orchestrator would make that distinction harder to preserve. Omit `domain/` only when the service
has no such business values or decisions today.

This explanatory excerpt makes the decision boundary visible:

```python
# domain/ticket.py
@dataclass(frozen=True)
class TicketObservation:
    ticket_id: str
    status: TicketStatus


class ClosedTicket(Exception):
    pass


def ensure_classifiable(*, observed: TicketObservation) -> None:
    if observed.status is TicketStatus.CLOSED:
        raise ClosedTicket(observed.ticket_id)
```

The decision sees values, not SQLAlchemy rows or an HTTP request. With `T-100` observed as OPEN,
it permits classification; changing that observation to CLOSED raises the domain-owned failure.
Tests supply those values directly. The action loads data, calls the rule, and invokes the external
classifier; it does not implement a second eligibility branch in a route or worker.

For a durable transition, an eligibility check before an external call is not enough. The ticket
may close while the model is running. The atomic store operation must read the current row under a
lock, call the domain decision on that current observation, and apply its returned change in one
transaction, or use a version check with a named conflict result. The policy stays in `domain/`;
the transaction stays with the owner chosen in [Port Contracts](05_design_ports_and_adapter_contracts.md).

---

## 5. Errors, configuration, and helpers stay with their meaning

A global `utils/`, `common/`, `constants.py`, or `core/errors.py` hides ownership. Prefer:

```text
Business invariant             -> domain/ticket.py or domain/errors.py
Use-case failure               -> application/classify_ticket.py
Stable external failure        -> ports/ticket_classifier.py
Private provider failure       -> genai/ticket_classification/
SQS envelope constant          -> adapters/sqs_inbox.py
Deployment-varying timeout     -> config/settings.py
```

A value is configuration when an operator may change it by environment. A constant represents
stable code or domain semantics. Retry behavior stays near the boundary that can classify the
failure; correlation logic stays with the business rule that defines correlation.

> **Key insight**: a good package tree is an ownership map—given a change request, an engineer can
> predict the small set of files that should change and the dependencies they are allowed to know.

---

## 6. The tree is successful when omissions are intentional

**Success signal:** choose five current files and explain each location using one placement question.
Then inspect imports and confirm no inner package reaches into its concrete outer implementation.

⚠️ The first failure is cosmetic symmetry: a repository with empty `domain/`, one protocol for each
function, and one-class packages looks architectural while preserving no meaningful boundary.
Remove empty and pass-through layers.

Do not use the service tree for a non-deployable internal library. A library normally has a flat,
cohesive import package, a deliberate public API, and its own tests; it should not acquire
`bootstrap/`, `api/`, or deployment configuration merely to resemble services.

> **Production:** once several actions form one cohesive capability, promote only that slice—for
> example `application/tickets/classify.py` and `application/tickets/replay.py`. The
> [flat-first guide](10_grow_without_package_ceremony.md) owns the growth criteria.

---

**Next**: [Part 5 — Design Ports and Adapter Contracts](05_design_ports_and_adapter_contracts.md)
