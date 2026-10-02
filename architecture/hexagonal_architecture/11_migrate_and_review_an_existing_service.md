# Migrate and Review an Existing Service Incrementally

> **Who this is for**: Engineers untangling an established FastAPI service, worker, consumer, or AI backend without mixing folder movement with business redesign.

A structure-only migration should preserve behavior while making ownership and dependency direction
visible. Start with one business action and its tests; do not begin by moving every file into a
canonical tree.

---

## 1. Inventory execution before proposing folders

For each candidate module, record:

| Question | Example answer |
|----------|----------------|
| Public entry point | `POST /tickets/{id}/classification` |
| Business action | Classify one eligible ticket |
| External effects | PostgreSQL, model call, SQS publication |
| Current inbound processes | FastAPI and bulk-import worker |
| Success/failure contract | Classified, human review, unavailable |
| Lifecycle resources | Engine, model HTTP client, consumer loop |
| Tests and prerequisites | Mixed route test requiring DB and model patches |

Trace imports in both directions. Inspect actual test execution, fixture scope, markers, hooks, CI
selectors, and deployment entry points; filenames alone do not reveal whether a test is unit or
integration.

> **Core:** establish the current behavior and ownership map before choosing the target directory
> map.

---

## 2. Classify findings by impact rather than taste

Use three labels:

- **Violation:** an inner package imports a concrete outer technology, provider failures cross a
  port, or business policy lives in transport code.
- **Improvement:** a split would materially clarify ownership, testing, lifecycle, or change
  isolation.
- **Preference:** naming or layout differs but dependency direction and ownership remain clear.

For example, naming the composition package `wiring/` instead of `bootstrap/` is usually a
preference in a generic review. For a service following this repository standard, however,
`bootstrap/` is the required composition owner. Generic hexagonal architecture permits other names; the agreed repository
contract fixes names so every reviewer knows where to look. A migration targets that contract.

---

## 3. Choose one vertical migration slice

For the coupled route from part 1, the smallest coherent sequence is:

```text
1. Characterize current HTTP behavior with tests
2. Extract typed ClassificationCandidate and stable failures
3. Extract classify_ticket with existing behavior unchanged
4. Put provider invocation behind TicketClassifier
5. Move SQLAlchemy queries to the persistence owner
6. Keep the route as input/output translation
7. Move concrete construction and disposal to bootstrap
8. Move existing worker callers to the public action
```

Move contract errors before application code would otherwise import concrete provider errors.
Move deterministic policy with its focused tests. Then move concrete integrations and composition.

Run the focused test slice after each meaningful step. Repository-wide movement followed by one
large test run makes regressions hard to locate and review.

---

## 4. Preserve behavior while changing dependency ownership

During a staged edit, a temporary import can keep callers working while their imports move. That
is a work-in-progress tool, not the completed internal architecture. For example, the old route
module may briefly import `classify_ticket` from its new application owner. Search all in-repository
callers, migrate their imports, and delete the forwarding module in the same repository change.
Otherwise the next engineer sees two public paths and must discover which one owns behavior.

A genuinely independent consumer may be unable to migrate atomically. A shared library can then
keep an additive supported API until a named removal condition is met, such as the final old
consumer being retired. That compatibility boundary differs from an internal-only shim: describe
who still needs it and verify both supported paths rather than treating every old import as a
reason for permanent forwarding.

Update more than Python imports: process commands, FastAPI app targets, worker entry points,
migrations, fixture paths, pytest markers, pre-commit filters, CI selectors, Docker commands,
telemetry service names, and documentation may all encode the old layout.

For example, a mixed route-test module has both fake-only policy checks and tests needing a real
database. Split those execution profiles before moving their owners. Keep assertions unchanged;
move the database fixture to the integration profile and importable support into a qualified
support package rather than importing `conftest.py`. Update selectors and run each supported
profile. Promoting the fixture to root scope would make previously isolated tests acquire
infrastructure, even if every test still passes. [Boundary testing](09_test_through_architectural_boundaries.md)
owns the detailed test placement and evidence.

---

## 5. Review the final dependency graph and test evidence

The highest-value final checks are:

```text
[ ] Every business operation, including one-call reads, has a public application action
[ ] Stateless actions are async functions with explicit keyword collaborators
[ ] Domain and ports import no framework, ORM, provider SDK, or bootstrap
[ ] Application imports no API, adapter, DB, GenAI, or concrete client
[ ] Each business API/worker entry point calls exactly one public action
[ ] Technical health/readiness/metrics/version endpoints call no business action
[ ] Workers own business input/settlement choices; inbox adapters own provider mechanics
[ ] Pure decisions are domain functions imported directly, never wrapped in Protocols
[ ] Concrete adapters translate success and failure at their boundary
[ ] Bootstrap constructs implementations once; runtime fields are collaborators, not bound actions
[ ] No forwarding layers remain except the public one-call catalog action
[ ] Behavior-changing AI concerns live below genai/; trace-only middleware belongs to observability/
[ ] No root messaging/, utils/, common/, or global error/constant bucket exists
[ ] Packages are flat until demonstrated pressure justifies nesting
[ ] Unit tests replace costly boundaries without patching SDK internals
[ ] Integration and E2E prerequisites are explicit and reproducible
[ ] All Python imports use the full absolute package path
[ ] Import-linter contracts enforce every canonical boundary in pre-commit and CI
[ ] Library independence and kind-specific importer contracts are enforced too
```

Import rules need executable contracts, not only this review list.
[Dependency direction](03_dependencies_point_toward_business_policy.md) explains enforcement;
[boundary testing](09_test_through_architectural_boundaries.md) separates static, semantic, and
behavioral evidence. A passing import contract cannot prove rollback or safe external retries.

**Success signal:** changing the classifier implementation modifies its adapter and bootstrap wiring
while application tests remain unchanged; adding a worker reuses the action without importing
FastAPI.

> **Key insight**: a successful migration is measured by smaller, one-way dependency edges and
> clearer test seams—not by how closely the final tree resembles a diagram.

---

## 6. Migration failures have recognizable symptoms

⚠️ If a “structure-only” pull request changes business outcomes, retry semantics, and data models,
reviewers cannot separate movement risk from redesign risk. Split the work.

⚠️ If tests pass only after broadening `pythonpath`, importing another service's test helpers, or
promoting expensive fixtures to root scope, the migration damaged test ownership.

Do not migrate a stable small service merely for symmetry with a larger neighbor. Apply the
architecture when it solves named ownership, change, lifecycle, or test-isolation problems.

> **Production:** import searches, focused suites, type checks, process startup checks, and CI
> profiles must prove internal consumers moved before completing the same change and deleting its
> shims. Independently deployed processes still require compatibility-safe rollout ordering.

---

## 7. The review can now answer operational questions

After migration, a cold reader should be able to answer:

- Where is each process constructed and shut down?
- Which action coordinates classification, and which pure domain function decides its policy?
- Which contract shields that action from model-provider behavior?
- Where are provider errors translated?
- Which test proves business handling without live infrastructure?
- Which integration test proves the concrete repository or broker?
- What fails readiness when construction is incomplete?
- Which module changes when HTTP, broker, database, or model details change?

If those answers still require tracing through generic services and utilities, the folder movement
did not establish meaningful ownership.

---

**Next**: [Part 12 — Trace One Investigation Across Services](12_trace_an_investigation_across_services.md), or return to the [Hexagonal Architecture index](README.md) for another reading path.
