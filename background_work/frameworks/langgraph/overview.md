# LangGraph Fits Checkpointed Agent and Human-Interrupt Workflows

> **Who this is for**: Python engineers building graph-shaped LLM/agent workflows whose state, interruptions, and resume points must survive process loss.

Before reading this, compare checkpointed graphs with service workflows in **[State-Machine Design](../../workflows/01_state_machine_design.md)**.

---

## 1. Agent state needs a durable cursor, not a sleeping request

An agent researches, proposes an action, waits overnight for a human, and resumes with the full message/tool context. Keeping the request or worker alive cannot survive deployment. Re-running from the start repeats model and tool calls and may produce a different path.

LangGraph models execution as state, nodes, and edges. A **checkpointer** saves state at super-step boundaries under a stable `thread_id`; an **interrupt** persists the wait and resumes when a `Command` supplies input. The official persistence guide describes checkpoints, pending writes, replay, and thread identity: [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence). Checked 2026-08-03.

```text
thread_id=editorial-run-42
  checkpoint: research complete
  checkpoint: draft proposed
  interrupt:  waiting for reviewer
  resume:     approved
  checkpoint: generation next
```

> **The near-miss**: a checkpoint is not a cache of a function return. Resuming or time-traveling can re-execute nodes after a checkpoint, including LLM, API, and interrupt calls.

---

## 2. The minimal graph persists and resumes one approval

This example uses an in-memory checkpointer only to make the mechanism runnable. Production requires a durable checkpointer.

```python
from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class EditorialState(TypedDict, total=False):
    draft: str
    reviewer_id: str
    approved: bool
    artifact: str


def prepare_draft(state: EditorialState) -> EditorialState:
    return {"draft": "verified research draft"}


def review(state: EditorialState) -> EditorialState:
    decision = interrupt({"draft": state["draft"], "question": "Approve?"})
    return {
        "approved": bool(decision["approved"]),
        "reviewer_id": str(decision["reviewer_id"]),
    }


def generate(state: EditorialState) -> EditorialState:
    if not state["approved"]:
        return {"artifact": "rejected"}
    return {"artifact": f"final:{state['draft']}"}


builder = StateGraph(EditorialState)
builder.add_node("prepare_draft", prepare_draft)
builder.add_node("review", review)
builder.add_node("generate", generate)
builder.add_edge(START, "prepare_draft")
builder.add_edge("prepare_draft", "review")
builder.add_edge("review", "generate")
builder.add_edge("generate", END)
graph = builder.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    config = {"configurable": {"thread_id": "editorial-run-42"}}
    paused = graph.invoke({}, config)
    assert "__interrupt__" in paused
    completed = graph.invoke(
        Command(resume={"approved": True, "reviewer_id": "editor-7"}),
        config,
    )
    assert completed["artifact"] == "final:verified research draft"
    print(completed)
```

Success is a first invocation containing `__interrupt__` and a second invocation producing the artifact under the same `thread_id`. Using a different ID starts a different thread and does not resume the checkpoint.

> **Key insight**: The checkpoint makes graph state durable; it does not make node effects exactly once. Stable thread identity recovers control flow, while operation identity recovers external effects.

---

## 3. Production durability needs an external checkpointer

`InMemorySaver` disappears with the process and is suitable only for tests. Use a supported database-backed checkpointer or the managed Agent Server persistence path, configure retention/encryption, and test restart against the actual store.

### Restart a paused thread in a second process

