# Give local development and CI the same small command interface

Role: decision guide. Prerequisites: [testing setup](../testing/02_setup.md),
[configuration](../../fundamentals/core_concepts/runtime/configuration.md) and
[packaging](../../fundamentals/python_packaging/01_reproducible_builds.md).
Start with a documented bootstrap and a few commands that call the project's existing tools.
Add dev containers when OS/toolchain differences are a measured source of failures.

## Reproduce the environment, not a colleague's shell history

A new engineer starts document service tests with a different interpreter, an old schema and a
production-like `.env` copied from someone else. The first error may look like an application bug,
but three independent inputs differ. Record the supported interpreter, locked dependencies, local
service versions, migration step and synthetic seed data. Provide `.env.example` with harmless
names/defaults and no real credentials; fetch actual local credentials through the approved secret
workflow only when needed.

An explanatory Makefile excerpt gives commands stable names. The application is assumed to have
`app.main`, a test suite, Alembic configuration and installed development tools; this notes repository
is not that application:

```makefile
.PHONY: check test serve migrate
check:
	python -m ruff check .
	python -m mypy app

test:
	python -m pytest -m "not live"

serve:
	python -m uvicorn app.main:app --reload --host 127.0.0.1

migrate:
	python -m alembic upgrade head
```

Recipe indentation is a real tab. The wrapper does not implement validation itself: CI calls the
same underlying commands so a locally skipped hook cannot bypass release gates. Keep `migrate`
separate from every test run; an unexpected target database should not be mutated just because
someone wanted a unit test. The migration entry point needs an environment guard for a local-only
workflow and a separately authorized production path.

## Make seeds idempotent and obviously synthetic

Use a dedicated local database and deterministic tenant/document IDs. Running seed twice should
produce the same fixture rows rather than duplicate customers. Assert the database identity before
writing, and seed through constraints so fixture data cannot teach impossible states. Include a
small ordinary tenant, a tenant with no access and a boundary-size document. Never use a production
dump as a casual fixture source; it creates hidden data-access and retention obligations.

The local sequence should expose success at each boundary:

```mermaid
flowchart LR
    A[Create isolated environment] --> B[Install reviewed dependency lock]
    B --> C[Start disposable dependencies]
    C --> D[Apply migrations and synthetic seed]
    D --> E[Run unit and integration checks]
    E --> F[Serve on loopback and smoke test]
```

The integration test must prove a seeded document is visible only to its tenant. A listening port
alone does not prove the schema and access policy are correct. If imports fail only in CI, compare
interpreter and installed-artifact behavior; if integration tests fail after a branch switch,
inspect migration history and seed version before resetting data.

## Hooks and containers reduce friction but remain code execution

Use pre-commit for fast deterministic checks such as formatting, lint and secret scanning. Pin
reviewed hook revisions and run the same checks in CI; avoid putting paid provider evals or long
load tests in a commit hook. After installation, deliberately introduce a harmless formatting error
and verify the hook catches it; also test the CI command independently.
[pre-commit documentation](https://pre-commit.com/), checked 2026-10-30.

A dev container packages editor/tooling setup with the runtime environment. Prefer one when native
libraries, service dependencies or platform differences justify the startup/storage cost. Keep its
base image and features reviewed, scope mounts, and avoid mounting cloud credentials or the Docker
socket unless the task actually needs their authority. Container isolation does not make repository
setup scripts trustworthy. See the [Dev Container specification](https://github.com/devcontainers/spec/blob/main/docs/specs/devcontainerjson-reference.md).

Measure setup time from a clean clone, time to first passing test and recurring failure causes.
A healthy workflow produces a known test pass and a loopback smoke response without undocumented
manual steps. Before upgrading tools, trial the new lock/image in a disposable environment, run the
same commands and keep the previous working lock/image for rollback. Stop adding wrappers when
they hide errors or create another configuration language to maintain.

**Decision exercise:** local hooks pass, but CI fails because the wheel is missing a template file.
Would moving all development into containers necessarily fix it?

<details><summary>Answer</summary>

No. An editable install inside a container can still read an un-packaged source file. Test the built
wheel from outside the source tree. Containers address environment drift; artifact tests address
what the release actually contains.

</details>
