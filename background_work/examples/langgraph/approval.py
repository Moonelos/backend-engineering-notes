from typing_extensions import TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
import os
import sys
import hashlib
import psycopg
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
    key = sys.argv[2] + ":generate:v1"
    digest = hashlib.sha256(state["draft"].encode()).hexdigest()
    artifact = f"final:{state['draft']}"
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS graph_effects (operation_key text PRIMARY KEY, request_hash text NOT NULL, artifact text NOT NULL)")
        conn.execute("INSERT INTO graph_effects VALUES (%s,%s,%s) ON CONFLICT DO NOTHING", (key,digest,artifact))
        saved = conn.execute("SELECT request_hash,artifact FROM graph_effects WHERE operation_key=%s", (key,)).fetchone()
        if saved[0] != digest:
            raise ValueError("operation key reused with changed draft")
        return {"artifact": saved[1]}


builder = StateGraph(EditorialState)
builder.add_node("prepare_draft", prepare_draft)
builder.add_node("review", review)
builder.add_node("generate", generate)
builder.add_edge(START, "prepare_draft")
builder.add_edge("prepare_draft", "review")
builder.add_edge("review", "generate")
builder.add_edge("generate", END)

if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in {"pause", "resume"}:
        raise SystemExit("usage: python approval.py [pause|resume] THREAD_ID")
    config = {"configurable": {"thread_id": sys.argv[2]}}
    with PostgresSaver.from_conn_string(os.environ["DATABASE_URL"]) as saver:
        saver.setup()  # Lab migration; production runs controlled migrations separately.
        graph = builder.compile(checkpointer=saver)
        if sys.argv[1] == "pause":
            paused = graph.invoke({}, config)
            assert "__interrupt__" in paused
            print("paused", graph.get_state(config).next)
        else:
            before = graph.get_state(config)
            assert before.next == ("review",), "thread is absent or no longer waiting for review"
            completed = graph.invoke(Command(resume={"approved": True, "reviewer_id": "editor-7"}), config)
            assert completed["artifact"] == "final:verified research draft"
            print("resumed", completed["artifact"])
