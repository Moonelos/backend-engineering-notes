# 07 — Fixture Patterns

> **Who this is for**: pytest users who can write a test and now need reusable setup with explicit
> lifetime and cleanup.

## A fixture owns one resource lifetime

```python
import pytest

@pytest.fixture
def opened_file(tmp_path):
    handle = (tmp_path / "result.txt").open("w+")
    try:
        yield handle
    finally:
        handle.close()

def test_write(opened_file):
    opened_file.write("ok")
    assert not opened_file.closed
```

The test passes while the handle is open; after the test, the fixture's `finally` closes it even on
failure. Scope changes how long that ownership lasts, not merely how often setup text runs.

> **Key insight**: A fixture is a lifetime owner with dependency ordering, not just a reusable value.

---

## `conftest.py` Hierarchy

pytest discovers `conftest.py` files at every directory level. Each file's fixtures are available to every test in that directory **and below**:

```
tests/
├── conftest.py              # shared across ALL tests
├── unit/
│   ├── conftest.py          # shared across unit tests only
│   ├── test_pricing.py
│   └── test_schemas.py
└── integration/
    ├── conftest.py          # shared across integration tests only
    ├── test_users.py
    └── test_orders.py
```

A child `conftest.py` can override a fixture defined in the parent by redeclaring it with the same name.

> **Do not import fixtures across modules.** `from tests.conftest import client` breaks pytest's discovery model. Put the fixture where it's needed (root `conftest.py`) and let pytest inject it.

---

## Essential Fixtures

The minimum `tests/conftest.py` for a FastAPI project:

```python
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
async def client():
    """Async test client — use for all endpoint tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    """Ensure no override leaks between tests."""
    previous = app.dependency_overrides.copy()
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
```

`autouse=True` makes the fixture run automatically for every test — no need to list it in each signature. See [05 — Dependency Overrides](05_dependency_overrides.md) for why this matters.

If the app uses `lifespan` startup/shutdown, include `asgi-lifespan` in the client fixture:

```python
from asgi_lifespan import LifespanManager


@pytest.fixture
async def client():
    async with LifespanManager(app) as manager:
        transport = ASGITransport(app=manager.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
```

---

## Scoped Fixtures

| Scope | Lifecycle | Use Case |
|-------|-----------|----------|
| `function` (default) | Per test | DB sessions, clients, request-scoped state |
| `class` | Per test class | Grouped related tests sharing setup |
| `module` | Per file | Schema creation/teardown, data seeding |
| `session` | Entire test run | Engine creation, test container startup |

```python
@pytest.fixture(scope="session")
def engine():
    """One engine for the entire test run."""
    eng = create_engine(TEST_DB_URL)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def tables(engine):
    """Create tables once per test module."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(engine, tables):
    """Fresh session per test, rolled back after."""
    conn = engine.connect()
    txn = conn.begin()
    session = Session(bind=conn)
    yield session
    session.close()
    txn.rollback()
    conn.close()
```

Fixture dependencies also determine reverse teardown order:

```mermaid
flowchart LR
    E[Engine setup] --> T[Tables setup] --> S[Connection and transaction] --> U[Test user rows]
    U --> C[Close session] --> R[Rollback transaction] --> D[Close connection]
    D --> X[Drop tables at owner scope] --> Z[Dispose engine]
```

The session cannot outlive its connection and the connection cannot outlive its engine. Register
cleanup before later setup can fail; `yield` teardown is reached only after the fixture successfully
yielded, so use context managers or immediate finalizers for multi-step acquisition failures.

### The Scope Trade-Off

Larger scope is faster but more coupled. A session-scoped `db_session` would be fast, but two tests running in it would see each other's writes. The convention is:

- **Expensive setup (engines, containers) → session scope.**
- **State that must reset per test (rows, overrides) → function scope, with rollback.**

See [08 — Database Testing](08_database_testing.md) for the DB-specific versions.

---

## Factory Fixtures

When you need multiple instances with different configurations, make the fixture return a **function**, not a value:

```python
@pytest.fixture
def make_user(db_session):
    """Factory fixture — create users with custom attributes."""
    created = []

    def _make_user(username=None, email=None, role="user"):
        n = len(created) + 1
        user = User(username=username or f"user_{n}",
                    email=email or f"user_{n}@example.com", role=role)
        db_session.add(user)
        db_session.flush()
        created.append(user)
        return user

    yield _make_user
    # cleanup happens via transaction rollback on db_session


async def test_admin_can_delete_user(client, make_user):
    admin = make_user(username="admin", role="admin")
    target = make_user(username="victim", role="user")

    response = await client.delete(
        f"/users/{target.id}",
        headers={"X-User-Id": str(admin.id)},
    )
    assert response.status_code == 200
```

