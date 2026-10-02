# Build One Vertical Slice Before Adding Layers

> **Who this is for**: Python backend engineers who want a runnable first example of one application action shared by two inbound adapters.

The example below classifies two support tickets. An HTTP-shaped function and a worker-shaped
function both call the same `classify_ticket` action, passing its collaborators explicitly. The only
requirement is Python 3.11 or newer; save the block as `slice.py` and run `python slice.py`.

---

## 1. Run the complete baseline

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    body: str


@dataclass(frozen=True)
class Classification:
    ticket_id: str
    category: str


class TicketRepository(Protocol):
    async def get(self, ticket_id: str) -> Ticket: ...


class TicketClassifier(Protocol):
    async def classify(self, body: str) -> str: ...


async def classify_ticket(
    *, ticket_id: str, tickets: TicketRepository, classifier: TicketClassifier
) -> Classification:
    ticket = await tickets.get(ticket_id)
    category = await classifier.classify(ticket.body)
    return Classification(ticket.ticket_id, category)


class InMemoryTickets:
    def __init__(self, tickets: list[Ticket]) -> None:
        self._tickets = {ticket.ticket_id: ticket for ticket in tickets}

    async def get(self, ticket_id: str) -> Ticket:
        return self._tickets[ticket_id]


class KeywordClassifier:
    async def classify(self, body: str) -> str:
        return "billing" if "invoice" in body.lower() else "general"


class EntryRuntime(Protocol):
    @property
    def tickets(self) -> TicketRepository: ...

    @property
    def classifier(self) -> TicketClassifier: ...


@dataclass(frozen=True)
class Runtime:
    tickets: TicketRepository
    classifier: TicketClassifier


async def http_handler(ticket_id: str, runtime: EntryRuntime) -> dict[str, str]:
    result = await classify_ticket(
        ticket_id=ticket_id, tickets=runtime.tickets, classifier=runtime.classifier
    )
    return {"ticket_id": result.ticket_id, "category": result.category}


async def worker_handler(message: dict[str, str], runtime: EntryRuntime) -> None:
    result = await classify_ticket(
        ticket_id=message["ticket_id"],
        tickets=runtime.tickets,
        classifier=runtime.classifier,
    )
    print(f"worker classified {result.ticket_id} as {result.category}")


async def main() -> None:
    runtime = Runtime(
        tickets=InMemoryTickets(
            [
                Ticket("T-100", "My invoice contains the wrong amount"),
                Ticket("T-200", "How do I change my email address?"),
            ]
        ),
        classifier=KeywordClassifier(),
    )

    response = await http_handler("T-100", runtime)
    print(f"http response: {response}")

    await worker_handler({"ticket_id": "T-200"}, runtime)


asyncio.run(main())
```

Expected output:

```text
http response: {'ticket_id': 'T-100', 'category': 'billing'}
worker classified T-200 as general
```

**Success signal:** both lines appear, and both entry points call the same action function using
the same constructed implementations. If you see `KeyError`, the requested ticket ID is absent
from `InMemoryTickets`; that is the baseline's deliberately small failure contract.

> **Production:** this baseline intentionally defers typed failure contracts, persistence,
> transactions, provider timeouts, retries, telemetry, and lifecycle management. It runs two
> transport-shaped functions, not a live HTTP server or queue consumer. The later notes add those
> concerns after their need becomes visible.

---

## 2. Three kinds of code cooperate without knowing everything

The example has three architectural roles:

```text
Driving adapters              Application core              Driven adapters
────────────────              ────────────────              ───────────────
http_handler ────────────────► classify_ticket ────────────► InMemoryTickets
worker_handler ──────────────►       │                      KeywordClassifier
                                  contracts
```

A **driving adapter** translates an external trigger into an application call. A **driven adapter**
fulfills a capability requested by the application. The word “adapter” means translation at a
boundary; it does not require inheritance from a framework base class.

`classify_ticket` coordinates the use case. It knows that classification requires loading a ticket
and obtaining a category. It does not know whether the trigger was HTTP or a queue message, or
whether ticket loading uses memory or PostgreSQL. The fake keyword implementation stands in for an
external classifier capability; a real service's local pure calculation would instead be imported
directly from `domain/`.

The public `classify_ticket` signature is the application’s **inbound contract**: it says how an
entry point invokes this operation and what it receives. Driving adapters call that function
directly; there is no duplicate Protocol around the action. The `TicketRepository` and
`TicketClassifier` Protocols are **outbound ports**, implemented by driven adapters.

The runtime holds constructed collaborators. The action receives the specific collaborators it
uses, rather than the whole runtime. Each entry point reads a narrow runtime view and passes those
fields at the call site. `EntryRuntime` is an edge-local Protocol: it describes what handlers read
without importing the bootstrap module that constructs `Runtime`. In a packaged service, API and
worker views live beside their respective consumers; they are not application I/O ports.

This explicit wiring has a cost. If classification later needs another capability, both handlers
must pass it. The benefit is that each call visibly names the operation's dependencies and the type
checker can catch a missing collaborator. Bootstrap builds the implementations once, without
binding application functions into handler objects.

> **Core:** the application action is the stable center. Entry points call it, external
> implementations satisfy its contracts, and the process edge constructs those implementations.

---

## 3. Structural typing keeps the first port small

Python's `Protocol` defines behavior by shape. The action accepts any object with the declared async
method, without requiring concrete adapters to inherit from the protocol, as defined by
[Python’s Protocol documentation](https://docs.python.org/3/library/typing.html#typing.Protocol):

```python
class TicketClassifier(Protocol):
    async def classify(self, body: str) -> str: ...
