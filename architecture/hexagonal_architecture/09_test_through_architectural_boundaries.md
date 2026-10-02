# Test Through Architectural Boundaries

> **Who this is for**: Engineers who want tests to prove dependency isolation instead of mirroring implementation details.

The fastest evidence that an application boundary works is a business test with small port fakes.
The strongest evidence that the complete service works comes later from adapter integration and
end-to-end tests. One test type cannot replace the other.

---

## 1. Test application decisions without infrastructure

This excerpt uses the confidence-bearing contract extension described in
[GenAI](08_treat_genai_as_an_external_capability.md), rather than the baseline string result.
The action receives a candidate and calls a pure domain confidence decision. Helpers and
test setup are omitted; this is a seam illustration, not a standalone runnable test.

```python
class StubClassifier:
    def __init__(self, candidate: ClassificationCandidate) -> None:
        self.candidate = candidate

    async def classify(self, body: str) -> ClassificationCandidate:
        return self.candidate


async def test_low_confidence_requires_human_review():
    tickets = InMemoryTickets([open_ticket("T-100")])
    classifier = StubClassifier(
        ClassificationCandidate(category="billing", confidence=0.61)
    )

    result = await classify_ticket(ticket_id="T-100", tickets=tickets, classifier=classifier)

    assert result.outcome is Outcome.HUMAN_REVIEW
```

Direct domain tests pass confidence and policy values to the pure decision and assert its result.
This action test proves that orchestration applies that decision and returns or persists its outcome;
it need not repeat every confidence branch already owned by the domain tests. The policy remains a
pure imported function, not another mocked Protocol. It does not patch a model SDK, SQLAlchemy
session, FastAPI dependency, or AWS client because none of those owns the rule.

> **Core:** application tests replace external effects at port or repository boundaries; adapter
> tests replace or provision the adapter's direct technology collaborator.

---

## 2. Classify tests by what they execute

Once a suite has more than one execution profile, use profile first and behavioral owner second:

```text
tests/
├── unit/
│   ├── application/
│   ├── domain/
│   ├── api/
│   ├── workers/
│   ├── adapters/
│   ├── genai/
│   └── bootstrap/
├── integration/
│   ├── db/
│   └── adapters/
├── contract/
│   ├── architecture/
│   ├── config/
│   └── deployment/
└── e2e/
```

A concrete SQS adapter tested with an injected fake AWS client is still a unit test. The same
adapter against a disposable emulator is integration. A FastAPI route exercised in-process with
outer ports replaced is a unit test of transport translation, not an end-to-end test.

The [testing notes](../../operations/testing/README.md) own general pytest mechanics. This chapter
owns how test seams demonstrate the architectural dependency graph.

