# Dependencies Point Toward Business Policy

> **Who this is for**: Engineers who ran the vertical slice and want to understand why calls may go outward while imports still point inward.

`classify_ticket` invokes a classifier at runtime, yet the application must not import the concrete
LLM classifier. That apparent contradiction is the mechanism at the heart of Hexagonal
Architecture: control flow and source dependency are different graphs.

---

## 1. A direct import gives the provider ownership of the action

Suppose the action constructs its dependency directly:

```python
from ticket_triage.genai.ticket_classification.classifier import LLMClassifier


async def classify_ticket(*, ticket_id: str, tickets: TicketRepository) -> Classification:
    classifier = LLMClassifier()
    ticket = await tickets.get(ticket_id)
    category = await classifier.classify(ticket.body)
    return Classification(ticket_id, category)
```

The action now changes when model construction changes, tests need provider setup unless they patch
the imported symbol, and a rule-based alternative requires editing business code. The runtime call
was always outward; the problematic addition is the inward package importing an outer concrete
choice.

> **Core:** business policy may describe the capabilities it needs, but it must not select or
> construct the technologies that fulfill them.

---

## 2. Runtime flow and import direction form different graphs

At runtime, the action calls an injected implementation:

```text
classify_ticket ──call──► LLMClassifier ──HTTP──► model provider
```

In source code, both sides depend on the stable port:

```text
application/classify_ticket.py ──import──► ports/ticket_classifier.py
genai/.../runner.py         ──import──► ports/ticket_classifier.py
```

The concrete classifier may explicitly implement or merely structurally satisfy the protocol. The
important part is that `application/` does not import `genai/`.

This is **dependency inversion**: high-level policy does not depend on low-level implementation;
both depend on an abstraction shaped around the high-level caller's need.

> **The near-miss**: framework dependency injection and dependency inversion sound alike. FastAPI's
> `Depends` resolves values for a request; dependency inversion decides which source package is
> allowed to know which. A service can use `Depends` everywhere and still couple application code
> directly to SQLAlchemy or an LLM SDK.

---

## 3. The caller owns the conversation shape

A provider-shaped port leaks the wrong owner:

```python
# Provider details force every implementation to speak SDK language.
class ClassificationModel(Protocol):
    async def invoke(self, messages: list[BaseMessage]) -> AIMessage: ...
```

The application actually needs a business candidate:

```python
@dataclass(frozen=True)
class ClassificationCandidate:
    category: str
    confidence: float


class TicketClassifier(Protocol):
    async def classify(self, body: str) -> ClassificationCandidate: ...
```

The second contract permits an LLM, rules engine, hybrid, or remote classification API. More
importantly, it lets the action express business handling of category and confidence without
understanding provider messages.

The abstraction belongs near the caller because the caller determines the smallest stable
conversation. Concrete adapters translate richer provider APIs into that shape.

---

## 4. The composition root is allowed to know concrete choices

Someone must connect the abstract requirement to a concrete implementation. That code belongs at
the process edge, normally `bootstrap/runtime.py`:

This excerpt separates construction from the entry point's business call:

```python
# bootstrap/runtime.py — constructs the implementations and the runtime value.
repository = SqlAlchemyTicketRepository(sessions=session_factory)
classifier = LLMTicketClassifier(model=model)
runtime = Runtime(tickets=repository, classifier=classifier)

# api/routes.py — reads the API's runtime view and names action collaborators.
result = await classify_ticket(
    ticket_id=ticket_id,
    tickets=runtime.tickets,
    classifier=runtime.classifier,
)
```

The **composition root** constructs the process dependency graph at its edge. It knows concrete
implementations because choosing and disposing them is its job. The public action stays a plain
async function; it receives ports explicitly when an entry point calls it. Bootstrap never creates
a class, closure, or `partial` that hides those collaborators inside a bound action.