```

`KeywordClassifier` satisfies this contract because it has a compatible `classify` method. A future
LLM-backed implementation can satisfy the same caller need while hiding messages and provider
responses. Python does not validate this annotation automatically at runtime; a type checker checks
the compatibility, and tests check behavior.

Under this repository's service standard, **every I/O capability used by an action has a port**,
even with one implementation. The persistence reader and external classifier are two capabilities;
their contracts describe what the action needs rather than every query or SDK method. A pure
`normalize_subject()` calculation does not earn an application port: import and test the domain
function directly. Nondeterministic clock, ID, or random inputs use typed callables or passed values;
[Port Contracts](05_design_ports_and_adapter_contracts.md) develops that distinction.

---

## 4. Entry points translate rather than decide policy

The HTTP-shaped handler takes a ticket ID and turns `Classification` into a response dictionary.
The worker-shaped handler takes the same ID from a message and turns the result into a log line.
Both invoke exactly one business action. Neither constructs a classifier or queries storage itself.

An actual FastAPI route would translate path parameters and results. A business queue handler in
`workers/` would receive typed business data, call the action, and choose ACK or retry according
to the outcome; a completed business rejection may also be acknowledged. The provider inbox adapter
in `adapters/` validates raw envelopes, dead-letters malformed wire messages, and performs
receipt-handle, visibility, and settlement mechanics. It does not choose which business action runs.
[APIs and Workers](07_apply_the_pattern_to_apis_and_workers.md) develops that transport boundary.

Neither entry point should decide which category is valid or whether a ticket is eligible. Those
are pure domain decisions, even if only this action needs them. If the worker later has different
business requirements, introduce a different action or an explicit policy input to a domain
decision, rather than hiding the branch in queue code.

A simple business read remains a public catalog action even when its body is one port call. Health,
readiness, metrics, and version endpoints report the process itself and call no business action.
This preserves one discoverable answer to “what does the service do?” without inventing extra steps.

---

## 5. Replace an adapter without editing the action

Change only the runtime's constructed classifier in `main()`:

```python
# Excerpt: add this implementation, then use it as Runtime.classifier.
class AlwaysEscalateClassifier:
    async def classify(self, body: str) -> str:
        return "human_review"


runtime = Runtime(tickets=runtime.tickets, classifier=AlwaysEscalateClassifier())
```

The HTTP response's category and worker's printed category now become `human_review`. The action
and its callers remain unchanged because the new class fulfills the same capability shape. The
runtime field changes the implementation; it does not change the required conversation.

> **Key insight:** the first useful hexagon is one application action whose external capabilities
> can be replaced through small contracts. The directory tree preserves that property as code grows.

### Predict a changed requirement before adding code

Suppose a CLI now needs classification, and an audit store must record every result. Could bootstrap
bind the new store into the action so only the CLI call changes? Which files need to change instead?

**Worked reasoning:** the new CLI is another entry point, so it translates its argument into the
same action call. The audit store is a new I/O capability of that action, so it gets a port and an
explicit action parameter. Bootstrap constructs the store and exposes it through the relevant
runtime views. HTTP, worker, and CLI callers all pass it. Updating only the CLI would let the other
entry points skip a required collaborator; hiding a bound action in bootstrap would remove the
visibility the explicit call sites are meant to preserve. No transport decides whether auditing
happens. The audit's atomicity and failure policy are new requirements to resolve before writing it;
adding a port alone does not make recording and another durable write atomic.

---

## 6. Know what breaks first and when to stop

⚠️ The first real failure is the untyped `KeyError` from the repository. Once callers must distinguish
not-found, transient storage failure, and invalid state, define stable port-owned contracts as shown
in [Port Contracts](05_design_ports_and_adapter_contracts.md).

Do not split this example into eleven production packages yet. A few cohesive modules are clearer
at this scale. Introduce physical boundaries from [Boundary Placement](04_map_code_to_owning_boundaries.md)
when frameworks, providers, lifecycle, or independent ownership make the dependency rule hard to
see in a flat package. The action and I/O contracts stay required by the service standard; empty
folders, forwarding wrappers, and a class around a one-call action do not.

**How you know the design still works:** add another entry point or classifier without changing the
action's orchestration. If a new transport requires business branches in the handler, or a provider
requires SDK types in the port, revisit which side owns the translation.

---

**Next**: [Part 3 — Dependencies Point Toward Business Policy](03_dependencies_point_toward_business_policy.md)
