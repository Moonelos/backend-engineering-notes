import asyncio
import socket
import sqlite3
from pathlib import Path
import re

import httpcore
import jwt
import pytest
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from auth_app import UserRecord, create_app, encode_access
from auth_egress import BlockedDestination, PinnedBackend, validate_url
from auth_inbox import admit, initialize

SECRET = "local-test-only-" + "x" * 32


@pytest.fixture
def client():
    users = {"u1": UserRecord("u1", "one@example.test", "t1", PasswordHash.recommended().hash("fixture-passphrase"))}
    posts = {1: {"id": 1, "owner_id": "u1", "tenant_id": "t1", "title": "Own"},
             2: {"id": 2, "owner_id": "u2", "tenant_id": "t1", "title": "Other"}}
    with TestClient(create_app(SECRET, users, posts)) as client:
        yield client


def test_login_projection_and_path_guard(client):
    result = client.post("/login", json={"email": "one@example.test", "password": "fixture-passphrase"})
    assert result.status_code == 200
    headers = {"Authorization": "Bearer " + result.json()["access_token"]}
    assert client.get("/users/me", headers=headers).json() == {"id": "u1", "email": "one@example.test"}
    assert client.put("/posts/1", headers=headers, json={"title": "changed"}).status_code == 200
    assert client.put("/posts/2?resource_id=1", headers=headers, json={"title": "attack"}).status_code == 404
    assert client.post("/login", json={"email": "absent@example.test", "password": "wrong"}).status_code == 401


