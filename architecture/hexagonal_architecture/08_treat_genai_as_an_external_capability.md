# Treat GenAI as an External Capability

> **Who this is for**: Engineers adding structured model calls, agents, tools, retrieval, or LangGraph workflows without turning AI code into the business layer.

A large language model (LLM) is remote, nondeterministic, expensive, and provider-controlled. It is
therefore an unusually strong candidate for a port. The application should receive a typed business
candidate—not model messages, prompt templates, graph state, or raw provider JSON.

---

## 1. A model call is not the classification use case

The application action may load a ticket, enforce eligibility, request a classification candidate,
interpret confidence, persist the decision, and publish the next outcome. The GenAI implementation
may build provider input, invoke the configured handle, validate structured output, and translate
provider failures.

```text
application/classify_ticket.py
    owns eligibility → request candidate → interpret → persist/handoff

genai/ticket_classification/runner.py
    owns prompt input → invoke model → validate provider output → port result
```

If `genai/` decides whether a ticket is eligible or where low-confidence work goes, provider
mechanics have absorbed business policy. If `application/` constructs prompts or catches SDK
exceptions, the dependency points outward.

> **Core:** every LLM, prompt, agent, AI schema, tool, graph, model binding, and behavior-changing AI middleware lives
> under root `genai/`; business execution remains under `application/`.

---

## 2. Start with one compact structured capability

The [baseline](02_build_one_vertical_slice.md) asks `TicketClassifier.classify(body)` for a category
string. Keep that contract for the first real model call. A provider-facing schema validates the
model answer; the implementation returns only its category:

```python
# genai/ticket_classification/runner.py — explanatory excerpt
class ClassificationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["billing", "general", "human_review"]


class LLMTicketClassifier:
    def __init__(self, *, model: BaseChatModel) -> None:
        self._structured = model.with_structured_output(ClassificationOutput)

    async def classify(self, body: str) -> str:
        output = await self._structured.ainvoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=body),  # untrusted ticket data, separate from instructions
        ])
        return output.category
```

