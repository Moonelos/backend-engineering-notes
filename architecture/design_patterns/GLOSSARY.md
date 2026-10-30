# Pattern vocabulary

These definitions support lookup; the linked lessons teach the decisions and mechanisms.

| Term | Meaning and owner |
|---|---|
| Abstraction | [A contract that exposes the decision a caller needs while leaving implementation choices elsewhere.](01_choose_the_smallest_abstraction.md) |
| Seam | [An explicit point where behavior can be supplied without rewriting its caller.](01_choose_the_smallest_abstraction.md) |
| Behavioral contract | [The meaning and failure behavior implementations must preserve beyond their type signatures.](01_choose_the_smallest_abstraction.md) |
| Dependency injection | [Supplying a collaborator from outside the operation that uses it.](01_choose_the_smallest_abstraction.md) |
| Callable | [An object that can be invoked; a function or an object implementing __call__ can supply behavior.](01_choose_the_smallest_abstraction.md) |
| Protocol | [A structural typing contract describing supported operations; annotations alone do not enforce runtime behavior.](01_choose_the_smallest_abstraction.md) |
| Strategy | [An interchangeable behavior selected independently of the operation that uses it.](02_select_behavior_and_build_dependencies.md) |
| Simple factory | [A function or object that constructs a collaborator from explicit choices.](02_select_behavior_and_build_dependencies.md) |
| Factory Method | [An overridable creation method used by an inherited algorithm.](02_select_behavior_and_build_dependencies.md) |
| Abstract Factory | [A construction interface for a family of related products.](02_select_behavior_and_build_dependencies.md) |
| Registry | [An explicit mapping from a supported name to its implementation or constructor.](02_select_behavior_and_build_dependencies.md) |
| Composition root | [The process edge that constructs implementations, supplies dependencies and assigns lifetimes.](../hexagonal_architecture/06_compose_the_runtime_at_the_edge.md) |
| Adapter | [A translation from an available interface into the interface a caller expects.](03_adapt_translate_and_simplify.md) |
| Facade | [A simpler supported entry point over several subsystem operations.](03_adapt_translate_and_simplify.md) |
| Anti-Corruption Layer | [A semantic translation boundary that protects an internal model from another system's vocabulary and rules.](03_adapt_translate_and_simplify.md) |
| Command | [Data describing a requested operation that its owner may accept or reject.](04_commands_and_application_handlers.md) |
| Handler / application service | [The use-case boundary that interprets a request and coordinates its explicit collaborators.](04_commands_and_application_handlers.md) |
| Repository | [A domain-oriented collection/access contract hiding persistence details where that separation is useful.](../hexagonal_architecture/05_design_ports_and_adapter_contracts.md) |
| Unit of Work | [One transaction owner deciding whether related persistence operations commit or roll back.](../hexagonal_architecture/05_design_ports_and_adapter_contracts.md#6-a-unit-of-work-makes-several-repositories-one-transaction) |
| Decorator pattern | [A wrapper that preserves an operation's interface while adding behavior around it.](05_wrap_and_chain_behavior.md) |
| Chain of Responsibility | [A sequence of handlers that can handle, reject or forward a request according to an explicit stopping rule.](05_wrap_and_chain_behavior.md) |
| Predicate | [A function answering whether a value satisfies a condition.](06_model_rules_and_state.md) |
| Specification | [A named, reusable business predicate that can be combined with other predicates.](06_model_rules_and_state.md) |
| Guard | [A condition that must hold before an otherwise legal transition can occur.](06_model_rules_and_state.md) |
| State-machine trigger | [An input requesting a transition; often called an event in state-machine vocabulary, distinct from a published domain fact.](06_model_rules_and_state.md) |
| State pattern | [State-specific objects supply behavior selected by an object's current lifecycle state.](06_model_rules_and_state.md) |
| Builder | [An owner of staged, incomplete construction that produces a complete value at finalization.](07_construction_and_inheritance_tradeoffs.md) |
| Template Method | [A base-class method that fixes algorithm order while subclasses supply selected steps.](07_construction_and_inheritance_tradeoffs.md) |
| Singleton | [A construction/access pattern restricting instances through a shared access point; it does not coordinate separate processes.](07_construction_and_inheritance_tradeoffs.md) |
| Dispatcher | [Code that selects or invokes the handlers of a command or event under an explicit routing/failure policy.](../event_driven_architecture/02_local_events_and_dispatch.md) |
| Observer | [A notification relationship in which subscribers react when a subject announces a change.](../event_driven_architecture/02_local_events_and_dispatch.md) |
| Domain event | [A fact expressed in the domain's language; a durable published fact must correspond to committed state.](../event_driven_architecture/02_local_events_and_dispatch.md) |
| Invariant | [A condition accepted state must preserve when commands change it.](../event_driven_architecture/03_cqrs_read_and_write_models.md) |
| DTO | [A data-transfer representation tailored to an input or read boundary rather than owning domain mutations.](../event_driven_architecture/03_cqrs_read_and_write_models.md) |
| CQS | [Command-query separation distinguishes operations that change state from operations that return information.](../event_driven_architecture/03_cqrs_read_and_write_models.md) |
| CQRS | [Separate models/interfaces for changing state and reading it, without requiring separate databases.](../event_driven_architecture/03_cqrs_read_and_write_models.md) |

For outbox, idempotency, circuit breakers, deployment and other production terms, use the
[repository glossary](../../GLOSSARY.md).
