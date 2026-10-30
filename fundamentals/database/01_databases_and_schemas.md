# Databases, Schemas, and SQL Foundations

<!-- length-justification: This is the canonical relational-foundations reference; schemas, constraints, transactions, indexes, normalization, and the first SQL operations remain together so later driver and ORM notes can assume one consistent database model. -->

> **Reading path**: table identities → disposable writes and constraints → NULL and joined rows → transaction snapshots → measured indexes → normalization. The database-choice and specialized-feature sections are optional reference continuations.

> **Who this is for**: Engineers who know how to code but want a solid mental model of relational databases before touching Python drivers or ORMs.

> **Key insight**: A relational database protects relationships and invariants at the shared data boundary; application objects are only temporary views of that durable model.

---

## 1. What Is a Relational Database?

A relational database stores data in **tables** (relations). Each table has a fixed set of **columns** (the structure) and a variable number of **rows** (the data). Tables can reference each other through **foreign keys**, forming a web of related data.

```
users table                    posts table
─────────────────────          ──────────────────────────────────
id | email       | name        id | title    | author_id | published
───┼─────────────┼────         ───┼──────────┼───────────┼─────────
1  | a@b.com     | Alice       1  | Hello    | 1         | true
2  | x@y.com     | Bob         2  | World    | 1         | false

```

`posts.author_id` is a **foreign key** — it points to `users.id`. This is how you express "a post belongs to a user" without duplicating user data in every row.

### Why Relational?

- **Data integrity**: The database enforces rules (unique emails, non-null names, valid foreign keys).
- **No duplication**: Data lives in one place. Update a user's email once, everywhere sees the change.
- **Flexible queries**: SQL lets you slice and combine data any way you need.
- **ACID guarantees**: Transactions are reliable even if the server crashes mid-operation.

---

## 2. Core Concepts: Tables, Columns, and Data Types

### Tables and Columns

A **table** maps to a real-world entity: users, orders, products.
A **column** is an attribute of that entity with a specific type.
A **row** is a single instance. The following permanent-table definition is a schema reference; use the disposable TEMP setup below for the runnable lesson.

