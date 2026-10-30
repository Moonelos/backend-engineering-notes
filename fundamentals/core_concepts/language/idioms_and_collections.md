# Reading Python idioms and collection transformations

> **Role:** foundation. Read [names and mutability](names_and_mutability.md) and
> [functions and scope](functions_and_scope.md). Python 3.11+.
> Each Python block below is a complete, independent program.

A backend often receives a list of records, selects the useful ones, and creates a response. Python
can express that work compactly. The way to read a compact expression is to recover its ordinary
loop, its input values, and the object it produces.

## Start with the loop hidden inside a comprehension

Consider three order lines. We want product names for lines whose quantity is positive:

```python
lines = [
    {"sku": "book", "quantity": 2},
    {"sku": "pen", "quantity": 0},
    {"sku": "mug", "quantity": 1},
]

names = []
for line in lines:
    if line["quantity"] > 0:
        names.append(line["sku"].upper())

compact = [line["sku"].upper() for line in lines if line["quantity"] > 0]
print(compact)                         # ['BOOK', 'MUG']
assert compact == names
```

A **comprehension** builds a collection by iterating, optionally filtering, and computing a value
for each surviving item. Read this one as: “for each line in lines, if quantity is positive, produce
the uppercased SKU.” Its textual order starts with the result expression, but execution starts with
the loop and filter.

This table makes the intermediate decisions visible:

| Input | Quantity test | Result expression evaluated? | Output appended |
|---|---|---|---|
| `book`, 2 | True | Yes | `'BOOK'` |
| `pen`, 0 | False | No | Nothing |
| `mug`, 1 | True | Yes | `'MUG'` |

The `pen` row is skipped before the result expression runs. A list comprehension creates the whole
result immediately. It preserves the input iteration order among selected items. It also has its
own scope for the loop variable in Python 3; `line` does not leak into the surrounding scope merely
because it appeared in this comprehension.

Use the expanded loop when there are several branching decisions, logging, error handling, or
side effects. A comprehension whose result is discarded only to trigger effects hides the purpose
of the loop and allocates an unnecessary list.

## Choose the output container by the question being answered

A list retains sequence and duplicates. A set retains unique values and supports membership tests;
do not depend on a set's iteration order. A dictionary associates unique keys with values and
preserves insertion order. Its keys and set members must be hashable, as the previous lesson explains.

```python
skus = ["book", "pen", "book"]
unique = {sku for sku in skus}
lengths = {sku: len(sku) for sku in skus}

print(sorted(unique))                  # ['book', 'pen']
print(lengths)                         # {'book': 4, 'pen': 3}
assert "book" in unique
assert lengths == {"book": 4, "pen": 3}
```

The second `book` adds no new set element. In the dictionary, it writes the existing key again. If
two source records have the same key but different values, the later assignment wins; constructing
a dictionary is not a duplicate-validation step:

```python
lines = [{"sku": "book", "quantity": 2}, {"sku": "book", "quantity": 5}]
by_sku = {line["sku"]: line["quantity"] for line in lines}
print(by_sku)                          # {'book': 5}
assert by_sku["book"] == 5
```

If duplicates indicate corrupt input, detect them explicitly before accepting the index. If the
goal is to sum quantities, a grouping or counting operation is required; changing the brackets to a
dictionary comprehension does not add aggregation. The
[standard-library tools](standard_library_tools.md) lesson develops those operations.

Parentheses instead of square brackets often produce a **generator expression**, which computes
values as a consumer requests them rather than allocating a result list up front:

```python
quantities = [2, 0, 1]
total = sum(quantity for quantity in quantities if quantity > 0)
print(total)                          # 3
assert total == 3
```

Here `sum` consumes one selected quantity at a time. The expression does not promise parallelism.
Retaining or consuming such an object twice requires understanding its one-shot behavior; continue
to [iterators and generators](../control_flow/iterators_and_generators.md) before designing lazy
pipelines. For a short result that callers must repeatedly inspect, a list is often simpler.

## Unpacking describes an expected shape

Unpacking assigns items from a sequence or other iterable to separate names. An **iterable** is
an object Python can ask for items in a loop. A starred target captures the remaining items as a
list:

```python
record = (42, "book", 2)
order_id, sku, quantity = record
first, *remaining = record
print(order_id, sku, quantity)          # 42 book 2
print(first, remaining)                # 42 ['book', 2]
assert remaining == ["book", 2]

try:
    order_id, sku = record
except ValueError:
    print("the record has more than two items")
```

Without a starred target, the number of supplied items must match the number of targets. This
makes unpacking useful for data with a known shape, but it does not validate the meaning or types of
those items. Unpacking a dictionary directly gets its keys; use `.items()` for key/value pairs.

The same star syntax can assemble containers. Dictionary unpacking uses the later value for a
repeated key:

```python
defaults = {"retries": 2, "timeout": 5}
overrides = {"timeout": 10}
options = {**defaults, **overrides}
tags = ["new", *["paid", "express"]]

print(options)                        # {'retries': 2, 'timeout': 10}
assert options["timeout"] == 10
assert tags == ["new", "paid", "express"]
```

These constructions create new outer containers but retain references to their elements. The copy
rules still apply. Also remember the previous lesson's distinction: duplicate keys can override
during dictionary construction, while passing duplicate keywords to a function raises `TypeError`.

Slicing selects a sequence region using `sequence[start:stop:step]`. The stop position is excluded,
and omitted bounds use the appropriate end of the sequence:

```python
ids = [41, 42, 43, 44]
print(ids[:2], ids[-1], ids[::-1])       # [41, 42] 44 [44, 43, 42, 41]
assert ids[:2] == [41, 42]
assert ids[1:3] == [42, 43]
```

List slices produce new lists, still containing references to the selected elements. Negative
indices count from the end. A slice beyond the end is bounded rather than failing; a single index
outside the sequence raises `IndexError`. This matters when a slice is incorrectly treated as proof
that a required number of records existed.

## Truthiness is broader than “is present”

A truth test asks how a value behaves in a condition. `None`, `False`, numeric zero, and empty
built-in containers and strings are false; their usual nonempty counterparts are true. Therefore
`if value:` is not equivalent to `if value is not None:`.

Suppose zero retries is a valid instruction to disable retries. A common defaulting idiom silently
overrides that choice:

```python
configured_retries = 0
wrong = configured_retries or 3
correct = 3 if configured_retries is None else configured_retries
print(wrong, correct)                  # 3 0
assert wrong == 3 and correct == 0
```

`or` returns its first truthy operand, or the last operand if none is truthy. `and` returns its first
false operand, or its last operand if all are truthy. They return operands, not necessarily booleans,
and **short-circuit**: later operands are evaluated only when needed to determine the result.

```python
events = []

def load_default():
    events.append("loaded")
    return "standard"

result = "express" or load_default()
assert result == "express" and events == []
result = "" or load_default()
assert result == "standard" and events == ["loaded"]

customer = None
assert (customer is not None and customer["active"]) is False
print(events)                         # ['loaded']
```

The last condition is safe because the first operand is false, so Python never indexes `None`.
Short-circuiting can prevent unnecessary work, but combining business actions with `and`/`or` often
makes their execution conditions hard to see. Use an `if` statement when an action deserves a clear
branch. Custom objects can customize truth testing; the object-protocol lesson explains how.

`any` and `all` ask questions over an iterable. `any` stops at the first truthy item; `all` stops at
the first false item. On empty input, `any` returns false and `all` returns true:

```python
quantities = [2, 0, 1]
assert any(q > 0 for q in quantities)
assert not all(q > 0 for q in quantities)
assert not any([])
assert all([])

orders = []
ready = bool(orders) and all(order["paid"] for order in orders)
print(ready)                          # False
assert not ready
```

`all([])` is true because no element disproves the condition. If “ready” also requires at least one
order, state that separately, as the example does. Neither `all` nor `any` ensures every item is
visited, so do not hide required side effects inside their inputs.

## Pairing, numbering, and sorting should preserve the intended relationships

`enumerate` pairs each value with a counter, avoiding a separate indexed lookup. `zip` pairs values
from iterables position by position. By default it stops when the shortest input ends:

```python
skus = ["book", "mug"]
quantities = [2]
print(list(enumerate(skus, start=1)))   # [(1, 'book'), (2, 'mug')]
print(list(zip(skus, quantities)))     # [('book', 2)]

try:
    list(zip(skus, quantities, strict=True))
except ValueError:
    print("SKU and quantity counts differ")
```

If the pairing represents a contract, use `strict=True` (available since Python 3.10). The mismatch
is detected while iterating, so earlier pairs may already have been produced. When partial work
would be harmful, validate or materialize the paired input before performing effects. For data that
can arrive out of order, positional pairing is the wrong contract entirely: match by a stable key.

Sorting similarly needs an explicit comparison key. `sorted` returns a new list; a list's `.sort()`
mutates the existing list and returns `None`:

```python
lines = [
    {"sku": "book", "quantity": 2},
    {"sku": "mug", "quantity": 1},
    {"sku": "pen", "quantity": 2},
]
ranked = sorted(lines, key=lambda line: line["quantity"], reverse=True)
print([line["sku"] for line in ranked])  # ['book', 'pen', 'mug']
assert [line["sku"] for line in lines] == ["book", "mug", "pen"]
assert ranked[0] is lines[0]            # new outer list, same record objects

values = [3, 1, 2]
result = values.sort()
assert values == [1, 2, 3] and result is None
```