Factory fixtures beat hard-coded ones:

- Each test requests exactly the shape it needs.
- Defaults cover the common case; overrides cover edge cases.
- No proliferation of `admin_user`, `normal_user`, `user_with_no_email`, etc.

For larger projects, `factory-boy` or `polyfactory` do this with less boilerplate — worth reaching for once you have ten-plus factories.

---

## Fixture for Authenticated Requests

Combine a factory fixture with `dependency_overrides` (see [05](05_dependency_overrides.md)) for role-based endpoint tests:

```python
@pytest.fixture
def as_user():
    """Install a fake current_user override with custom role."""
    def _as_user(user_id=1, role="user"):
        from app.dependencies import get_current_user
        app.dependency_overrides[get_current_user] = lambda: {
            "id": user_id,
            "role": role,
        }
    return _as_user


async def test_admin_endpoint(client, as_user):
    as_user(role="admin")
    response = await client.get("/admin/stats")
    assert response.status_code == 200


async def test_regular_user_rejected(client, as_user):
    as_user(role="user")
    response = await client.get("/admin/stats")
    assert response.status_code == 403
```

Cleanup is handled by the `reset_dependency_overrides` autouse fixture above.

---

## Yield vs Return

| Form | When |
|------|------|
| `return value` | Pure setup, nothing to clean up |
| `yield value` | Setup + teardown |

```python
# Return — simple factories, values
@pytest.fixture
def default_payload():
    return {"username": "alice", "email": "a@b.com"}


# Yield — anything that owns resources
@pytest.fixture
def tmp_db_file(tmp_path):
    path = tmp_path / "test.db"
    yield path
    # nothing explicit — tmp_path auto-cleans
```

The post-yield block runs **even if the test fails**, which is exactly what you want for cleanup.

---

## Parameterized Fixtures

When you want the same test to run under multiple configurations:

```python
@pytest.fixture(params=["sqlite", "postgres"])
def db_url(request):
    if request.param == "sqlite":
        return "sqlite:///./test.db"
    return "postgresql://user:pass@localhost/test"


def test_migrations_apply(db_url):
    # runs once per param — test IDs include the param name
    ...
```

Different from `@pytest.mark.parametrize` on the test itself: fixture parameterization fans out *all* tests that request the fixture, which is usually what you want for backend-switching tests.

---

## Built-In Fixtures Worth Knowing

| Fixture | Use |
|---------|-----|
| `tmp_path` | Unique temp directory per test, auto-cleaned |
| `monkeypatch` | Patch env vars, attributes, without leakage |
| `capsys` / `capfd` | Capture stdout/stderr |
| `caplog` | Assert on log messages |
| `request` | Introspect the test (name, params, fixtures) |

```python
def test_env_defaults(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    from app.config import load_settings
    settings = load_settings()
    assert settings.database_url == "sqlite://"
```

`monkeypatch` auto-reverses after the test. Never `os.environ["X"] = ...` in a test without cleanup — it leaks.

---

## Next

- [08 — Database Testing](08_database_testing.md) — put these fixture patterns to use with real (or fake) databases.

## Recap and retrieval

- Fixtures express acquisition dependencies and reverse teardown ownership.
- Expensive servers may be shared while rows and overrides reset per test.
- Factories must generate unique defaults when the schema enforces uniqueness.

**Two tests need different users and one expensive server. Which state can be shared?**

<details><summary>Reasoned answer</summary>

The server only if isolation is explicit; give identities, rows, overrides and transaction state function lifetime and restore surrounding state on failure.

</details>

**A factory creates admin and target with different usernames but the same default email. What fails?**

<details><summary>Reasoned answer</summary>

A unique-email constraint. Generate distinct email defaults, and specify duplicates explicitly only in tests intended to assert rejection.

</details>

**Try it:** Create three users without specifying emails, then create an intentional duplicate in a constraint test.

Hint: The factory counter supplies unique defaults; explicit arguments still win.

<details><summary>Worked solution</summary>

Use user_1@example.com through user_3@example.com by default. Pass a prior address explicitly for the duplicate test and assert the production constraint outcome.

</details>
