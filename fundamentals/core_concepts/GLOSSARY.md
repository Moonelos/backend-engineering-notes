# Python concepts glossary

Use this as a lookup aid after the [learning map](README.md). Each link leads to the lesson
that develops the concept with examples.

| Term | Meaning and owner |
|---|---|
| Alias | [Another reference to the same object; mutations can be visible through both names.](language/names_and_mutability.md) |
| Binding | [An association between a name and an object; assignment can replace the association.](language/names_and_mutability.md) |
| Mutation | [A change to an existing object's state, distinct from rebinding a name.](language/names_and_mutability.md) |
| Shallow/deep copy | [A new outer container versus recursive copying of reachable data.](language/names_and_mutability.md) |
| Hashability | [Stable hashing compatible with equality, needed for dictionary keys and set members.](language/names_and_mutability.md) |
| Sentinel | [A reserved marker, often a unique object, distinguishing omission from a legitimate value.](language/names_and_mutability.md) |
| Positional-only / keyword-only | [Signature restrictions introduced by `/` and `*`.](language/functions_and_scope.md) |
| Closure | [A function retaining access to bindings from an enclosing function call.](language/functions_and_scope.md) |
| Late binding | [Looking up a retained binding when the function executes, rather than capturing a value snapshot.](language/functions_and_scope.md) |
| Comprehension | [A collection built by iteration, optional filtering and a result expression.](language/idioms_and_collections.md) |
| Truthiness | [How an object behaves in a condition; it is broader than being present or non-None.](language/idioms_and_collections.md) |
| Short-circuiting | [Skipping later operands once a logical expression's returned value is determined.](language/idioms_and_collections.md) |
| Module cache | [The process-local `sys.modules` mapping used to reuse imported module objects.](language/modules_and_imports.md) |
| Bound method | [A function paired with the receiver supplied automatically on a call.](objects/classes_and_methods.md) |
| Property | [Attribute syntax that invokes a getter and optionally setter/deleter behavior.](objects/classes_and_methods.md) |
| MRO | [Method resolution order: the sequence used for inherited lookup and cooperative `super()`.](objects/classes_and_methods.md) |
| Composition | [An object delegating work to a collaborator it holds.](objects/classes_and_methods.md) |
| Introspection | [Inspecting objects, attributes, types or signatures at runtime.](objects/attributes_and_introspection.md) |
| `getattr` | [A built-in that performs ordinary attribute lookup using a string name.](objects/attributes_and_introspection.md) |
| `__getattr__` | [A customization hook reached when ordinary attribute lookup fails.](objects/protocols_and_descriptors.md) |
| Descriptor | [An object on a class that customizes attribute access through methods such as `__get__` and `__set__`.](objects/protocols_and_descriptors.md) |
| Special method / dunder | [A named protocol method such as `__len__` that Python operations dispatch to.](objects/protocols_and_descriptors.md) |
| Protocol | [An expected capability: runtime behavior is demonstrated in object protocols, static structural contracts in typing.](typing/typing.md) |
| Dataclass | [A class whose field declarations generate methods such as initialization and equality.](data_models/dataclasses.md) |
| Default factory | [A callable invoked to create an omitted field's value, keeping per-instance mutable defaults independent.](data_models/dataclasses.md) |
| Frozen | [A guard against ordinary field assignment; nested values may remain mutable.](data_models/dataclasses.md) |
| Slots | [Declared instance attribute storage, separate from validation or immutability.](objects/attributes_and_introspection.md) |
| Enum / StrEnum | [A finite set of named values; StrEnum additionally interoperates with strings.](data_models/enums_and_named_tuples.md) |
| NamedTuple | [A tuple-compatible record with named fields and a positional public contract.](data_models/enums_and_named_tuples.md) |
| BaseModel | [Pydantic's model base for declared parsing, validation and serialization contracts.](data_models/pydantic/01_models_and_fields.md) |
| Coercion / strict mode | [Permitted input conversions versus type-specific stricter validation rules.](data_models/pydantic/01_models_and_fields.md) |
| Validator | [A function that normalizes or checks data at a specified point in a validation pipeline.](data_models/pydantic/02_validation.md) |
| Discriminated union | [Alternative schemas selected by an explicit tag in the input.](data_models/pydantic/02_validation.md) |
| TypeAdapter / RootModel | [Operations over an existing type expression versus a named model around a root value.](data_models/pydantic/02_validation.md) |
| Serialization | [Producing an output representation; its shape and types can differ from the validated model.](data_models/pydantic/03_serialization_and_schema.md) |
| Computed field | [A derived property included in Pydantic serialization.](data_models/pydantic/03_serialization_and_schema.md) |
| JSON Schema | [A machine-readable description of document constraints, distinct from executing validation.](data_models/pydantic/03_serialization_and_schema.md) |
| Iterator / generator | [A pull-based stream and a function-backed implementation that retains suspended state.](control_flow/iterators_and_generators.md) |
| Context manager | [An object/protocol owning entry and exit around a block, commonly for resource cleanup.](control_flow/context_managers.md) |
| Partial application | [Creating a callable with selected arguments already supplied.](language/standard_library_tools.md) |
| Memoization | [Reusing retained results keyed by arguments, with explicit sharing and freshness consequences.](language/standard_library_tools.md) |

[Repository glossary](../../GLOSSARY.md)
