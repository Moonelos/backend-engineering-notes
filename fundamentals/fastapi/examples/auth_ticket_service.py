"""Local ticket policy/transaction lab. The principal resolver is an injected trust boundary."""
import json
import sqlite3
import uuid
from dataclasses import dataclass

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class Principal:
    id: str
    tenant_id: str
    capabilities: frozenset[str]


class Patch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)


def initialize(path):
    with sqlite3.connect(path) as db:
        db.executescript(
            "CREATE TABLE tickets(id TEXT PRIMARY KEY, tenant TEXT, owner TEXT, title TEXT);"
            "CREATE TABLE budgets(tenant TEXT PRIMARY KEY, remaining INTEGER);"
            "CREATE TABLE outbox(id TEXT PRIMARY KEY, body TEXT, state TEXT);"
            "INSERT INTO tickets VALUES ('42', 'acme', 'alice', 'original');"
            "INSERT INTO budgets VALUES ('acme', 2);"
        )


def load(db, ticket_id, principal, action):
    if f"ticket:{action}" not in principal.capabilities:
        raise HTTPException(403, "Insufficient permissions")
    query = "SELECT id, title FROM tickets WHERE id=? AND tenant=?"
    parameters = [ticket_id, principal.tenant_id]
    if f"ticket:{action}:any" not in principal.capabilities:
        query += " AND owner=?"
        parameters.append(principal.id)
    row = db.execute(query, parameters).fetchone()
    if row is None:
        raise HTTPException(404, "Ticket not found")
    return {"id": row[0], "title": row[1]}


def create_app(path, resolve_principal, *, before_commit=lambda: None, after_commit=lambda: None):
    app = FastAPI()

    @app.get("/tickets/{ticket_id}")
    def read(ticket_id: str, principal: Principal = Depends(resolve_principal)):
        with sqlite3.connect(path) as db:
            return load(db, ticket_id, principal, "read")

    @app.patch("/tickets/{ticket_id}")
    def patch(ticket_id: str, body: Patch, principal: Principal = Depends(resolve_principal)):
        with sqlite3.connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            ticket = load(db, ticket_id, principal, "write")
            changed = db.execute("UPDATE budgets SET remaining=remaining-1 "
                                 "WHERE tenant=? AND remaining>0", (principal.tenant_id,)).rowcount
            if changed != 1:
                raise HTTPException(429, "Mutation budget exhausted")
            db.execute("UPDATE tickets SET title=? WHERE id=? AND tenant=?",
                       (body.title, ticket_id, principal.tenant_id))
            event = {"event_id": str(uuid.uuid4()), "actor": principal.id,
                     "tenant": principal.tenant_id, "ticket_id": ticket_id, "action": "ticket:write"}
            db.execute("INSERT INTO outbox VALUES (?, ?, 'pending')",
                       (event["event_id"], json.dumps(event)))
            before_commit()
        after_commit()
        return {**ticket, "title": body.title}

    return app
