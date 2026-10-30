# 02 — Setup

> **Who this is for**: Python backend engineers creating a pytest suite from an empty `tests/`
> directory.

## Quick proof: one test is discovered and passes

After `pip install pytest`, save this as `tests/test_setup.py`:

```python
def test_pytest_is_running():
    assert 2 + 2 == 4
```

Run `pytest -q tests/test_setup.py`. The success signal is `1 passed`; `collected 0 items` means the
file or function naming convention is wrong. The rest of this note adds async support, layout,
markers, and the commands useful once the baseline works.

> **Key insight**: A test toolchain is installed only when discovery, execution, and exit status all
> work in the same environment that will run CI.

---

## Install Dependencies

```bash
pip install pytest pytest-asyncio httpx respx
```

Common additions, covered in later files:

```bash
pip install asgi-lifespan       # async lifespan startup/shutdown — see 04_endpoint_testing.md
pip install pytest-cov          # coverage — see 11_coverage_and_ci.md
pip install pytest-xdist        # parallel test runs — see 11_coverage_and_ci.md
pip install pytest-repeat pytest-randomly  # flake detection — see 11_coverage_and_ci.md
pip install hypothesis          # property-based testing — see 03_unit_testing.md
pip install syrupy              # snapshot testing — see 10_test_patterns.md
pip install testcontainers      # real-DB testing — see 08_database_testing.md
pip install moto                # AWS mocking — see 09_mocking_external.md
```

---

## Version the test stack and its migration checks

The async examples here use HTTPX 0.28.1 APIs. Resolve FastAPI, Starlette, HTTPX and test plugins
as one lock, then record their versions with `python -m pip freeze`; the first installation command
is dependency intent, not a reproducible lock. New Starlette supports HTTPX2 and deprecates its
plain-HTTPX TestClient backend. A migration should verify lifespan, cookies, transport mocks and
stream cancellation before changing imports throughout the suite. Keep the old imports only in
a deliberately pinned compatibility profile. [Starlette TestClient](https://starlette.dev/testclient/)
and [release notes](https://starlette.dev/release-notes/), checked 2026-10-30.

**GA — pytest 9:** Native TOML is an alternative to `ini_options`; do not combine two competing
configuration files. The equivalent core selection in `pytest.toml` is:

```toml
[pytest]
minversion = "9.0"
testpaths = ["tests"]
addopts = ["--strict-markers", "-m", "not integration and not e2e and not live"]
markers = ["integration: disposable real infrastructure", "e2e: deployed boundary", "live: external provider"]
```

In `pyproject.toml`, use `[tool.pytest]` for native TOML on pytest 9, or retain the supported
`[tool.pytest.ini_options]` form below for compatibility. Check the selected config path printed
by pytest and use `--collect-only` to verify the same test profile after migration.
[pytest configuration](https://docs.pytest.org/en/stable/reference/customize.html), checked 2026-10-30.

## Project Structure

```
project/
├── app/
│   ├── main.py
│   ├── models.py
│   ├── schemas.py
│   ├── services.py
│   ├── dependencies.py
│   └── routers/
│       └── users.py
├── tests/
│   ├── conftest.py          # shared fixtures — see 07_fixtures.md
│   ├── unit/                # fast, no I/O — see 03_unit_testing.md
│   │   ├── test_services.py
│   │   └── test_schemas.py
│   ├── integration/         # ASGI stack + DB — see 04/08
│   │   ├── test_users.py
│   │   └── test_auth.py
└── pyproject.toml
```

Separating `unit/` from `integration/` lets you run the fast suite on every save and the slow suite on every push:

```bash
pytest tests/unit              # < 1s feedback loop
pytest -m integration tests/integration  # real disposable boundaries
pytest                         # everything
```

---

## `pyproject.toml` Configuration

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"          # no @pytest.mark.asyncio on every test
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
addopts = [
    "--strict-markers",
    "-m", "not integration and not e2e and not live",
]

# fail fast on unexpected warnings
filterwarnings = [
    "error",
    "ignore::DeprecationWarning:some_noisy_dep.*",
]

# markers — declare them to avoid "unknown marker" warnings
markers = [
    "integration: uses disposable real infrastructure",
    "e2e: starts or calls the deployable system",
    "live: calls a shared or paid external provider",
    "llm_eval: runs a nondeterministic dataset evaluation",
    "slow: unusually expensive within its proof profile",
]
```

> Setting `asyncio_mode = "auto"` treats every `async def test_*` as an async test automatically. Without it, the default `"strict"` mode requires `@pytest.mark.asyncio` on each one. See [06 — Async Testing](06_async_testing.md) for the trade-offs.

---

## Running Tests

Start with three commands: `pytest` for the hermetic default suite, `pytest -x` for a short feedback
loop, and `pytest path/to/test.py::test_name` while working on one failure. Select every broader
profile explicitly so its prerequisites and failures remain visible.

```bash
pytest                              # hermetic default profile
pytest -v                           # hermetic profile, one line per test
pytest -x                           # stop at first failure
pytest -k "user and not slow"       # select by name
pytest -m "not integration and not e2e and not live"  # explicit hermetic profile
pytest -m integration               # disposable DB/broker/service emulator profile
pytest -m e2e                       # deployed-process profile
pytest -m live                      # shared/provider profile; credentials required
pytest tests/unit/test_services.py::test_discount  # single test
pytest --lf                         # last failed only
pytest --ff                         # failed first, then the rest
```

Markers describe execution cost or prerequisites, not business packages. An `orders` test can be a
unit, integration, or E2E test; `@pytest.mark.orders` would not tell CI which environment it needs.
A selected infrastructure or live job must fail when its prerequisite is missing—an all-skipped
green job proves nothing.

---

## Sanity-Check Your Setup

Save this as `tests/test_setup.py` — if it fails, nothing else will work:

```python
import pytest


def test_sync_works():
    assert 1 + 1 == 2


async def test_async_works():
    """Requires asyncio_mode = 'auto' in pyproject.toml."""
    assert 1 + 1 == 2


def test_fixtures_work(tmp_path):
    """tmp_path is a pytest built-in — if it works, plugins are loaded."""
    (tmp_path / "x").write_text("hello")
    assert (tmp_path / "x").read_text() == "hello"
```

Run `pytest tests/test_setup.py -v`. If the async test fails with `PytestUnhandledCoroutineWarning`, your `asyncio_mode` is wrong.

---

## Next

- [03 — Unit Testing](03_unit_testing.md) — test pure logic without spinning up FastAPI.

## Recap and retrieval

- Discovery, execution and the process exit code all belong to the test-toolchain contract.
- Marker defaults select a hermetic profile; an explicit -m expression replaces that selection.
- Only the intentionally selected live job receives credentials and bounded prerequisites.

**A test has live and integration markers. Does pytest -m live retain the default exclusions?**

<details><summary>Reasoned answer</summary>

No. The command-line expression replaces the configured -m expression. This is intentional opt-in; verify the collected list before supplying credentials.

</details>

**The command exits successfully but collects zero tests. Was the feature verified?**

<details><summary>Reasoned answer</summary>

No. Check naming, testpaths and marker selection; an empty suite has no behavioral evidence.

</details>

**Try it:** Add a live-marked dummy test without any network calls and compare collection under the default profile and -m live.

Hint: Use pytest --collect-only -q; do not provide credentials for a collection test.

<details><summary>Worked solution</summary>

Default collection excludes live; the explicit -m live selects it and replaces the default expression. Preserve combined exclusions when selecting any other profile.

</details>