```sql
CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    email       VARCHAR(255) NOT NULL UNIQUE,
    name        VARCHAR(100) NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Build a disposable users/posts database first

Use `psql` against a disposable PostgreSQL database. These TEMP tables belong only to this connection and disappear on disconnect; they shadow any same-named permanent tables. Run this setup once, then the queries below in the same connection. Later feature examples are independent excerpts and name their own prerequisites.

```sql
CREATE TEMP TABLE users (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TEMP TABLE posts (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL CHECK (length(title) > 0),
    author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    published BOOLEAN NOT NULL DEFAULT FALSE
);
INSERT INTO users (email, name) VALUES
    ('alice@example.com', 'Alice'), ('bob@example.com', 'Bob');
INSERT INTO posts (title, author_id, published) VALUES
    ('Hello', 1, TRUE), ('World', 1, FALSE);
SELECT id, name FROM users ORDER BY id;
-- 1 | Alice
-- 2 | Bob
```

The generated identifier is the stable identity of a row, while `name` can change. Both posts reference identity 1. Updating Alice's name changes one row, and a join subsequently reads that new name for both posts. A foreign key checks identity, not a copied name.

Try these failed writes individually with psql's ordinary autocommit enabled; each fails without changing the earlier rows:

```sql
INSERT INTO users (email, name) VALUES ('alice@example.com', 'Other');
-- duplicate key violates unique constraint
INSERT INTO posts (title, author_id) VALUES ('Orphan', 999);
-- violates foreign key constraint
INSERT INTO posts (title, author_id) VALUES ('', 1);
-- violates check constraint
```

A pre-insert Python check cannot replace these constraints: two clients can both check before either inserts. The unique index arbitrates their actual writes. Within an explicit transaction a statement error instead leaves the transaction aborted until rollback (or rollback to a previously created savepoint).

## 3. Constraints — Enforcing Data Integrity at the Database Level

Constraints are rules the database enforces on every write. They are your last line of defense.

### PRIMARY KEY

Uniquely identifies each row. Cannot be NULL. Usually an auto-increment integer or UUID.

```sql
id SERIAL PRIMARY KEY
id UUID PRIMARY KEY DEFAULT gen_random_uuid()
```

### UNIQUE

No two rows can have the same value(s). Can span multiple columns.

```sql
email VARCHAR(255) UNIQUE                          -- single column
UNIQUE (user_id, team_id)                          -- composite unique (no duplicate memberships)
```

### NOT NULL

Column must always have a value. Without this, `NULL` is allowed: it represents missing or unknown data, rather than an ordinary value. Both `NULL = NULL` and `NULL <> NULL` evaluate to UNKNOWN, represented by SQL NULL.

```sql
name VARCHAR(100) NOT NULL
```

### NULL changes both filtering and integrity checks

Run this independent temporary-table example in the same psql connection:

```sql
CREATE TEMP TABLE readings (id INTEGER PRIMARY KEY, value INTEGER UNIQUE CHECK (value >= 0));
INSERT INTO readings VALUES (1, 5), (2, NULL), (3, NULL);
SELECT id FROM readings WHERE value <> 5 ORDER BY id;
-- no rows: NULL <> 5 is UNKNOWN, not TRUE
SELECT id FROM readings WHERE value IS NULL ORDER BY id;
-- 2; 3
SELECT NULL = NULL AS equal, NULL <> NULL AS unequal, NULL IS NULL AS missing;
-- NULL | NULL | true
```

`WHERE` retains only TRUE. FALSE and UNKNOWN both remove a row. `IS NULL` asks whether a value is missing and always returns TRUE or FALSE. `CHECK (value >= 0)` rejects FALSE but accepts UNKNOWN, so it admits both NULL rows; add `NOT NULL` when absence is invalid. PostgreSQL's ordinary UNIQUE constraint allows multiple NULLs by default. PostgreSQL 15+ can use `UNIQUE NULLS NOT DISTINCT` to allow at most one. This is a uniqueness policy, not a change to ordinary NULL comparisons. [Comparison operators](https://www.postgresql.org/docs/current/functions-comparison.html), [constraints](https://www.postgresql.org/docs/current/ddl-constraints.html).

### FOREIGN KEY

Links rows between tables. Prevents orphaned records.

```sql
author_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE
```

`ON DELETE` behaviors:

| Behavior | What happens when parent row is deleted |
|----------|----------------------------------------|
| `NO ACTION` | Default: reject a remaining violation at constraint-check time; a DEFERRABLE constraint can postpone this check |
| `RESTRICT` | Reject the referenced-row delete immediately; this action cannot be deferred |
| `CASCADE` | Delete child rows automatically |
| `SET NULL` | Set the FK column to NULL |
| `SET DEFAULT` | Set the FK column to its default value |

### CHECK

Validates a condition on the row:

```sql
age INTEGER CHECK (age >= 0 AND age <= 150)
status VARCHAR(20) CHECK (status IN ('pending', 'active', 'cancelled'))
```

### DEFAULT

Sets the value when none is provided:

```sql
is_active   BOOLEAN NOT NULL DEFAULT TRUE
created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

---

## 4. SQL Fundamentals

The following SELECT/INSERT/UPDATE/DELETE blocks are independent syntax references against the earlier schema, not one script to execute from top to bottom: some intentionally modify the same row or reuse a unique email. The joined-row trace below is the runnable continuation of the disposable setup.

### SELECT — Reading Data

```sql
-- Basic
SELECT id, email, name FROM users;

-- All columns (avoid in production code — fragile against schema changes)
SELECT * FROM users;

-- Filter
SELECT * FROM users WHERE is_active = TRUE AND email LIKE '%@company.com';

-- Sort
SELECT * FROM users ORDER BY created_at DESC;

-- Paginate
SELECT * FROM users ORDER BY id LIMIT 20 OFFSET 40;

-- Count
SELECT COUNT(*) FROM users WHERE is_active = TRUE;
```

### JOINs — Combining Tables

```sql
-- INNER JOIN: only rows with a match in both tables
SELECT u.name, p.title
FROM posts p
INNER JOIN users u ON p.author_id = u.id;

-- LEFT JOIN: all rows from left table, matching rows from right (NULL if no match)
SELECT u.name, COUNT(p.id) AS post_count
FROM users u
LEFT JOIN posts p ON p.author_id = u.id
GROUP BY u.id, u.name;

-- EXISTS: check if related rows exist
SELECT * FROM users u
WHERE EXISTS (
    SELECT 1 FROM posts p WHERE p.author_id = u.id AND p.published = TRUE
);
```

### Follow rows through JOIN, grouping, and filtering

Using the disposable setup, inspect the joined rows before aggregating:

```sql
SELECT u.id, u.name, p.id AS post_id, p.title
FROM users u LEFT JOIN posts p ON p.author_id = u.id
ORDER BY u.id, p.id;
-- 1 | Alice | 1    | Hello
-- 1 | Alice | 2    | World
-- 2 | Bob   | NULL | NULL
SELECT u.id, u.name, COUNT(p.id) AS post_count, COUNT(*) AS joined_rows
FROM users u LEFT JOIN posts p ON p.author_id = u.id
GROUP BY u.id, u.name ORDER BY u.id;
-- 1 | Alice | 2 | 2
-- 2 | Bob   | 0 | 1
```

The LEFT JOIN preserves Bob with a placeholder row because no post matches. `GROUP BY` collects joined rows per user. `COUNT(p.id)` counts non-NULL identifiers, giving Bob zero; `COUNT(*)` counts the placeholder too. An INNER JOIN removes Bob entirely. The logical reasoning order is FROM/JOIN → WHERE → GROUP BY/aggregates → HAVING → SELECT → ORDER BY → LIMIT; the optimizer may implement it differently while preserving meaning.

To count published posts and retain zero-post users, place `p.published = TRUE` in the join's `ON` condition. Placing it in `WHERE` removes Bob: his placeholder yields UNKNOWN. `HAVING COUNT(p.id) >= 2` filters whole groups after counting, while `WHERE` filters individual input rows before counting.

A window function instead preserves each input row. On the two post rows, `COUNT(*) OVER (PARTITION BY author_id)` reports 2 beside both Hello and World. A grouped count would produce one row for Alice. `ROW_NUMBER() OVER (PARTITION BY author_id ORDER BY id)` labels Hello 1 and World 2; the explicit ordering determines the ranking, rather than relying on storage order.

Run this query before changing the fixture to see that row-preserving calculation:

```sql
SELECT title, COUNT(*) OVER (PARTITION BY author_id) AS author_total,
       ROW_NUMBER() OVER (PARTITION BY author_id ORDER BY id) AS position
FROM posts ORDER BY id;
-- Hello | 2 | 1
-- World | 2 | 2
```

**Predict before running:** add Carol with no posts, then delete Alice's unpublished post. The grouped query gives Alice `(1, 1)`, Bob `(0, 1)`, Carol `(0, 1)` for `(post_count, joined_rows)`. Each remaining user contributes at least one joined row; only Alice contributes a non-NULL post identifier. This explanation should still work if there are ten users with no posts.

### Keep the next page anchored to a stable ordered key

OFFSET skips a number of rows in the current statement's result. If page 1 ends at the twentieth row and another client inserts a row before it, page 2's OFFSET 20 can repeat the former twentieth row. A deletion before that point can instead skip a row. Deep offsets also require locating/discarding preceding rows.

Keyset pagination asks for keys after the last **value**, rather than after a changing count. This excerpt uses the posts fixture and an `(author_id, id)` ordering; the cursor from Hello is `(1, 1)`:

```sql
CREATE INDEX ON posts(author_id, id);
SELECT id, author_id, title FROM posts
ORDER BY author_id, id LIMIT 1;
-- 1 | 1 | Hello; encode author_id=1, id=1 as the next cursor
SELECT id, author_id, title FROM posts
WHERE (author_id, id) > (1, 1)
ORDER BY author_id, id LIMIT 1;
-- 2 | 1 | World
```

The comparison uses author_id first, then id to break ties. A key equal to the cursor is excluded; a row inserted before it cannot shift the next page boundary. Include every ORDER BY key in the cursor and index, use the same direction/comparison, and validate or bind decoded cursor values in Python. These keys are NOT NULL; nullable keys need an explicit ordering/cursor policy because comparisons with NULL become UNKNOWN. Require author_id to remain stable during pagination, or choose an immutable ordering key: moving a row across the cursor can still skip or repeat it. Keyset pagination also does not freeze a dataset across READ COMMITTED requests: later inserts after the cursor can appear, earlier inserts can be omitted. Use one bounded-duration repeatable-read transaction when an export requires a fixed snapshot, accounting for its connection and old-version retention costs. [Row comparisons](https://www.postgresql.org/docs/current/functions-comparisons.html), [LIMIT/OFFSET](https://www.postgresql.org/docs/current/queries-limit.html).

### INSERT

```sql
-- Single row
INSERT INTO users (email, name) VALUES ('a@b.com', 'Alice');

-- Return generated values
INSERT INTO users (email, name) VALUES ('a@b.com', 'Alice') RETURNING id, created_at;

-- Multiple rows
INSERT INTO users (email, name) VALUES
    ('a@b.com', 'Alice'),
    ('x@y.com', 'Bob');

-- Upsert (insert or update on conflict)
INSERT INTO users (email, name) VALUES ('a@b.com', 'Alice')
ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name;

-- Ignore on conflict
INSERT INTO users (email, name) VALUES ('a@b.com', 'Alice')
ON CONFLICT (email) DO NOTHING;
```

### UPDATE

```sql
-- Basic update
UPDATE users SET name = 'Alice Smith' WHERE id = 1;

-- Update multiple columns
UPDATE users SET name = 'Alice Smith', is_active = FALSE WHERE id = 1;

-- Update with a subquery
UPDATE posts SET published = TRUE
WHERE author_id IN (SELECT id FROM users WHERE is_active = TRUE);

-- Return updated rows
UPDATE users SET is_active = FALSE WHERE id = 1 RETURNING id, email;
```

### DELETE

```sql
-- Delete specific rows
DELETE FROM users WHERE id = 1;

-- Delete with condition
DELETE FROM users WHERE created_at < NOW() - INTERVAL '1 year' AND is_active = FALSE;

-- Return deleted rows
DELETE FROM users WHERE id = 1 RETURNING email;

-- Destructive rehearsal on a verified disposable database.
BEGIN;
SELECT current_database();  -- stop unless this is the expected test database
TRUNCATE TABLE users RESTART IDENTITY CASCADE;
SELECT count(*) FROM users;  -- 0
ROLLBACK;
SELECT count(*) FROM users;  -- original rows are visible again
```

PostgreSQL `TRUNCATE` is transactional for table data, but it takes an `ACCESS EXCLUSIVE` lock and
is not MVCC-safe for snapshots taken before the truncation. `CASCADE` also truncates referencing
tables and `RESTART IDENTITY` resets owned sequences, so verify the target and dependent tables
before committing it.

---

## 5. Transactions and ACID

A **transaction** groups multiple SQL statements into a single atomic unit. Either all statements succeed, or none of them do.

```sql
BEGIN;
    UPDATE accounts SET balance = balance - 100 WHERE id = 1;
    UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;
-- Both updates committed, or neither is
```

If anything goes wrong between `BEGIN` and `COMMIT`:

```sql
BEGIN;
    UPDATE accounts SET balance = balance - 100 WHERE id = 1;
    -- server crashes here
-- PostgreSQL automatically rolls back — balance unchanged
```

### ACID Properties

| Property | Meaning | Example |
|----------|---------|---------|
| **Atomicity** | All or nothing — partial transactions don't exist | Money transfer: both debits and credits happen, or neither does |
| **Consistency** | Declared constraints and correctly written business operations preserve invariants | Immediate constraints are checked per statement; deferrable ones may be checked at commit |
| **Isolation** | Controls what concurrent transactions observe and which conflicts must abort | A booking invariant still needs a conditional write, lock, or serializable transaction |
| **Durability** | Committed data survives crashes | Written to disk (WAL) before `COMMIT` returns |

### Isolation Levels

PostgreSQL supports four isolation levels. The default is `READ COMMITTED`.

| Level | Prevents | Use case |
|-------|----------|----------|
| `READ UNCOMMITTED` | Nothing (same as READ COMMITTED in PG) | N/A in PostgreSQL |
| `READ COMMITTED` | Dirty reads | Default — good for most apps |
| `REPEATABLE READ` | Dirty reads, non-repeatable reads | Reporting queries that must see consistent snapshot |
| `SERIALIZABLE` | Serialization anomalies among successfully committed serializable transactions | Cross-row rules; retry the whole transaction on serialization failure |

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
-- all reads see the same snapshot for the duration
COMMIT;
```

In SQLAlchemy, configure the connection/engine isolation level before its transaction starts. PostgreSQL itself permits `SET TRANSACTION ISOLATION LEVEL` after `BEGIN`, but before the first query or data-modification statement. A session may already have issued SQL implicitly, so engine configuration avoids that ambiguity. [SET TRANSACTION](https://www.postgresql.org/docs/current/sql-set-transaction.html). The following is an async configuration excerpt; imports/session setup belong to [04](04_async_sqlalchemy.md):

```python
# Bind the isolation level before a session can implicitly start a transaction.
repeatable_read_engine = create_async_engine(
    DATABASE_URL,
    isolation_level="REPEATABLE READ",
)
RepeatableReadSession = async_sessionmaker(repeatable_read_engine)

async with RepeatableReadSession.begin() as session:
    rows = (await session.execute(report_query)).all()
```

### Two connections show what a snapshot means

MVCC keeps row versions so a normal reader can inspect a committed version while another transaction is editing it. A snapshot defines which committed versions that statement may see. Use two psql connections to the same **disposable database** for this example; TEMP tables cannot be shared between them. Connection A creates `snapshot_demo` once:

```sql
CREATE TABLE snapshot_demo (id INTEGER PRIMARY KEY, seats INTEGER NOT NULL CHECK (seats >= 0));
INSERT INTO snapshot_demo VALUES (1, 1);
```

Execute each row in order across the connections. The initial seats value is 1.

| Step | Connection A | Connection B | Visible result |
|------|--------------|--------------|----------------|
| 1 | `BEGIN ISOLATION LEVEL READ COMMITTED;` then `SELECT seats FROM snapshot_demo WHERE id=1;` | — | A reads 1 |
| 2 | — | `BEGIN; UPDATE snapshot_demo SET seats=0 WHERE id=1;` | B owns uncommitted 0 |
| 3 | `SELECT seats FROM snapshot_demo WHERE id=1;` | — | A still reads committed 1 |
| 4 | — | `COMMIT;` | 0 is committed |
| 5 | `SELECT seats FROM snapshot_demo WHERE id=1;` then `COMMIT;` | — | A now reads 0 |

Repeat after resetting seats to 1, changing A's BEGIN to REPEATABLE READ. A reads 1 at step 5 because its first read fixed the transaction snapshot. After A commits, a new transaction sees 0. A transaction always sees its own writes. A stable snapshot does not automatically protect rules derived from several rows; SERIALIZABLE can reject conflicting executions with SQLSTATE `40001`, requiring the **whole transaction**, including its decisions, to retry. [PostgreSQL isolation](https://www.postgresql.org/docs/current/transaction-iso.html).

Two clients can both read 1 and then each decide to book. Protect this single-row invariant by making the decision part of the write:

```sql
BEGIN;
UPDATE snapshot_demo SET seats = seats - 1 WHERE id = 1 AND seats > 0 RETURNING seats;
COMMIT;
-- One returned row means booked; zero rows means unavailable.
```

At READ COMMITTED, a concurrent second update waits for the first writer. After that writer commits, PostgreSQL rechecks `seats > 0` against the new row version. With one seat, the first update returns 0 and the second returns no row. `CHECK (seats >= 0)` remains a defensive invariant. For a multi-statement decision, `SELECT ... FOR UPDATE` can lock the shared decision row before reading it; keep that transaction short. Lock rows in a consistent order to reduce deadlocks. A plain SELECT does not acquire that exclusive row lock.

**Changed condition:** start with two seats and three clients. Exactly two conditional updates return a row; one returns none. Reading seats and later assigning a value calculated in Python loses this protection because the condition is no longer tied to the write. Once both connections commit, clean up with `DROP TABLE snapshot_demo;`.

### Savepoints — Nested Rollbacks

In interactive psql, the duplicate error is intentional: continue with ROLLBACK TO SAVEPOINT before issuing further SQL. In a script with ON_ERROR_STOP enabled, handle the expected error in the driver instead; a script that stops at the duplicate will never execute the recovery statements.

```sql
BEGIN;
    INSERT INTO users (email, name) VALUES ('savepoint@example.com', 'Savepoint');
    SAVEPOINT sp1;
    INSERT INTO users (email, name) VALUES ('savepoint@example.com', 'Savepoint');  -- duplicate!
    ROLLBACK TO SAVEPOINT sp1;                      -- undo only the second insert
    -- first insert is still in transaction
COMMIT;
```

Savepoints let you roll back part of a transaction without aborting the whole thing. SQLAlchemy exposes this via `session.begin_nested()`.

---

## 6. Indexes — Making Queries Fast

An index is a separate data structure (usually a B-tree) that PostgreSQL maintains to allow fast lookups.

### Without an Index

The fixture's UNIQUE email already creates an index, so it cannot demonstrate an unindexed email lookup. This comparison describes a hypothetical table without that constraint; for the fixture, compare an unindexed name lookup and `CREATE INDEX ON users(name)` instead. Small tables can correctly keep a sequential scan even after indexing.

```sql
SELECT * FROM users WHERE email = 'alice@example.com';
-- An unindexed equality lookup may scan all rows.
```

### With an Index

```sql
CREATE INDEX ON users (email);
SELECT * FROM users WHERE email = 'alice@example.com';
-- A B-tree lookup can narrow candidates; the planner still chooses the plan.
```

### Index Types

| Type | Use case | Example |
|------|----------|---------|
| B-tree (default) | Equality, range queries (`=`, `<`, `>`, `BETWEEN`) | Most columns |
| Hash | Equality only (`=`); benchmark size/performance for the workload | `id = $1` |
| GIN | JSONB, arrays, full-text search | `payload @> '{"type":"login"}'` |
| GiST | Geometric data, full-text | PostGIS, `tsvector` |
| BRIN | Very large tables with naturally ordered data | Append-only logs by timestamp |

### Compare eligible and ineligible partial-index queries

This optional complete plan experiment uses another temporary table. Run it in the disposable connection; timings and exact plan formatting vary by environment.

```sql
CREATE TEMP TABLE index_orders (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, status TEXT NOT NULL);
INSERT INTO index_orders
SELECT n, n % 100, CASE WHEN n % 1000 = 0 THEN 'active' ELSE 'complete' END
FROM generate_series(1, 10000) n;
CREATE INDEX ix_index_orders_active ON index_orders(user_id) WHERE status = 'active';
ANALYZE index_orders;
EXPLAIN SELECT * FROM index_orders WHERE user_id = 0 AND status = 'active';
EXPLAIN SELECT * FROM index_orders WHERE user_id = 0;
```

The first query asks only for the ten active rows and can use the partial index. The second asks for all 100 user-0 rows, including complete rows absent from that index, so it needs another access path. On the verified PostgreSQL 15 fixture, the first plan used Index Scan and the second Seq Scan. This demonstrates predicate eligibility, not a promise that every eligible query will choose an index. ANALYZE gives the planner distribution estimates; poor estimates can also arise from correlation or skew, so a row-estimate mismatch alone does not prove statistics are stale.

### When to Add an Index

Add indexes on columns you:
- Filter on (`WHERE email = $1`)
- Sort on frequently (`ORDER BY created_at DESC`)
- Join on (`JOIN posts ON posts.author_id = users.id`)
- Use as a foreign key

**Unique constraint = unique index.** When you declare `UNIQUE`, PostgreSQL creates the index automatically.

### Index Cost

Indexes are not free:
- Writes maintain relevant index entries; updates can sometimes avoid index changes through HOT when indexed columns are unchanged
- Indexes use disk space
- Too many indexes on a write-heavy table can slow it down

Rule of thumb: add indexes for your known query patterns. Don't index everything preemptively. Use `EXPLAIN ANALYZE` to see if a query is using indexes.

```sql
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'alice@example.com';
```

### Reading `EXPLAIN ANALYZE` Output

`EXPLAIN` shows the plan the optimizer will use. `EXPLAIN ANALYZE` actually runs the query and reports real numbers. The output is a tree of nodes; read bottom-up (leaves run first).

```
Index Scan using users_email_idx on users  (cost=0.42..8.44 rows=1 width=64) (actual time=0.041..0.043 rows=1 loops=1)
  Index Cond: (email = 'alice@example.com'::text)
Planning Time: 0.108 ms
Execution Time: 0.071 ms
```

What each piece means:

| Piece | Meaning |
|-------|---------|
| `Index Scan using users_email_idx` | Used an index. Seeking to rows directly. |
| `Seq Scan on users` | Reading the whole table. Fine for small tables; a red flag on large ones with a `WHERE` that should be indexable. |
| `Bitmap Index Scan` / `Bitmap Heap Scan` | Mid-selectivity query: index gives row locations, heap is read in sorted order. |
| `cost=0.42..8.44` | Planner's estimated cost units (startup..total). Arbitrary, but comparable across plans. |
| `rows=1` | Planner's row estimate. Compare against actual — large mismatch suggests inaccurate estimates: stale statistics, skew, or correlated predicates; investigate and ANALYZE as appropriate. |
| `actual time=0.041..0.043` | Wall time, ms. First number is time to first row, second is time to last row. |
| `loops=N` | Node executed N times (once per outer row in a nested loop join). Total time = per-loop × loops. |
| `Planning Time` / `Execution Time` | Planning cost (usually sub-ms) and real execution. If planning is a large fraction of total, the query is fast enough to not care. |

**What to look for when tuning:**

- `Seq Scan` on a large table with a selective `WHERE` → add the right index.
- Large gap between estimated `rows=` and actual rows in the output → `ANALYZE` the table (autovacuum usually handles this, but bulk loads may outrun it).
- `Rows Removed by Filter: N` after an index scan → index matched too broadly; consider a composite or partial index.
- Nested Loop with high `loops=` → outer side is big; maybe a Hash Join would be better. PostgreSQL usually picks right, but very skewed data or wrong stats can mislead it.

### Partial Indexes

The orders excerpts below require an independently defined `orders(user_id, created_at, status)` table. They explain index eligibility; they are not part of the users/posts fixture.

A **partial index** indexes only the rows matching a `WHERE` clause. Smaller on disk, faster to maintain, and often faster to query — because the index is exactly the subset you filter on.

```sql
-- Most orders are completed; only a small fraction are 'active'.
-- A full index on status is huge and mostly useless for the "active" query.
CREATE INDEX idx_orders_active ON orders (user_id, created_at)
    WHERE status = 'active';
```

Now:

```sql
SELECT * FROM orders
 WHERE user_id = 42
   AND status = 'active'
 ORDER BY created_at DESC;
```

…is eligible to use this partial index because its predicate implies `status = 'active'`. The planner still compares costs and can choose a sequential scan. A smaller index can reduce maintenance and pages read; query speed is not proportional to index size.

Other good partial-index targets:

- **Soft-delete columns**: `WHERE deleted_at IS NULL` — exclude the dead rows from the index.
- **Flag columns with lopsided distribution**: `WHERE flagged = true` — the 0.1% of rows flagged for review.
- **Fixed lifecycle buckets**: `WHERE archive_status = 'hot'` — move rows to `cold` with a scheduled
  update, or use time-based partitioning. PostgreSQL requires partial-index predicates to be
  immutable, so `now()` is not allowed in the index definition.

Cost to remember: PostgreSQL can only use a partial index when the planner can prove the query's `WHERE` clause implies the index predicate. A query whose predicate does not imply `status = 'active'` cannot use it to answer that query. A generic prepared plan for `status = $1` cannot establish that implication for every parameter; verify the actual prepared/custom plan used by the application. [Partial indexes](https://www.postgresql.org/docs/current/indexes-partial.html).

---

## 7. Database Design: Normalization

**Normalization** is the process of organizing tables to reduce redundancy and prevent data anomalies.

### First Normal Form (1NF)

Each column contains atomic (indivisible) values. No repeating groups.

```
Bad:  users.tags = "python,backend,api"    ← CSV in a column
Good: tags table with user_id FK           ← separate rows
```

### Second Normal Form (2NF)

Every non-key column depends on the **whole** candidate key (relevant for composite keys). Consider membership rows keyed by `(user_id, team_id)`:

| user_id | team_id | user_email | role |
|---------|---------|------------|------|
| 1 | 10 | alice@example.com | owner |
| 1 | 20 | alice@example.com | member |

`role` depends on the pair: Alice has different roles in different teams. `user_email` depends only on `user_id`; changing it requires editing both rows, and a missed update leaves contradictory emails. Split into `users(user_id PRIMARY KEY, email)` and `memberships(user_id, team_id, role, PRIMARY KEY(user_id, team_id))` with a user foreign key. The dependency now has one owner. Adding a surrogate membership ID alone does not remove the duplicated dependency.

### Third Normal Form (3NF)

No transitive dependencies: non-key columns shouldn't depend on other non-key columns.

```
Bad:  orders table has both customer_id AND customer_email
      (customer_email depends on customer_id, not on order_id)
Good: customer_email lives in the customers table
```

In the orders example, split `customers(customer_id PRIMARY KEY, email)` from `orders(order_id PRIMARY KEY, customer_id REFERENCES customers)`. Joining retrieves the current email without storing one copy per order. Deleting the last order no longer deletes the only record of the customer's email. Conversely, a purchase-time contact address is a historical fact owned by the order: it should remain unchanged when the customer edits their current email. Define what the fact means before treating every repeated value as an anomaly.

**Transfer:** if each membership stores `team_name`, which table owns it? `teams(team_id, name)` owns a current name because it depends only on team_id, while membership role still depends on both IDs. If a report deliberately stores the team's name at invitation time, that field is a snapshot with a different meaning and update policy.

### When to Denormalize

Normalization reduces redundancy, but sometimes you need to **denormalize** for performance:

- **Precomputed counts**: `user.post_count` column instead of counting every time
- **Denormalized snapshots**: `orders.customer_name` captures the name at order time (immutable history)
- **Read-heavy analytics**: flattened tables avoid expensive JOINs

> Rule: normalize first, denormalize only when you have a measured performance problem.

---

## 8. PostgreSQL vs SQLite — Choosing the Right Tool

### PostgreSQL

Full-featured client/server database. Use it when several processes or hosts write concurrently,
when operations need PostgreSQL-specific types or indexes, or when replication and centralized
operations matter.

| Feature | Detail |
|---------|--------|
| Concurrency | Multi-version concurrency control (MVCC) — readers and writers usually proceed against different row versions |
| Data types | Rich: `JSONB`, arrays, `UUID`, `INET`, `TSVECTOR`, ranges |
| Indexes | B-tree and Hash, plus generalized inverted indexes (GIN), generalized search trees (GiST), and block range indexes (BRIN) for specialized lookups |
| Full-text search | Built-in `tsvector` + `tsquery` |
| Replication | Streaming replication, logical replication (see §Replication and Read Replicas below) |
| Extensions | `pgvector` (embeddings), `PostGIS` (geospatial), `pg_trgm` (fuzzy search) |
| Max DB size | Capacity depends on storage, maintenance windows, table/index growth, and workload |

**When to use PostgreSQL**: it is the default for multi-instance web services, write-heavy APIs,
and centrally operated data. It is not automatically better for every embedded or single-host use.

### SQLite

File-based, zero-configuration, serverless. The database is a single `.db` file.

```python
# Entire database is one file
"sqlite:///./local.db"
"sqlite+aiosqlite:///./local.db"  # async
":memory:"                         # in-memory, lost when process ends
```

| Feature | Detail |
|---------|--------|
| Setup | None — just a file |
| Concurrency | One writer at a time; WAL allows readers alongside that writer |
| Data types | Dynamic typing by default; optional STRICT tables enforce supported declared types |
| Max size | Configured page-size/page-count limits; practical capacity depends on workload and operations |
| Network | No — must be on same machine |

**When to use SQLite**:
- Local development (no Docker needed)
- Unit and integration tests (fast, clean state per test)
- CLI tools, scripts, small embedded apps
- Single-host, low-write production services where operational simplicity matters more than horizontal write concurrency

Move to a client/server database when multiple hosts must share the database, sustained concurrent
writes cause lock waits, or you need centralized access control, replication, or failover.

### The SQLite-to-PostgreSQL Switch

During development you might use SQLite, then switch to PostgreSQL for production. The switch is mostly painless with SQLAlchemy, but watch out for:

| Difference | SQLite | PostgreSQL |
|-----------|--------|------------|
| Boolean | `0`/`1` integers | Native `BOOL` |
| Auto-increment | `INTEGER PRIMARY KEY` | `SERIAL` or `GENERATED ALWAYS AS IDENTITY` |
| `LIKE` operator | Case-insensitive for ASCII | Case-sensitive (use `ILIKE`) |
| `JSON` type | Stored as text | Native `JSONB` with indexing |

**Recommendation**: use PostgreSQL in development when the application depends on PostgreSQL
semantics, extensions, or concurrent behavior; a container keeps that environment reproducible.
Use SQLite deliberately for isolated tests, local tools, and bounded single-host workloads whose
behavior does not need to match PostgreSQL.

---

## 9. Schemas — Namespacing Tables

In PostgreSQL, a **schema** is a namespace inside a database. Think of it like a folder.

```
database: myapp
├── schema: public (default)
│   ├── users
│   ├── posts
│   └── comments
├── schema: analytics
│   ├── events
│   └── sessions
└── schema: auth
    ├── tokens
    └── sessions
```

```sql
-- Access a table in a specific schema
SELECT * FROM analytics.events;

-- Create a schema
CREATE SCHEMA analytics;

-- Set the search path (which schemas to check by default)
SET search_path = public, analytics;
```

In most Python apps with a single database, you only use `public`. Schemas become useful for:
- Multi-tenant apps (one schema per tenant)
- Logical separation of concerns (auth, core, reporting)
- Preventing name collisions when using multiple modules

---

## 10. Advanced PostgreSQL Features

The foundation path ends after normalization. The remaining sections are optional lookup and operational continuations. Specialized SQL below is an excerpt requiring its named tables and columns.

### PostgreSQL Data Types You Will Actually Use

| Type | Use case | Example |
|------|----------|---------|
| `INTEGER` / `BIGINT` | Whole numbers, IDs | `42`, `-7` |
| `SERIAL` / `BIGSERIAL` | Auto-increment integers | Primary keys |
| `UUID` | Universally unique IDs | `gen_random_uuid()` |
| `VARCHAR(n)` | Short strings with max length | Emails, names |
| `TEXT` | Unlimited text | Content, descriptions |
| `BOOLEAN` | True/false | `TRUE`, `FALSE` |
| `NUMERIC(p,s)` | Exact decimals | Money: `NUMERIC(10,2)` |
| `FLOAT` / `DOUBLE PRECISION` | Approximate decimals | Coordinates, percentages |
| `TIMESTAMP` | Local date and clock time without an identified instant | Store closing time in a known business timezone |
| `TIMESTAMPTZ` | An instant displayed in the session timezone; original zone name is not retained | Creation times, deadlines tied to an instant |
| `DATE` | Date only | Birthdays, due dates |
| `JSONB` | Binary JSON, indexable | Flexible data, config, events |
| `ARRAY` | Array of a type | `INTEGER[]`, `TEXT[]` |
| `INET` | IP address | Client IPs |
| `TSVECTOR` | Full-text search | Search indexes |

A timezone-aware Python `datetime` identifies an instant through its UTC offset; a naive one does not. PostgreSQL `TIMESTAMPTZ` normalizes instants and displays them in the current session timezone. Store an IANA zone name separately when a recurring local schedule needs daylight-saving rules. For example, `2026-01-01 12:00+02` and `2026-01-01 10:00+00` identify the same instant. [Date/time types](https://www.postgresql.org/docs/current/datatype-datetime.html).

### JSONB — PostgreSQL's Superpower

`JSONB` stores a decomposed binary representation that avoids reparsing JSON text. It is queryable and **indexable**, but indexes must be created explicitly; compression depends on PostgreSQL storage decisions. The following are independent schema/query excerpts, assuming an `events(payload JSONB)` table:

```sql
-- Querying inside JSONB
SELECT * FROM events WHERE payload->>'event_type' = 'login';

-- Index a specific key
CREATE INDEX ON events ((payload->>'user_id'));

-- GIN index for arbitrary key queries
CREATE INDEX ON events USING GIN (payload);
```

Use `JSONB` when:
- Data is schemaless or highly variable (audit logs, config, metadata)
- You need to store arbitrary key-value pairs
- You want to avoid a schema migration for every new field

Avoid `JSONB` when the data is structured and you need to filter/join on its contents frequently — ordinary typed columns make constraints, joins, and statistics easier to express. Compare actual plans and matched workloads before claiming a speed advantage. [PostgreSQL JSON types](https://www.postgresql.org/docs/current/datatype-json.html).

---



### Common Table Expressions (CTEs)

CTEs (`WITH` clauses) let you name and reuse subqueries. They make complex queries readable.

```sql
-- Readable multi-step query
WITH active_users AS (
    SELECT id, name FROM users WHERE is_active = TRUE
),
user_post_counts AS (
    SELECT author_id, COUNT(*) AS post_count FROM posts GROUP BY author_id
)
SELECT u.name, COALESCE(c.post_count, 0) AS post_count
FROM active_users u
LEFT JOIN user_post_counts c ON c.author_id = u.id
ORDER BY post_count DESC;
```

### Window Functions

Window functions compute a value for each row based on a "window" of related rows, without collapsing them like `GROUP BY` does.

```sql
-- Rank users by post count within each department
SELECT
    name,
    department,
    post_count,
    RANK() OVER (PARTITION BY department ORDER BY post_count DESC) AS rank_in_dept
FROM user_stats;

-- Running total
SELECT
    created_at,
    amount,
    SUM(amount) OVER (ORDER BY created_at) AS running_total
FROM transactions;

-- Previous row's value
SELECT
    created_at,
    temperature,
    LAG(temperature) OVER (ORDER BY created_at) AS prev_temp
FROM sensor_readings;
```

### JSONB Operators

```sql
-- Field access (returns text)
SELECT payload->>'user_id' FROM events;

-- Nested field access
SELECT payload->'metadata'->>'source' FROM events;

-- Contains (subset check)
SELECT * FROM events WHERE payload @> '{"event_type": "login"}';

-- Has key
SELECT * FROM events WHERE payload ? 'error_code';

-- Path exists
SELECT * FROM events WHERE payload #>> '{metadata,source}' = 'web';
```

### Full-Text Search

```sql
-- Create a tsvector column
ALTER TABLE posts ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || content)) STORED;