The entry point imports its own narrow runtime Protocol, not the concrete `Runtime` definition from
bootstrap. The concrete runtime structurally satisfies that view. This keeps API code from reaching
through the object into unrelated implementations and prevents an import back into the module that
already imports API code. [Runtime Composition](06_compose_the_runtime_at_the_edge.md) develops the
view and lifetime in a complete process.

Construction does not own business policy. Bootstrap may build a settings-derived threshold value
and select a classifier; a pure `domain/` decision determines what low confidence means. The action
or an atomic repository method calls that decision with values. Neither imports configuration to
look up the rule dynamically.

---

## 5. An import audit makes the rule testable

For the representative service, this map shows the main permitted edges, rather than every
allowed import. Bootstrap may also import domain, port, and observability types:

```text
main ──► bootstrap ──► api, workers, db, adapters, genai
api, workers ────────► application, domain, ports types
application ────────► domain, ports, observability
db ─────────────────► domain, ports
genai ──────────────► domain, ports
adapters ───────────► ports, domain; inbox imports its workers/inbox contract
domain ─────────────► dependency-light Python only
ports ──────────────► domain and dependency-light Python only
```

A GenAI tool has one explicit inbound-adapter exception: it may import the public application
action it invokes, just as an HTTP route does. The action still never imports the tool or its SDK.
An inbox adapter imports the worker-owned contract it implements, not the business handler.

An outer component can also implement a Protocol private to another outer consumer, when an
actual dependency/substitution trigger earns that contract. For example, a database evidence
index can import the retriever-owned Protocol without letting the retriever import concrete SQL.
Permit that exact contract edge; do not open general imports between concrete integrations.

The highest-value review checks are:

- `application/` imports no `api`, `workers`, `bootstrap`, `config`, `db`, `adapters`, `genai`, ORM, or provider SDK.
- `domain/` and `ports/` import no framework or concrete integration.
- API routes and business worker handlers each call exactly one public application action.
- A provider inbox adapter implements the worker's inbound contract and does not select actions.
- Entry points and implementations never import bootstrap; bootstrap constructs their runtime.
- Concrete driven adapters depend inward on the port they fulfill.
- Business code never imports bootstrap.

**Success signal:** replacing `LLMTicketClassifier` in `bootstrap/runtime.py` requires no edit in
`application/`. A silent failure is a type annotation or exception handler in the action that still
imports the old provider even though construction was moved.

> **Key insight**: dependency direction is determined by who owns the contract in source code, not
> by the direction of the runtime method call.

---

## 6. Cycles and pass-through layers expose misplaced ownership

⚠️ If `application/` imports an adapter while that adapter imports the action's types, a circular
import is often the first visible symptom. Moving imports inside functions hides the cycle without
fixing the two-way ownership.

Another smell is a layer that forwards every argument and result without owning behavior. Remove
handler wrappers, re-export modules, and transaction coordinators that merely rename a call. A
public application action is a deliberate exception: every business operation stays in the catalog,
even when its body is one port call.

```python
# Excerpt: a business read remains discoverable and reusable by every entry point.
async def read_ticket(*, ticket_id: str, tickets: TicketRepository) -> Ticket:
    return await tickets.get(ticket_id)
```

Adding fake steps to make this action look substantial would obscure the operation. Its role is a
stable entry contract and a complete catalog, not another layer of business decisions. Technical
liveness, readiness, metrics, and version endpoints call no business action. A provider client
library has a different role from a deployable service and does not copy this service shell.

**Every service enforces the import graph from creation.** Add import-linter contracts to pre-commit
and a CI job running those same hooks, including when CI does not exist yet. Contracts name the
canonical boundaries even if some directories are not present today. Waiting for enough contributors
lets the first outward import establish a dependency later features imitate. Static checks catch
that edge early; they cannot establish whether a pure function owns the right business decision or
whether a write is atomic. [Boundary Testing](09_test_through_architectural_boundaries.md) owns the
runnable contract configuration, deliberate failing edge, and behavioral evidence.

---

**Next**: [Part 4 — Map Code to Owning Boundaries](04_map_code_to_owning_boundaries.md)