This success-path excerpt omits the failure translation developed below. The service standard uses
LangChain chat models for inference, including one structured call; agents and explicit graphs use
LangChain and LangGraph. The action sees neither framework. The [model structured-output guide](https://docs.langchain.com/oss/python/langchain/models#structured-output)
describes the schema-binding mechanism used here. Bootstrap calls a factory with resolved
model options, builds the model once, and injects it. No model, agent, checkpointer, or MCP client is
constructed at import time.

One-line structured binding belongs in the runner constructor. The current service standard uses
`llms.py`, `prompts.py`, `schemas.py`, and `runner.py` for this simple capability: construction,
versioned instructions, provider schema, and invocation each have a known home. Every model is
built through `init_chat_model` in `llms.py`, with tuning defaults owned by its settings slice;
the integration constructs its clients. Shared provider policy moves to `genai/shared/llms.py`
only when a second task needs identical semantics.

When confidence becomes a business input, evolve the port to return a typed `ClassificationCandidate`
with category and bounded confidence. The GenAI schema validates that representation; a pure domain
decision interprets confidence against policy. This is an explicit extension of the baseline's string
contract, not permission for the model implementation to decide whether human review is required.

---

## 3. Agent factories assemble harnesses but do not invoke them

An agent task adds `agent.py`:

```text
genai/pricing_agent/
├── llms.py
├── schemas.py
├── prompts.py
├── tools.py
├── agent.py
└── runner.py
```

`agent.py` accepts constructed models and explicit tools, then returns the harness. `runner.py`
implements the application-facing `TicketPricer` capability by invoking the harness and
translating its result.

A custom `graph/` package is justified only when the service defines graph state, nodes, routing,
or edges. Using an agent library that internally has a graph does not create a project-owned graph
responsibility.

---

## 4. Tools cross trust boundaries and need narrow authority

A tool that changes business state, or exposes an operation also reached by a route, worker or
CLI, is a business entry point and calls exactly one public action. A read-only tool used only
inside its agent calls its GenAI collaborator directly; the outer capability port is already the
action-test boundary. I/O alone does not require another action or application port. Promote that
read when another entry point needs it. This ticket read is also exposed through HTTP, so its tool
calls the same authorization-aware action:

```python
# application/get_ticket.py — excerpt
async def get_ticket(
    *, ticket_id: str, context: ApplicationContext, tickets: TenantTicketReader
) -> TicketView:
    require_ticket_read_access(context)  # pure domain check over trusted values
    return await tickets.get_for_tenant(ticket_id=ticket_id, tenant_id=context.tenant_id)


# genai/support_agent/tools.py — excerpt
from langchain.tools import ToolRuntime, tool
from langchain_core.tools import BaseTool
# ToolReply is a bounded typed envelope; AccessDenied/TicketNotFound are declared
# domain/action errors. The two dependency bases come from ports/errors.py.
def build_ticket_tool(*, tickets: TenantTicketReader) -> BaseTool:
    @tool
    async def ticket_tool(ticket_id: str, runtime: ToolRuntime[ApplicationContext]) -> ToolReply:
        """Read a ticket within the caller's authorized tenant."""
        context = runtime.context  # typed ApplicationContext supplied by the server
        try:
            ticket = await get_ticket(ticket_id=ticket_id, context=context, tickets=tickets)
        except AccessDenied:
            return ToolReply(code="forbidden", ticket=None)
        except TicketNotFound:
            return ToolReply(code="not_found", ticket=None)
        except DependencyUnavailableError:
            return ToolReply(code="temporarily_unavailable", ticket=None)
        except DependencyRejectedError:
            return ToolReply(code="request_rejected", ticket=None)
        return ToolReply(code="ok", ticket=ticket)
    return ticket_tool
```

The builder captures process-lifetime collaborators, not a tenant identity. Assemble the agent
with `context_schema=ApplicationContext` and invoke it with `context=context`; `ToolRuntime`
provides the immutable trusted values for that run. Keep counters and collected evidence in
per-invocation agent state. Use ContextVars only when a callback has no framework context channel;
bind and reset them together inside invocation and fail loudly on missing bindings. A cached
harness must not share identity or budgets between concurrent runs.

The action checks the business precondition, so HTTP and workers cannot skip it. The port performs
tenant-scoped retrieval; the model cannot use prompt-authored identity to broaden that query. The
excerpt handles every declared failure of this read with an allowlisted envelope, without exposing
exception text. An undeclared defect stops the run instead of becoming a fabricated safe result.
For a task whose declared failure must stop the whole run, the tool raises a GenAI-private abort
that the capability translates once into its own port error. Another port's errors and private SDK
failures must not escape the capability untranslated.

The agent must not invent `tenant_id` from prompt text. Tool discovery must not silently broaden
permissions. A tool should not query a database directly if doing so bypasses application
authorization or auditing.

Prompt injection is the attack: untrusted ticket text tells the model to retrieve another tenant's
ticket; an overpowered tool obeys. The defense is server-supplied identity, authorization inside the
action/domain boundary, and a capability narrow enough that model text cannot choose wider authority.

---

## 5. Retrieval and prompts follow semantic ownership

Keep retrieval local to one AI capability until another genuinely reuses the same retrieval,
reranking, and context semantics. Agent-only query retrieval uses a direct GenAI collaborator;
its vector-search class stays in `db/`, typed by a private Protocol in the retriever module and
injected by bootstrap. Shared hit types belong in `domain/`. It does not need
`ports/retrieval.py` or an application search action until another entry point uses the read.
Application-owned ingestion and index-refresh actions remain in
`application/`; their index contracts remain in `ports/`; concrete persistence belongs in
`db/` or the appropriate adapter.

Prompts are versioned implementation details of their AI task. Every persisted AI-derived value carries both the prompt version and model name that
produced it; values only logged emit both on the record. Each `prompts.py` exports `PROMPT_VERSION`.
Without this provenance, a changed answer cannot be tied to the prompt or model that generated it.

Persisting classifications is another explicit extension of the baseline, whose string result has
no provenance. Add neutral evidence fields to the port result, then preserve them through storage:

```text
genai: configured model name = "triage-model-v2"; PROMPT_VERSION = "ticket-2026-10-02"
port result: ClassificationCandidate(category="billing", confidence=0.91,
             prompt_version="ticket-2026-10-02", model_name="triage-model-v2")
action: pure confidence decision accepts candidate; passes candidate evidence to store port
db row: ticket_id=T-100, category=billing, prompt_version=ticket-2026-10-02,
        model_name=triage-model-v2
```

The implementation attaches its configured provenance; the model does not invent it. These strings
are technology-neutral evidence, not a model handle or provider message. An action that discards
them before persistence breaks the requirement even though the category remains correct. A DB
integration test verifies the stored fields; a fake model unit test verifies the implementation's
metadata without a paid call.
 Similar wording is not enough to justify `genai/shared/prompts/`;
promote only demonstrated shared semantics.

> **Key insight**: GenAI belongs outside the application not because it is unimportant, but because
> its nondeterminism, trust boundary, cost, and provider mechanics must not define business policy.

---

## 6. Context-dependent agents separate reusable configuration from one run

An investigation's valid reason codes and manuals can change after deployment. A single agent
constructed at startup can retain an obsolete output schema; rebuilding everything for every
message wastes work. The sample separates a **control context**, an immutable snapshot of manuals,
valid codes, and schema names, from the agent machinery built for that snapshot.

First follow one call with illustrative values:

```text
ResolveControlContext → context generation 7, allowed reason codes [R1, R2]
InvestigateException → analyst.analyze(input, context=context)
ContextualLLMExceptionAnalyst → build or reuse a harness for this context
LLMExceptionAnalyst → invoke harness, validate output, return ExceptionAnalysis
InvestigateException → interpret and checkpoint the result
```

A **harness** is the wrapper that assembles and executes the model, tools, middleware, and output
handling. `agent.py` assembles the agent; `harness.py` adapts its execution interface;
`analyst.py` presents the application-facing capability. These names describe the supplied sample, whose shape differs from the current standard. For
new code, `agent.py` assembles and `runner.py` invokes/translates; use the fixed names rather than
copying its `harness.py` and `analyst.py` layout. Add `memory.py` for agent-memory behavior and
`middleware.py` for behavior hooks only when those responsibilities exist.

### Two caches avoid different kinds of repeated work

`ResolveControlContext` uses a shared Redis cache keyed by tenant scope, deployment release, and
configuration **generation**, a number advanced when configuration is reset. It coordinates a
rebuild through a temporary exclusive lease so concurrent workers do not all fetch and summarize
the same configuration. Summarized manuals have their own object-store keys that include the
configuration digest and prompt version.

`ContextualLLMExceptionAnalyst` separately caches constructed analysts inside one process. Its key
includes the generation, manual digests, code vocabularies, and schema names. When the generation
changes, it clears that local cache before selecting the analyst.

```text
call A: generation 7, context K → construct analyst A7
call B: generation 7, context K → reuse A7; execute a new analysis
call C: generation 8, context K → clear local cache; construct A8
```

Reusing an analyst does not mean reusing its answer. The sample creates a fresh tool-call budget
inside each `analyze()` invocation. The reusable harness must likewise avoid leaking one
investigation's conversation or tool state into another concurrent run.

For the shared context, a reset can require refetching configuration while unchanged manual
digests still permit reuse of stored summaries. “Cache invalidated” therefore does not imply
“every investigation pays for a new summary.” The sample tests these separately in
`tests/unit/application/test_resolve_control_context.py` and
`tests/unit/genai/exception_analysis/test_contextual_analyst.py`.

### Schema validation and application decisions remain different steps

If the active vocabulary contains R1 and R2 but the model returns R9, the provider-facing schema
and subsequent domain validation reject that result. `LLMExceptionAnalyst` converts accepted
`AnalysisOutput` into `ExceptionAnalysis`; its caller never needs to inspect model messages.
An exhausted transient provider failure becomes `AnalysisUnavailableError`, which the application
classifies for investigation retry. Invalid analysis is a different outcome from unavailability.

⚠️ A cache key that omits a changing input can preserve an old prompt or schema without raising
an error. The tell is output validated against yesterday's vocabulary after a configuration
change. Test equal contexts for reuse and changed contexts for reconstruction; do not infer cache
correctness from reduced model latency.

**Success signal:** the action sees the same typed capability regardless of how the harness is
built; changing the configuration generation replaces cached construction; each analysis still
gets fresh invocation state. These are architectural and behavioral checks, not a guarantee of
answer quality, which requires [LLM testing and evaluation](../../operations/testing/13_testing_llm_code.md).

Do not introduce generation caches and harness wrappers for a fixed prompt with one small model
call. Add them when configuration changes and repeated construction create a measurable need.

---

## 7. Test the seam before paying for a live call

Test prompt assembly, schema rejection, factories, capability invocation with a fake model handle,
failure translation, graph routing, and authorization propagation separately. Ordinary unit tests
make no live model call and require no provider credentials.

**Success signal:** `classify_ticket` can be tested with a six-line fake `TicketClassifier`, while
`LLMTicketClassifier` can be tested with a fake model handle returning structured output. Changing
model provider edits `genai/`, configuration, and bootstrap—not application policy.

⚠️ The first failure is raw provider output crossing the port. The symptom is application code
reading message content, tool-call arrays, or provider refusal fields. Translate them into stable
typed outcomes inside `genai/`.

Do not create a GenAI abstraction when the product is intentionally a thin provider-specific client
library with no independent business action. In a deployable business service, however, even one
small model call belongs under the explicit `genai/` boundary.

### Provider failures have one translation and one handling boundary

The classifier translates framework/SDK failures directly into its port vocabulary. Classification
follows what is wrong, rather than blindly copying HTTP codes:

| Observed failure | Port meaning | Named handling boundary |
|---|---|---|
| Timeout, 429, 5xx, expired credentials or misconfigured provider endpoint | Unavailable capability | Declared action fallback/retry outcome; otherwise API handler or supervisor outage backoff |
| This item's business data is refused | Rejected input | Action records rejection or chooses a domain fallback |
| Schema/semantic output validation fails | Distinct invalid-output error, classified as rejected | Action decides human review or another declared outcome |
| Unknown exception or programmer defect | Propagate unchanged | Request/process boundary records defect; supervisor fails fast |

An expired credential affects every item; treating it as a permanent rejection would fail each item
until an operator fixes the token. The authoritative local [error rules](../../python-service-architecture/references/errors.md)
classify it as unavailable. Invalid output remains distinct even when both cases lead to review.
The action maps a port failure into a domain value before calling a pure domain decision; domain
code never imports port exceptions. The [port-contract chapter](05_design_ports_and_adapter_contracts.md)
owns the stable error types.

Exactly one layer retries a physical provider call. A LangChain provider factory sets explicit
request timeout and disables SDK retries (`max_retries=0` for the corresponding client); the
capability's bounded retry policy counts each call as one attempt. If an enclosing owner retries
instead, the capability does not retry too. Changing provider requires rechecking that provider's
retry options rather than assuming every constructor uses the same field names.

A request deadline covers acquisition and the model call, not only socket reads. Token/cost and
tool-call budgets bound one invocation; tests force exhaustion rather than measuring only latency.
An outage records safe error classification and attempts at its handling boundary, once. Do not
log raw sensitive prompts, credentials, or provider bodies. Refusal must become a named safe result
or port error; an empty category is not a useful failure contract.

Behavior-changing middleware such as fallback, summarization, token limits, and tool policy belongs
in the owning `genai/` task. A callback or middleware that only emits traces, metrics, or usage belongs
in `observability/`, even when it imports LangChain. The effect it owns determines placement.

**Changed-condition check:** provider credentials expire for all tenants. The caller cannot repair
one ticket by altering its data. Record capability unavailability, stop or defer according to the
action's declared policy, and alert the operator; do not mark every ticket permanently rejected.
Separately, one model answer with an unknown reason code follows invalid-output policy and need
not stop every other item's processing.

---

**Next**: [Part 9 — Test Through Architectural Boundaries](09_test_through_architectural_boundaries.md)