CREATE INDEX ON posts USING GIN (search_vector);

-- Search
SELECT title FROM posts
WHERE search_vector @@ to_tsquery('english', 'python & database');

-- Ranked search
SELECT title, ts_rank(search_vector, query) AS rank
FROM posts, to_tsquery('english', 'python & database') query
WHERE search_vector @@ query
ORDER BY rank DESC;
```

---


## Quick Reference

### Useful psql Commands

```bash
\l                    # list databases
\c mydb               # connect to database
\dt                   # list tables
\dt+                  # list tables with sizes
\d users              # describe table
\di                   # list indexes
\df                   # list functions
\timing               # toggle query timing
\x                    # toggle expanded output
EXPLAIN ANALYZE ...;  # query plan + actual execution stats
```

### PostgreSQL System Queries

```sql
-- Active connections
SELECT * FROM pg_stat_activity;

-- Table sizes
SELECT relname, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC;

-- Unused indexes
SELECT * FROM pg_stat_user_indexes WHERE idx_scan = 0;

-- Slow queries (requires pg_stat_statements extension)
SELECT query, calls, mean_exec_time FROM pg_stat_statements
ORDER BY mean_exec_time DESC LIMIT 20;
```

---

## Replication and Read Replicas

Ordinary PostgreSQL physical replication uses the **Write-Ahead Log (WAL)**. Every change the primary makes is first written to the WAL; replicas stream that log and apply it. Understanding this mechanism is worth the five minutes:

### Physical streaming replication (ordinary PostgreSQL standbys)

The primary ships WAL records to the replica continuously. In the default asynchronous setup, the
primary can acknowledge locally before a standby confirms receipt. Synchronous replication requires
both `synchronous_standby_names` to select eligible standbys and a `synchronous_commit` level that
waits for the required remote acknowledgement. Stronger remote acknowledgement reduces the data-loss
window but adds standby/network latency to commits; `synchronous_commit=on` alone does not select a
synchronous standby.

**Replication lag** is the time between a write committing on the primary and being visible on a replica. On a healthy system it's sub-second; under heavy write load it can grow to seconds or minutes. Monitoring lag is non-negotiable:

```sql
-- On the primary — shows lag per replica
SELECT client_addr, state, write_lag, flush_lag, replay_lag
  FROM pg_stat_replication;