The [investigation case study's evidence map](12_trace_an_investigation_across_services.md#7-tests-turn-the-source-tour-into-evidence)
connects existing sample tests to acceptance, checkpointed retry, and delivery behavior. Pay
attention to fake semantics: an in-memory Unit of Work with a no-op commit can prove action
sequencing while proving nothing about database rollback. Use real transaction tests for that
claim rather than making the fake look like an ORM.

---

## 3. Adapter tests prove translation in both directions

For an LLM classifier, test provider output to port output and provider failure to port failure:

```python
async def test_timeout_becomes_stable_unavailable_error():
    model = FakeModel(raises=ProviderTimeout("upstream timed out"))
    classifier = LLMTicketClassifier(model=model)

    with pytest.raises(ClassificationUnavailable):
        await classifier.classify("invoice is wrong")
```

For an API route, test request fields and application outcomes against status and response fields.
For a consumer worker, test typed business outcome to `Ack` or `Retry(delay)` mapping.
For its inbox adapter, test raw-envelope validation, dead-lettering malformed messages, visibility
heartbeat, and applying settlements through the fake broker client. These are different owners.

Changing one input should change one observable decision. If the test asserts private method calls
without checking translation, it locks down implementation while leaving the boundary unproved.

---

## 4. Bootstrap tests prove selection and disposal

Construction has different failure modes from business execution. Inject constructors or factories
and verify:

```text
settings select "rules"
  → RulesTicketClassifier constructed
  → runtime.classifier exposes that instance to explicit action calls
  → shutdown disposes the shared engine exactly once
```

Do not prove classification policy again through bootstrap. Its contract is selection, dependency
closure, startup order, readiness, and disposal.

Integration tests own disposable databases, brokers, filesystems, or local protocol endpoints.
They require bounded timeouts and deterministic cleanup. A destructive database reset must refuse
an ordinary service database URL.

---

## 5. E2E tests close the gap without swallowing the suite

An end-to-end (E2E) test starts the deployable or crosses several real boundaries:

```text
POST /tickets/T-100/classification
  → application action
  → disposable PostgreSQL
  → fake local classifier endpoint
  → persisted result
  → 200 response
```

Use a fake local external endpoint when the claim is service composition rather than provider
availability. A paid or shared staging model call is a separate opt-in **live test**, with bounded
inputs, cost, credentials, and an explicit CI selector.

> **Key insight**: test folders should reveal both the execution cost and the behavior owner; the
> ability to test business decisions with tiny fakes is evidence that dependencies point inward.

---

## 6. Failure symptoms show where seams are wrong

⚠️ If application tests patch `boto3`, model SDK internals, or SQLAlchemy calls several modules
away, the application boundary is leaking concrete ownership.

⚠️ If an integration CI job passes because every intended test skipped when infrastructure was
missing, the profile has no trustworthy success signal. Selected jobs must fail fast on absent
prerequisites.

**Success signal:** the ordinary unit suite runs without network, provider credentials, live
wall-clock sleeps, or external processes. Each integration and E2E profile also has a direct,
reproducible command and provisions its prerequisites explicitly.

Do not introduce profile directories for four deterministic library tests. Keep a small suite flat
until a second execution environment makes the distinction real. Do not mirror every source folder
automatically; add an owner directory only when navigation, fixture scope, or naming pressure
justifies it.

> **Production:** align pytest markers, strict marker registration, fixture scope, local commands,
> pre-commit or pre-push selection, and CI jobs. Folder names alone do not prevent expensive tests
> from running accidentally.

## 7. Make forbidden imports fail before they merge

Port fakes prove behavior under chosen inputs. They do not stop tomorrow's action from importing a
concrete database implementation. Import-linter checks the static dependency graph, including
indirect import chains. A `forbidden` contract names source boundaries and boundaries they cannot
import; it does not inspect whether a function contains correct business policy.

Run the following isolated demonstration with Python 3.11+ and `uv` installed. Save the whole block
as `check_boundaries.py` and run `python check_boundaries.py`. It installs pinned Import-linter 2.7
in uv's isolated tool environment, writes only a temporary package, and needs no database or credentials.

```python
import os
from pathlib import Path
import subprocess
import tempfile


CONTRACT = """[importlinter]
root_package = demo

[importlinter:contract:application]
name = Application points inward
type = forbidden
source_modules = *.application
forbidden_modules =
    *.api
    *.workers
    *.bootstrap
    *.config
    *.db
    *.adapters
    *.genai

[importlinter:contract:domain]
name = Domain is pure
type = forbidden
source_modules = *.domain
forbidden_modules =
    *.application
    *.ports
    *.api
    *.workers
    *.bootstrap
    *.config
    *.db
    *.adapters
    *.genai
    *.observability

[importlinter:contract:ports]
name = Ports expose contracts
type = forbidden
source_modules = *.ports
forbidden_modules =
    *.application
    *.api
    *.workers
    *.bootstrap
    *.config
    *.db
    *.adapters
    *.genai
    *.observability

[importlinter:contract:entries]
name = Entry points use runtime views
type = forbidden
source_modules =
    *.api
    *.workers
forbidden_modules =
    *.bootstrap
    *.config
    *.db
    *.adapters
    *.genai

[importlinter:contract:composition]
name = Implementations do not import composition
type = forbidden
source_modules =
    *.db
    *.adapters
    *.genai
    *.config
    *.observability
forbidden_modules = *.bootstrap

[importlinter:contract:db]
name = Persistence uses inward contracts
type = forbidden
source_modules = *.db
forbidden_modules =
    *.api
    *.workers
    *.adapters
    *.genai

[importlinter:contract:adapters]
name = Adapters use inward contracts
type = forbidden
source_modules = *.adapters
forbidden_modules =
    *.api
    *.workers
    *.db
    *.genai
ignore_imports = demo.adapters.sqs_inbox -> demo.workers.inbox
unmatched_ignore_imports_alerting = none

[importlinter:contract:genai]
name = GenAI uses inward contracts
type = forbidden
source_modules = *.genai
forbidden_modules =
    *.api
    *.workers
    *.db
    *.adapters
"""

with tempfile.TemporaryDirectory(prefix="hexagonal-imports-") as directory:
    root = Path(directory)
    package = root / "demo"
    package.mkdir()
    (package / "__init__.py").write_text("")
    for boundary in ("application", "domain", "ports", "db"):
        folder = package / boundary
        folder.mkdir()
        (folder / "__init__.py").write_text("")
    (root / ".importlinter").write_text(CONTRACT)
    environment = dict(os.environ, PYTHONPATH=str(root))

    def check(expected: int) -> str:
        result = subprocess.run(
            ["uv", "run", "--no-project", "--with", "import-linter==2.7",
             "lint-imports", "--no-cache"],
            cwd=root, env=environment, capture_output=True, text=True, timeout=120,
        )
        assert result.returncode == expected, result.stdout + result.stderr
        return result.stdout

    assert "Contracts: 8 kept, 0 broken" in check(0)
    print("clean boundaries: 8 contracts kept")
    action = package / "application" / "classify.py"
    action.write_text("from demo import db\n")
    assert "demo.application.classify -> demo.db" in check(1)
    print("outward database import: rejected")
    (package / "genai").mkdir()
    (package / "genai" / "__init__.py").write_text("")
    action.write_text("from demo import genai\n")
    assert "demo.application.classify -> demo.genai" in check(1)
    print("new GenAI boundary: already protected")
```

Expected output:

```text
clean boundaries: 8 contracts kept
outward database import: rejected
new GenAI boundary: already protected
```

The graph starts without `api/`, `workers/`, `bootstrap/`, `config/`, `adapters/`, or `genai/`.
Because the configuration analyzes one root package, `*.genai` selects that root's GenAI boundary
if it exists and matches nothing before it exists. Creating it later activates the existing rule;
there is no reason to scaffold empty folders. These are whole-module wildcards: `demo.genai*` is
invalid, and `demo.**.genai` does not select the immediate `demo.genai` module. Package descendants
are covered by default. The final assertion demonstrates a previously absent boundary becoming
protected. See the pinned [contract and wildcard documentation](https://import-linter.readthedocs.io/en/v2.7/contract_types.html)
for the semantics used here.

For a real service, copy the `CONTRACT` contents into `.importlinter`, change `root_package` to the
actual import package, update the exact inbox exception to the actual module names, and keep the
contract's scope to that member. The sole adapter-to-worker exception is the inbox contract module;
it does not permit an SQS implementation to import consumer actions or worker loops. GenAI tool
modules may import the one action they invoke and its port types, which these rules allow; they
still cannot access concrete DB/adapters. Unmatched inbox exceptions are tolerated only so absent
features do not force empty packages; review every new ignore rule as an ownership decision. Run with its source importable,
for example `PYTHONPATH=src uv run --no-project --with import-linter==2.7 lint-imports`. The mandatory
pre-commit hook runs that same check:

```yaml
# .pre-commit-config.yaml — excerpt for a single src-layout service
repos:
  - repo: local
    hooks:
      - id: architecture
        name: architecture import contracts
        entry: env PYTHONPATH=src uv run --no-project --with import-linter==2.7 lint-imports
        language: system
        pass_filenames: false
        always_run: true
```

CI runs the same hooks; a developer's optional local installation cannot be the only enforcement.
Create this job even when the service has no existing CI:

```yaml
# .github/workflows/checks.yml — complete minimal job, alongside existing jobs
name: checks
on: [push, pull_request]
jobs:
  pre-commit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: python -m pip install uv==0.12.13 pre-commit==4.3.0
      - run: pre-commit run --all-files
```

The hook assumes `uv` is installed, as CI explicitly ensures; its isolated pinned tool version keeps
local and CI contract behavior aligned. In a workspace, run per-member contracts from each member's
working directory rather than extending `PYTHONPATH` with every service. Pure `domain/` and `ports/`
add their dependency allowlist checks: standard library and declared type/model libraries only;
forbid concrete installed SDK roots with `include_external_packages = True` when present. The
example demonstrates internal graph enforcement, not automatic detection of every possible I/O
library or every ownership rule. A new SDK dependency requires reviewing that allowlist.

The demonstration deliberately has no cross-integration private Protocol. When a real feature
introduces one, add an exact `ignore_imports` exemption for its implementation importing the
consumer-owned contract, as with the inbox exception. For example, a database evidence index may
implement a Protocol in its GenAI retriever module. Keep the rest of the outer-boundary contract
closed: this exception permits the contract, not a sibling concrete implementation.

Static checks cannot prove that every business operation has a catalog action, a helper is a useless
forwarding layer, an action checks authorization, a transaction rolls back, or a broker delivery is
idempotent. Review establishes semantic ownership; behavior tests establish failure and concurrency
guarantees. Keep all three forms of evidence. Replacing an invalid import with dynamic lookup just
hides it from this static graph; it does not satisfy the architecture rule.

---

**Next**: [Part 10 — Grow Without Package Ceremony](10_grow_without_package_ceremony.md)