The `key` callable computes each item's comparison value. Python sorting is **stable**: items whose
keys compare equal keep their input order, even with `reverse=True`. That is why `book` remains
before `pen`. To define a secondary order, return a tuple such as
`(-line['quantity'], line['sku'])`: tuples compare the first unequal element, so negative quantity
sorts larger quantities first and SKU breaks ties. Stability alone does not make an unordered data
source deterministic; define a tie-breaker if the output contract requires one.

## Pattern matching selects by shape and can bind names

`match` (Python 3.10+) can express branches for several structured input shapes. Unlike a chain of
simple equality checks, a pattern can extract values into names. A guard, introduced by `if`, adds
a condition after a pattern matches:

```python
def describe_action(payload):
    match payload:
        case {"action": "ship", "order_id": int(order_id)} if order_id > 0:
            return f"ship:{order_id}"
        case {"action": "cancel", "order_id": int(order_id)} if order_id > 0:
            return f"cancel:{order_id}"
        case _:
            return "unsupported"

print(describe_action({"action": "ship", "order_id": 42}))  # ship:42
assert describe_action({"action": "ship", "order_id": "42"}) == "unsupported"
assert describe_action({"action": "ship", "order_id": 42, "extra": 1}) == "ship:42"
```

The mapping pattern requires the listed keys but permits additional keys. `int(order_id)` matches
an integer instance and binds it; it does not parse a string into an integer. Since `bool` is a
subclass of `int`, the pattern also accepts booleans unless the guard excludes them. This example
is dispatch over already-understood application data, not a complete untrusted-input validator.
Use the [Pydantic lessons](../data_models/pydantic/README.md) for a declared external-data contract.

One important reading trap: a bare name in a pattern generally **captures** the matched value. It
does not compare to a same-named local constant. Use literal patterns such as `"ship"` or qualified
enum members such as `Action.SHIP`. `_` is a wildcard that does not bind a name. Prefer ordinary
`if`/`elif` when the decision is about conditions rather than structured shapes.

The assignment expression `:=`, often called the walrus operator, can bind a computed value inside
an expression. Use it when naming a result avoids repeated work and clarifies the condition:

```python
raw_names = [" book ", " ", "mug"]
clean = [name for raw in raw_names if (name := raw.strip())]
print(clean)                          # ['book', 'mug']
assert clean == ["book", "mug"]
```

The filter computes and binds `name`, tests its truthiness, and only then evaluates the result
expression. Here empty strings are intentionally discarded. Assignment expressions inside a
comprehension bind in its containing scope, unlike its loop variable; avoid using that leaked name
as an output contract. An ordinary loop is clearer when the expression needs explanation on every
read.

## Recap

- Recover a comprehension's loop, filter, and produced value before interpreting its compact syntax.
- Container choice decides whether order, duplicate values, or key/value associations survive.
- Unpacking expresses shape; copies and assembled containers still share their element objects.
- Truthiness and short-circuiting decide both returned values and which work executes.
- Pairing and sorting need a contract for missing items and equal keys; matching is dispatch, not full validation.

## Check yourself

**1. `zip(ids, results, strict=True)` is used directly in a loop that writes each result to a database.
It raises on the final iteration. Have the earlier writes necessarily been prevented?**

<details><summary>Answer</summary>

No. `zip` yields earlier pairs before discovering the length mismatch. `strict=True` detects the
broken contract but does not undo effects. Materialize/validate the pairs first, or use a transaction
whose rollback policy covers the failure. Which choice fits depends on input size and the operation.

</details>

**2. You sort a list of order dictionaries into `ranked`, then change `ranked[0]['quantity']`.
Can the original list's contents change even though `sorted` made a new list?**

<details><summary>Answer</summary>

Yes. The lists are different outer containers holding references to the same dictionaries. Sorting
does not clone each element. Mutating the selected dictionary is visible wherever that dictionary
is referenced. Replacing `ranked[0]` with a different dictionary would only change the new list's slot.

</details>

**3. An empty batch passes `all(record['valid'] for record in batch)`. Is that a Python bug?**

<details><summary>Answer</summary>

No. There is no false item, so `all` returns true. If an empty batch is invalid for the application,
add a separate nonempty requirement. Collection predicates only answer the question encoded in them.

</details>

## Sources and continuation

Checked 2026-10-30 against the Python 3.11 baseline:
[data structures](https://docs.python.org/3.11/tutorial/datastructures.html),
[built-in functions](https://docs.python.org/3.11/library/functions.html), and
[pattern matching and control flow](https://docs.python.org/3.11/tutorial/controlflow.html).

**Next:** [Modules and imports](modules_and_imports.md). For reusable collection and function tools,
continue to [standard-library tools](standard_library_tools.md).