-- On the replica — age of the last replayed transaction, not current backlog
SELECT now() - pg_last_xact_replay_timestamp() AS lag;
```

The replay-timestamp age grows while an idle primary produces no transactions, even if the replica is caught up. It cannot by itself identify backlog or its cause. Compare primary WAL LSN with replica receive/replay LSN (in the same observation window), monitor transport and replay separately, and use a heartbeat transaction when the service needs an elapsed-time freshness bound. The primary lag intervals describe acknowledgement delay and may become NULL during idleness; they do not predict catch-up time. Diagnose sustained WAL-byte backlog alongside network, disk, CPU, and long replica queries before sizing hardware. [Replication statistics](https://www.postgresql.org/docs/current/monitoring-stats.html).

### Reading from replicas

The business reason to have replicas: **offload read traffic**. Reporting queries, dashboard aggregations, non-critical reads — send them to a replica so the primary can focus on writes.

```python
# Separate engines, separate pools
write_engine = create_async_engine(PRIMARY_URL, pool_size=20)
read_engine = create_async_engine(REPLICA_URL, pool_size=30)

# Dependencies pick based on intent
async def get_write_session():
    async with async_sessionmaker(write_engine)() as s:
        yield s

async def get_read_session():
    async with async_sessionmaker(read_engine)() as s:
        yield s