@pytest.mark.parametrize("change", ["no_exp", "refresh", "wrong_aud", "wrong_issuer", "expired"])
def test_invalid_token_profiles(client, change):
    claims = jwt.decode(encode_access(SECRET, "u1"), options={"verify_signature": False})
    if change == "no_exp":
        claims.pop("exp")
    elif change == "refresh":
        claims["type"] = "refresh"
    elif change == "wrong_aud":
        claims["aud"] = "https://another.example.com"
    elif change == "wrong_issuer":
        claims["iss"] = "https://untrusted.example.com"
    else:
        claims["exp"] = 1
    token = jwt.encode(claims, SECRET, algorithm="HS256")
    assert client.get("/users/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_inactive_user_and_exact_bcrypt_boundary():
    user = UserRecord("u1", "inactive@example.test", "t1", PasswordHash.recommended().hash("fixture-password"), False)
    with TestClient(create_app(SECRET, {"u1": user}, {})) as client:
        assert client.post("/login", json={"email": user.email, "password": "fixture-password"}).status_code == 401
        token = encode_access(SECRET, "u1")
        assert client.get("/users/me", headers={"Authorization": "Bearer " + token}).status_code == 401
    note = Path(__file__).parents[1] / "04_authentication.md"
    fence = next(block for block in re.findall(r"```python\n(.*?)\n```", note.read_text(), re.S)
                 if block.startswith("import bcrypt"))
    namespace = {}
    exec(compile(fence, str(note), "exec"), namespace)
    hashed = namespace["hash_password"]("x" * 72)
    assert namespace["verify_password"]("x" * 72, hashed)
    assert not namespace["verify_password"]("x" * 73, hashed)
    with pytest.raises(ValueError):
        namespace["hash_password"]("é" * 37)


def test_dns_pins_first_checked_numeric_address_and_rejects_private_answer():
    seen = []

    async def resolver(host, port):
        seen.append((host, port))
        ip = "8.8.8.8" if len(seen) == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    class Backend:
        async def connect_tcp(self, host, port, **kwargs):
            assert host == "8.8.8.8"  # original hostname cannot be resolved again
            return "stream"

    async def scenario():
        backend = PinnedBackend({"provider.example"}, resolver=resolver, backend=Backend())
        assert await backend.connect_tcp("provider.example", 443, timeout=1) == "stream"
        assert len(seen) == 1
        with pytest.raises(BlockedDestination):
            await backend.connect_tcp("provider.example", 443, timeout=1)
    asyncio.run(scenario())
    for url in ["https://user@provider.example/x", "https://provider.example:8443", "https://127.0.0.1/x"]:
        with pytest.raises(BlockedDestination):
            validate_url(url, {"provider.example"})


def test_inbox_crash_and_restart(tmp_path):
    path = tmp_path / "inbox.sqlite"
    initialize(path)

    def crash():
        raise RuntimeError("crash before commit")

    with pytest.raises(RuntimeError):
        admit(path, "acme:tenant1", "e1", b'{"id":"e1"}', before_commit=crash)
    assert admit(path, "acme:tenant1", "e1", b'{"id":"e1"}')
    assert not admit(path, "acme:tenant1", "e1", b'{"id":"e1"}')
    with pytest.raises(ValueError):
        admit(path, "acme:tenant1", "e1", b'{"id":"e1","other":true}')
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT state FROM inbox").fetchall() == [("pending",)]


def test_httpcore_keeps_original_tls_hostname():
    seen = []

    class Stream(httpcore.AsyncMockStream):
        async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
            seen.append(server_hostname)
            assert ssl_context.check_hostname
            return self

    class Backend:
        async def connect_tcp(self, host, port, **kwargs):
            assert host == "8.8.8.8"
            return Stream([b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"])

    async def resolve(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]

    async def scenario():
        pinned = PinnedBackend({"provider.example"}, resolver=resolve, backend=Backend())
        async with httpcore.AsyncConnectionPool(network_backend=pinned) as pool:
            response = await pool.request("GET", "https://provider.example/data")
            assert response.content == b"OK"
    asyncio.run(scenario())
    assert seen == ["provider.example"]


def test_exact_published_action_query(tmp_path):
    from sqlalchemy import String
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
    from auth_ticket_service import Principal as LabPrincipal

    class Base(DeclarativeBase):
        pass

    class Ticket(Base):
        __tablename__ = "tickets"
        id: Mapped[str] = mapped_column(String, primary_key=True)
        tenant_id: Mapped[str]
        owner_id: Mapped[str]

    class Principal(LabPrincipal):
        def has(self, capability):
            return capability in self.capabilities

    note = Path(__file__).parents[1] / "11_api_security.md"
    fence = next(block for block in re.findall(r"```python\n(.*?)\n```", note.read_text(), re.S)
                 if "async def get_ticket_for_action(" in block)
    namespace = {"Ticket": Ticket, "Principal": Principal}
    exec(compile(fence, str(note), "exec"), namespace)

    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite://")
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with async_sessionmaker(engine)() as session:
                session.add(Ticket(id="42", tenant_id="acme", owner_id="alice"))
                await session.commit()
                bob = Principal("bob", "acme", frozenset({"ticket:read", "ticket:read:any", "ticket:write"}))
                load = namespace["get_ticket_for_action"]
                assert await load(session, ticket_id="42", principal=bob, action="read") is not None
                assert await load(session, ticket_id="42", principal=bob, action="write") is None
                outsider = Principal("alice", "other", frozenset({"ticket:write", "ticket:write:any"}))
                assert await load(session, ticket_id="42", principal=outsider, action="write") is None
        finally:
            await engine.dispose()
    asyncio.run(scenario())


def test_ticket_policy_budget_and_atomic_audit(tmp_path):
    from auth_ticket_service import Principal, create_app as ticket_app, initialize as init_tickets
    path = tmp_path / "tickets.sqlite"
    init_tickets(path)
    principal = Principal("bob", "acme", frozenset({"ticket:read", "ticket:read:any", "ticket:write"}))
    app = ticket_app(path, lambda: principal)
    with TestClient(app) as client:
        assert client.get("/tickets/42").status_code == 200
        assert client.patch("/tickets/42", json={"title": "blocked"}).status_code == 404
        principal = Principal("alice", "other", frozenset({"ticket:write", "ticket:write:any"}))
        assert client.patch("/tickets/42", json={"title": "blocked"}).status_code == 404
        principal = Principal("alice", "acme", frozenset({"ticket:write"}))
        assert client.patch("/tickets/42", json={"title": "updated", "owner": "bob"}).status_code == 422
        assert client.patch("/tickets/42", json={"title": "updated"}).status_code == 200
        principal = Principal("alice", "acme", frozenset())
        assert client.patch("/tickets/42", json={"title": "revoked"}).status_code == 403

    def crash():
        raise RuntimeError("injected crash")

    principal = Principal("alice", "acme", frozenset({"ticket:write"}))
    with TestClient(ticket_app(path, lambda: principal, before_commit=crash), raise_server_exceptions=False) as client:
        assert client.patch("/tickets/42", json={"title": "rolled back"}).status_code == 500
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT title FROM tickets").fetchone()[0] == "updated"
        assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 1
    with TestClient(ticket_app(path, lambda: principal, after_commit=crash), raise_server_exceptions=False) as client:
        assert client.patch("/tickets/42", json={"title": "committed"}).status_code == 500
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT title FROM tickets").fetchone()[0] == "committed"
        assert db.execute("SELECT count(*) FROM outbox WHERE state='pending'").fetchone()[0] == 2
    with TestClient(app) as client:
        assert client.patch("/tickets/42", json={"title": "over budget"}).status_code == 429


def test_exact_expiry_advice_uses_full_access_profile(monkeypatch):
    note = Path(__file__).parents[1] / "04_authentication.md"
    source = note.read_text()
    fences = re.findall(r"```python\n(.*?)\n```", source, re.S)
    helper = next(block for block in fences if "def decode_access_token" in block)
    advice = re.search(r"### Not Validating Token Expiry.*?```python\n(.*?)\n```",
                       source, re.S).group(1)
    monkeypatch.setenv("SECRET_KEY", SECRET)
    namespace = {}
    exec(compile(helper, str(note), "exec"), namespace)
    valid = namespace["create_access_token"]({"sub": "u1"})
    namespace["token"] = valid
    exec(compile(advice, str(note), "exec"), namespace)
    assert namespace["payload"]["type"] == "access"
    claims = jwt.decode(valid, options={"verify_signature": False})
    for mutation in [dict(claims, type="refresh"), {k: v for k, v in claims.items() if k != "exp"}]:
        namespace["token"] = jwt.encode(mutation, SECRET, algorithm="HS256")
        with pytest.raises(jwt.PyJWTError):
            exec(compile(advice, str(note), "exec"), namespace)


def test_exact_combined_auth_rejects_failed_api_key_lookup():
    from fastapi import Depends, Security, HTTPException, status
    note = Path(__file__).parents[1] / "04_authentication.md"
    fence = next(block for block in re.findall(r"```python\n(.*?)\n```", note.read_text(), re.S)
                 if "def get_current_user_or_client" in block)
    class User:
        pass
    class APIClient:
        pass
    principal = APIClient()
    namespace = {"Depends": Depends, "Security": Security, "HTTPException": HTTPException,
                 "status": status, "User": User, "APIClient": APIClient,
                 "lookup_client_by_key": lambda key: principal if key == "known" else None,
                 "decode_and_get_user": lambda token: None}
    exec(compile(fence, str(note), "exec"), namespace)
    authenticate = namespace["get_current_user_or_client"]
    for token, key in [(None, "invalid"), (None, None), ("invalid-token", "known")]:
        with pytest.raises(HTTPException) as error:
            authenticate(token=token, api_key=key)
        assert error.value.status_code == 401
    assert authenticate(token=None, api_key="known") is principal