The [complete persisted example](../../examples/langgraph/approval.py) keeps the same graph and replaces only the saver, adding a tiny durable effect record for generation. Start PostgreSQL using the [job lab](../../foundations/03_minimal_durable_task.md#run-one-job-before-studying-the-schema). From the repository root:

```bash
cd background_work/examples/langgraph
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
export DATABASE_URL=postgresql://lab:lab@127.0.0.1:56432/jobs
.venv/bin/python approval.py pause editorial-run-42
.venv/bin/python approval.py resume editorial-run-42
```

The first process prints `paused ('review',)` and exits completely. The second recreates the graph against PostgreSQL, verifies that its next node is `review`, and prints `resumed final:verified research draft`. No original input is resubmitted. Use a fresh thread ID for another experiment; a completed thread is not a waiting approval.

The checkpointer's `setup()` creates its schema in this lab. Production migration permissions should be separate from the runtime role. A `graph_effects` row is keyed by `thread_id:generate:v1`; its request hash prevents reusing the same operation for changed input. This is a local transactional effect fixture. A remote provider needs the external-effects protocol, including recovery when provider success and local recording are separated by a crash.

The state belongs to PostgreSQL across process boundaries; resuming still reruns the interrupted node.

```mermaid
sequenceDiagram
    participant A as Process A
    participant D as PostgreSQL saver
    participant B as Process B
    A->>D: Save draft and review interrupt for run-42
    Note over A: Process exits
    B->>D: get_state thread run-42
    D-->>B: next = review
    B->>B: Restart review node with resume decision
    B->>D: Save generation effect and completed checkpoint
```

The draft checkpoint avoids repeating preparation. Code before `interrupt()` in `review` would run again; keep it pure or idempotent. [PostgresSaver setup and lifecycle](https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint-postgres/README.md), checked 2026-10-30.

The persisted contract includes:

- Stable `thread_id` mapped to the business workflow/run.
- Serializable, bounded state; large artifacts live behind immutable references.
- Checkpoint and pending-write retention sized for active threads.
- Access control for message, prompt, tool, and human-review data.
- Search/operational index for interrupted, busy, and failed threads.
- Backup, restore, schema migration, and deletion behavior.

The checkpointer saves state at super-step boundaries; successful node writes within a failed parallel super-step can be retained as pending writes. Recovery granularity therefore follows node and super-step design, not arbitrary Python lines.

---

## 4. Interrupts restart the node from its beginning

The official interrupt guide states that resuming restarts the node containing `interrupt()` from the beginning. Code before the interrupt executes again: [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts). Checked 2026-08-03.

```text
node begins
  → code before interrupt executes
  → interrupt persists wait
  → resume restarts node
  → code before interrupt executes again
  → resume value becomes interrupt() result
```

Keep pre-interrupt work pure or idempotent. Do not send an email, charge, or mutate an external system before `interrupt()` unless the operation uses a stable key and a durable local/provider record. Do not reorder multiple interrupts in the same node; resume values are matched by their execution order.

⚠️ Wrapping `interrupt()` in a broad `try/except` can catch the runtime's control-flow exception and prevent the graph from pausing correctly.

---

## 5. Time travel re-executes later nodes

Replaying from a prior checkpoint skips nodes before it and re-executes nodes after it. The official time-travel guide explicitly includes LLM calls, API requests, and interrupts among the re-executed work: [Time travel](https://docs.langchain.com/oss/python/langgraph/use-time-travel). Checked 2026-08-03.

Design tool/provider nodes like background activities:

```text
operation_key = thread_id + logical_node_purpose + definition_version
request_hash  = canonical tool input
local record  = INTENT → SUCCEEDED
checkpoint    = stores result reference, not the only evidence of the effect
```

For non-repeatable exploration, fork under a new business operation scope. Reusing the original operation key deliberately returns the original effect rather than creating an alternative one.

---

## 6. Graph changes are compatibility changes for saved threads

LangGraph applies current deployed graph code to persisted threads. Its current compatibility guidance warns that removing/renaming a node can break a thread paused at that node, and that renamed or incompatibly changed state fields can break old checkpoints: [Backward compatibility](https://docs.langchain.com/oss/python/langgraph/backward-compatibility). Checked 2026-08-03.

Use an add-then-remove migration:

- Add new state keys as optional with defaults for old checkpoints.
- Keep old node names as routing shims through a drain window.
- Dual-read/dual-write renamed state temporarily.
- Inspect `get_state()` and `get_state_history()` for representative in-flight threads before deployment.
- Record a graph/business definition version in state when old and new behavior must differ.

⚠️ A graph that resumes technically can still violate business compatibility if the new conditional edge interprets old state differently.

---

## 7. Choose LangGraph for graph state, not generic queues

Use LangGraph when LLM/tool loops, branching graph state, streaming, human interrupts, checkpoint inspection, and alternative-path replay are central. Use a database-backed state machine for a small service lifecycle whose source of truth is relational business state. Use a Temporal-class engine when general service-workflow timers, signals, activity retries, and long-lived deterministic orchestration dominate rather than agent state.

Do not use a checkpointer as the only record of a payment, email, or domain entity. Do not use LangGraph for one independent job merely to obtain retries.

**How you know it is working**: stop the runtime at an interrupt and mid-graph, restart it against the durable store, resume the same thread, and assert one effect per operation key. Monitor checkpoint-write failures, interrupted/error thread age, state size, replayed node count, and graph-version compatibility.

---

## Recap and check yourself

- A stable thread ID plus durable checkpointer preserves graph progress across processes.
- Resume restarts the interrupted node, so preceding code may execute again.
- Graph compatibility and external-effect identity require policies beyond checkpoint persistence.

**send_email runs before interrupt. How many sends can occur after resume?**

<details><summary>Answer</summary>

At least two across the first run and resume, because the node restarts. Place the effect after approval or use a stable operation key and durable result reconciliation.

</details>

**An old thread waits at review, but the deployment renames that node. Why is keeping the saved data insufficient?**

<details><summary>Answer</summary>

The saved cursor refers to a node in the graph. Keep a compatible routing shim or migrate the thread explicitly; data persistence does not provide code compatibility.

</details>

**Try it:** Move a notification before `interrupt()` in a scratch graph. Replace it with `load_or_create_effect(operation_key=...)`; fill the key from the state/thread context.

<details><summary>Hint and worked solution</summary>

The key describes the business notification, not this node invocation. Use a stable thread ID plus notification purpose and definition version, and compare the request hash. Resume can call it again but returns the recorded outcome. A real provider also needs ambiguity reconciliation.

</details>


**Next**: [Part 9: Decision Guide](../00_system_selection.md)