```

**Rule of thumb for safety:** do not read from a replica immediately after writing to the primary if the user expects to see their write. The 200ms of replication lag is plenty to produce "I just saved this and it's gone" bug reports. Options:
- Read the user's own writes from the primary (tag "my own data" queries as writable).
- Use a read-your-writes cache (write goes to primary + cache; reads check cache first).
- Accept the UX and clearly indicate "this may take a moment to appear."

### Logical replication

Logical replication replays changes at the **row level**, not WAL block level. This lets you replicate subsets of tables, replicate across Postgres versions, or feed the changes to a non-Postgres consumer (Kafka, Elasticsearch) via Debezium. Slower and more complex than streaming replication; use when you need the flexibility, not when you just want a hot standby.

---

## Aurora is a different replica topology

An Aurora PostgreSQL writer and its in-region Aurora Replicas share the cluster storage volume. Adding a reader does not create an ordinary independent PostgreSQL data directory maintained by the WAL receiver/replay model above. Readers still have instance-local state and visibility/freshness concerns; use Aurora-specific lag/failover metrics and test read-after-write requirements rather than assuming shared storage makes every read immediately current. Logical replication and cross-region Aurora global databases are separate mechanisms. [AWS Aurora replication](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/AuroraPostgreSQL.Replication.html), checked 2026-10-30.
