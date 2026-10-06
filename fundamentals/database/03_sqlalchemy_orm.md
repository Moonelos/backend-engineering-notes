# SQLAlchemy ORM — Core Concepts and Sync Usage

<!-- length-justification: This is the canonical synchronous SQLAlchemy ORM reference; mappings, session identity, relationships, loading, transactions, and CRUD remain together because their behavior depends on one unit-of-work model. -->

> **Who this is for**: Python engineers who understand relational tables and SQL and want to use SQLAlchemy's synchronous ORM without hiding transaction or loading behavior.

> **What is an ORM?** An Object-Relational Mapper lets you interact with a database using Python objects instead of raw SQL. SQLAlchemy is Python's most powerful ORM and the de-facto standard for production Python backends.

> **Key insight**: The ORM maps rows to objects, but the session—not the model instance—is the unit that owns identity, pending changes, and the transaction boundary.

---

## 1. What Is an ORM?

An ORM maps database tables to Python classes and rows to instances:

```
Database Table          Python Class
─────────────────       ─────────────────────
users table       ←→   class User(Base)
column: id        ←→   id: Mapped[int]
column: email     ←→   email: Mapped[str]
row: (1, a@b.com) ←→   User(id=1, email='a@b.com')
```

Instead of writing:

```python
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
row = cursor.fetchone()
user = {"id": row[0], "email": row[1], "name": row[2]}
```

The smallest synchronous mapping is executable with SQLite and requires no external service:

```python
from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)


engine = create_engine("sqlite+pysqlite:///:memory:")
Base.metadata.create_all(engine)

with Session(engine) as session:
    session.add(User(email="alice@example.com"))
    session.commit()
    user = session.scalar(select(User).where(User.email == "alice@example.com"))
    print(user.id, user.email)

# 1 alice@example.com
```

The engine owns database connectivity, the metadata creates the schema, and `Session` owns one unit
of work. If the table setup is missing, the first statement fails with `no such table: users`.
Async engines and sessions are a separate implementation path in
[Async SQLAlchemy](04_async_sqlalchemy.md).

### See add, flush, commit, and rollback as different transitions

Continue the minimal SQLite program above **in the same process**, after its initial commit. Run this extension to observe a failed flush and recovery:

```python
from sqlalchemy import inspect, func
from sqlalchemy.exc import IntegrityError

with Session(engine) as session:
    bob = User(email="bob@example.com")
    print(inspect(bob).transient, bob.id)  # True None
    session.add(bob)
    print(inspect(bob).pending, bob.id)    # True None: no INSERT yet
    session.flush()
    print(inspect(bob).persistent, bob.id) # True 2: INSERT, still uncommitted
    session.add(User(email="alice@example.com"))
    try:
        session.flush()                  # duplicate email; transaction fails
    except IntegrityError:
        session.rollback()               # undo Bob too; reset Session state
    print(session.scalar(select(func.count()).select_from(User)))  # 1

with Session(engine) as session:
    alice1 = session.get(User, 1)
    alice2 = session.get(User, 1)
    print(alice1 is alice2)               # True: identity map
```

`add()` puts a new object in the pending set. `flush()` converts pending changes into SQL inside the current transaction and retrieves generated identifiers. It does not commit: another PostgreSQL connection cannot see that row yet, and rollback removes it even though Python already received an ID. Generated sequence IDs may have gaps after rollback; they are identities, not a count of successful transactions. A failed flush requires `session.rollback()` before the session can execute more work. Catching the exception does not reset transaction state.

| State | Database action | Independent connection sees the new row? |
|-------|-----------------|------------------------------------------|
| Transient, before add | None | No |
| Pending, after add | Queued in session | No |
| Persistent after flush | INSERT executed inside transaction | No |
| Committed | Commit makes the transaction durable | Yes, subject to reader snapshot |
| Rolled back | Uncommitted writes discarded | No |
| Detached after close | Session no longer manages instance | Only if previously committed |

The identity map keeps one managed object per primary key in a session. It is not a cross-process cache: another session has different Python objects, and outside commits need an explicit refresh or expiration if the current object is stale. By default commit expires attributes; accessing them in an open sync session can SELECT again. After close, expired attributes cannot reload. Extract the response fields you need while the session is open, or intentionally use `expire_on_commit=False` and accept that retained values may be stale. [Session basics](https://docs.sqlalchemy.org/en/20/orm/session_basics.html).

A normal query triggers **autoflush** first, so a new pending user can become visible to that transaction's query without an explicit flush call. With `autoflush=False`, a database query cannot find a still-pending row: flush explicitly before querying it. `commit()` flushes regardless of the autoflush setting. Temporarily use `session.no_autoflush` when assembling an object graph that is not yet valid; it postpones SQL, not constraint enforcement.

### Let one business operation own the transaction

Creating a user and their first post is one operation. If a user helper commits first and a post helper fails next, rollback cannot undo the first commit. Helpers should queue or flush work; their caller commits once. Here is a separate complete SQLite program (save as `atomic_user_post.py`):

```python
from sqlalchemy import CheckConstraint, ForeignKey, String, create_engine, event, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.exc import IntegrityError

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)

class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (CheckConstraint("length(title) > 0", name="ck_post_title"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

engine = create_engine("sqlite+pysqlite:///:memory:")
@event.listens_for(engine, "connect")
def enable_foreign_keys(connection, record):
    connection.execute("PRAGMA foreign_keys=ON")
Base.metadata.create_all(engine)

def add_user(session: Session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    session.flush()  # get id; caller still owns commit
    return user

def add_post(session: Session, user: User, title: str) -> None:
    session.add(Post(author_id=user.id, title=title))

for title in ("", "Hello"):
    try:
        with Session(engine) as session, session.begin():
            user = add_user(session, "alice@example.com")
            add_post(session, user, title)
    except IntegrityError:
        print("rolled back")
    with Session(engine) as session:
        print(session.scalar(select(func.count()).select_from(User)),
              session.scalar(select(func.count()).select_from(Post)))
# rolled back
# 0 0
# 1 1
```

The empty title fails when the transaction exit flushes, and the exception leaves the `begin()` context, which rolls back the earlier successful user INSERT. The second attempt commits both. Each loop iteration creates a fresh session, so no failed transaction state leaks into the retry. A Session is mutable transaction state: keep one owner per operation; do not share it between threads or concurrent tasks.

**Transfer:** create two posts after flushing the user, with the second title empty. Neither post nor user persists because every flush belongs to the same outer transaction. If a helper commits after the first post, the user and first post survive the second failure. A savepoint can intentionally isolate a recoverable optional step, but creates a different business guarantee; teach it as a deliberate policy rather than silently swallowing failure.

### ORM Trade-offs

| Benefit | Cost |
|---------|------|
| Less SQL boilerplate | Learning curve |
| Python type safety | Abstraction can hide bad queries |
| Relationship navigation | N+1 queries if you're not careful |
| Automatic migrations with Alembic | Some PostgreSQL features need raw SQL |
| Testability (isolated sessions) | Mapping and identity bookkeeping that must be measured on hot paths |
| Portable across databases | Can obscure what SQL runs |

### SQLAlchemy Architecture

SQLAlchemy has two layers:

```
SQLAlchemy ORM           ← High-level: mapped classes, sessions, relationships
      ↓
SQLAlchemy Core          ← Mid-level: Table, select(), insert() — generates SQL
      ↓
Driver (asyncpg/psycopg) ← Low-level: speaks to PostgreSQL
      ↓
PostgreSQL
```

You can use Core without the ORM (handwritten SQL with Python constructs) or bypass Core entirely with raw SQL through the driver. In most apps you use all three layers together.

---

## 2. Installation

```bash
# Synchronous baseline used in this note
pip install sqlalchemy

# PostgreSQL synchronous driver
pip install sqlalchemy "psycopg[binary]"

# Alembic for migrations
pip install alembic
```

Async driver selection, `MissingGreenlet`, and explicit relationship loading belong to
[Async SQLAlchemy](04_async_sqlalchemy.md), after the synchronous unit-of-work model is established.

---

## 3. Sync SQLAlchemy — Engine and Session

The lifecycle above works with a real PostgreSQL connection too. An installed psycopg3 driver needs the explicit `postgresql+psycopg://` scheme; bare `postgresql://` can select psycopg2 and fail with ModuleNotFoundError when only psycopg3 was installed. This configuration excerpt requires psycopg and a supplied DATABASE_URL. It uses the richer mapping reference below for later CRUD and loading snippets; finish that mapping before executing those snippets:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

DATABASE_URL = "postgresql+psycopg://user:pass@localhost:5432/mydb"

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False,  # True logs SQL
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=True,  # queries flush pending changes; flush is still not commit
    expire_on_commit=True,  # sync: True is fine (lazy reloads work)
)
```

### Using Sync Sessions

```python
# Context manager (always use this)
with SessionLocal() as session:
    user = session.get(User, 1)
    print(user.email)

# Or manually
session = SessionLocal()
try:
    user = session.get(User, 1)
    session.commit()
finally:
    session.close()
```

## 4. SQLAlchemy 2.0 Declarative Style

SQLAlchemy 2.0 (released 2023) introduced a cleaner, type-annotated style. Always use this for new projects.

### Defining Models

This larger mapping is a separate program from the minimal examples: define a fresh Base and use its complete schema. Persisted creation times explicitly use `DateTime(timezone=True)` for PostgreSQL instants. Ordinary declarative `default=True` runs at INSERT/flush, so `User(...).is_active` is initially None unless the constructor supplies a value; after flush it is True. SQLite does not fully model PostgreSQL timezone storage; use PostgreSQL to verify aware datetime round trips.

```python
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Text, ForeignKey, Numeric, DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared base for all models. Holds metadata for Alembic."""
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    posts: Mapped[list["Post"]] = relationship(
        back_populates="author", cascade="all, delete-orphan",
        passive_deletes=True, lazy="raise",
    )
    profile: Mapped[Optional["Profile"]] = relationship(
        back_populates="user", cascade="all, delete-orphan",
        passive_deletes=True, lazy="raise",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    published: Mapped[bool] = mapped_column(default=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    author: Mapped["User"] = relationship(back_populates="posts", lazy="raise")
    tags: Mapped[list["Tag"]] = relationship(
        secondary="post_tags", back_populates="posts", passive_deletes=True, lazy="raise"
    )


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    bio: Mapped[Optional[str]] = mapped_column(Text)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))

    user: Mapped["User"] = relationship(back_populates="profile", lazy="raise")


# Many-to-many association table
from sqlalchemy import Table, Column

post_tags = Table(
    "post_tags",
    Base.metadata,
    Column("post_id", ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)

    posts: Mapped[list["Post"]] = relationship(
        secondary="post_tags", back_populates="tags", passive_deletes=True, lazy="raise"
    )
```

### Column Annotation Patterns

| Pattern | Column type | Nullable |
|---------|------------|---------|
| `Mapped[int]` | INTEGER NOT NULL | No |
| `Mapped[str]` | TEXT NOT NULL | No |
| `Mapped[Optional[int]]` | INTEGER NULL | Yes |
| `Mapped[Optional[str]]` | TEXT NULL | Yes |
| `Mapped[bool]` | BOOLEAN NOT NULL | No |
| `Mapped[datetime]` | TIMESTAMP NOT NULL | No |

### `mapped_column` Options

```python
# Primary key (auto-increment)
id: Mapped[int] = mapped_column(primary_key=True)

# String with max length
email: Mapped[str] = mapped_column(String(255))

# Python-side INSERT default (applied during flush if no value was supplied)
is_active: Mapped[bool] = mapped_column(default=True)

# Server-side default (SQL expression, evaluated when row is inserted)
created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

# Unique constraint
email: Mapped[str] = mapped_column(unique=True)

# Index
email: Mapped[str] = mapped_column(index=True)

# Both
email: Mapped[str] = mapped_column(unique=True, index=True)

# Foreign key
author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

# Custom column name in DB
first_name: Mapped[str] = mapped_column("first_name", String(50))

# Not mapped to a column (just a Python attribute)
# Use @property instead

# Check constraint
from sqlalchemy import CheckConstraint
__table_args__ = (CheckConstraint("age >= 0", name="ck_users_age"),)
```

### Advanced Column Types

```python
import uuid
from sqlalchemy import String, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

# UUID primary key
id: Mapped[uuid.UUID] = mapped_column(
    UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
)

# JSONB — avoid the attribute name `metadata`, it's reserved on DeclarativeBase
payload: Mapped[dict] = mapped_column(JSONB, default=dict)

# Array
tags: Mapped[list[str]] = mapped_column(ARRAY(String))

# Numeric (exact decimal for money)
price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
```

`JSONB` and `ARRAY` are PostgreSQL-specific — import them from `sqlalchemy.dialects.postgresql`, not the top-level `sqlalchemy` package.

### Table-Level Constraints and Indexes

```python
from sqlalchemy import UniqueConstraint, Index, text

# Extension to the complete mapping above; define the referenced table too.
class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))

class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        # Composite unique constraint
        UniqueConstraint("user_id", "team_id", name="uq_membership_user_team"),
        # Partial index: represent the SQL predicate explicitly with text().
        Index("ix_active_memberships", "user_id", postgresql_where=text("is_active = TRUE")),
        # Multi-column index
        Index("ix_memberships_team_user", "team_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"))
    is_active: Mapped[bool] = mapped_column(default=True)
```

---

## 5. Relationship Types

### One-to-Many

One user has many posts:

```python
class User(Base):
    posts: Mapped[list["Post"]] = relationship(back_populates="author", lazy="raise")

class Post(Base):
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    author: Mapped["User"] = relationship(back_populates="posts", lazy="raise")
```

### One-to-One

One user has one profile:

```python
class User(Base):
    profile: Mapped[Optional["Profile"]] = relationship(
        back_populates="user", lazy="raise"
    )

class Profile(Base):
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    user: Mapped["User"] = relationship(back_populates="profile", lazy="raise")
```

### Many-to-Many

Posts have multiple tags; tags belong to multiple posts:

```python
post_tags = Table(
    "post_tags",
    Base.metadata,
    Column("post_id", ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

class Post(Base):
    tags: Mapped[list["Tag"]] = relationship(
        secondary="post_tags", back_populates="posts", lazy="raise"
    )

class Tag(Base):
    posts: Mapped[list["Post"]] = relationship(
        secondary="post_tags", back_populates="tags", lazy="raise"
    )
```

### `lazy` Options

| Value | Behavior | Use in async |
|-------|----------|-------------|
| `"select"` | Lazy load on attribute access | ❌ Raises MissingGreenlet |
| `"raise"` | Raises error on attribute access | ✅ Forces explicit loading |
| `"raise_on_sql"` | Raises only if SQL would be issued | ✅ Safe |
| `"selectin"` | Always loads via SELECT IN | ✅ Auto-eager (use carefully) |
| `"joined"` | Always loads via JOIN | ✅ Auto-eager (use carefully) |
| `"subquery"` | Loads via subquery | ✅ Auto-eager |
| `"dynamic"` | Returns a Query object (legacy; not supported on async) | ❌ Don't use |
| `"write_only"` | Write-only relationship | ✅ For large collections |

The mapping below deliberately uses `lazy="raise"` to expose unexpected I/O. In a synchronous session `lazy="select"` can issue SQL on access; under ordinary async attribute access that implicit I/O cannot be awaited. [04](04_async_sqlalchemy.md) owns the async loading choices. Load explicitly with `selectinload()` or `joinedload()` when needed.

### Coordinate ORM deletion with database deletion

The complete model uses both `ForeignKey(..., ondelete="CASCADE")` and `relationship(cascade="all, delete-orphan", passive_deletes=True)`. These configure different actors. ORM delete cascade deletes loaded child objects when `session.delete(user)` is flushed. Database CASCADE deletes matching rows even when a raw SQL client deletes the parent. `passive_deletes=True` lets the database handle **unloaded** collections instead of loading them or assigning NULL to a required foreign key. It does not disable ORM work for loaded children.

Without ORM delete cascade, SQLAlchemy normally tries to detach child rows by setting their foreign keys to NULL, which violates this model's NOT NULL author_id. An ON DELETE clause alone does not prevent that ORM action. Profile uses the same coordinated policy; deleting posts also deletes association rows, but must not delete shared Tag objects. Bidirectional delete cascade across many-to-many relationships could traverse and delete an entire graph, so the association foreign keys cascade without cascading deletion of the tags themselves.

`delete-orphan` also marks a child deleted when it is removed from its owning collection. Use it when the child's lifetime belongs to exactly one parent. Soft deletion needs a different policy: changing a deleted flag is an UPDATE, so neither ORM delete cascade nor database ON DELETE fires. SQLite tests must enable foreign keys; PostgreSQL enforces them by default. [SQLAlchemy cascades](https://docs.sqlalchemy.org/en/20/orm/cascades.html).

---

### Sync CRUD

These helpers participate in the caller's transaction and never commit it. A service calls them inside `with SessionLocal.begin() as session:`; one successful exit commits every change, and an exception rolls them all back. Returning an ORM object does not itself make it durable.

```python
from typing import Optional
from sqlalchemy import select

# Create
def create_user(session: Session, email: str, name: str) -> User:
    user = User(email=email, name=name)
    session.add(user)
    session.flush()  # retrieve generated values without ending the caller transaction
    return user

# Read by primary key (checks identity map first)
def get_user(session: Session, user_id: int) -> Optional[User]:
    return session.get(User, user_id)

# Read with filter
def get_user_by_email(session: Session, email: str) -> Optional[User]:
    stmt = select(User).where(User.email == email)
    return session.execute(stmt).scalar_one_or_none()

# Read many
def list_active_users(session: Session, limit: int = 20) -> list[User]:
    stmt = select(User).where(User.is_active == True).limit(limit).order_by(User.id)
    return list(session.execute(stmt).scalars().all())

# Update
def deactivate_user(session: Session, user_id: int) -> bool:
    user = session.get(User, user_id)
    if not user:
        return False
    user.is_active = False
    return True

# Delete
def delete_user(session: Session, user_id: int) -> bool:
    user = session.get(User, user_id)
    if not user:
        return False
    session.delete(user)
    return True
```

### Sync with Relationships

```python
from sqlalchemy.orm import selectinload, joinedload

# selectinload (one parent query plus batched child queries; two for this one-user case)
def get_user_with_posts(session: Session, user_id: int) -> Optional[User]:
    stmt = (
        select(User)
        .options(selectinload(User.posts))
        .where(User.id == user_id)
    )
    return session.execute(stmt).scalar_one_or_none()

# joinedload (1 query with JOIN, for many-to-one / one-to-one)
def get_post_with_author(session: Session, post_id: int) -> Optional[Post]:
    stmt = (
        select(Post)
        .options(joinedload(Post.author))
        .where(Post.id == post_id)
    )
    return session.execute(stmt).scalar_one_or_none()
```

---

## 6. SQLAlchemy Core — Queries Without the ORM

SQLAlchemy Core lets you build SQL queries in Python without full ORM mapping. Useful when you want SQL control but still want Python's query building:

```python
from sqlalchemy import select, insert, update, delete, text, func

# SELECT
stmt = (
    select(User.id, User.email, func.count(Post.id).label("post_count"))
    .join(Post, Post.author_id == User.id, isouter=True)
    .where(User.is_active == True)
    .group_by(User.id, User.email)
    .order_by(func.count(Post.id).desc())
    .limit(10)
)
result = session.execute(stmt)
rows = result.all()  # list of Row objects (not ORM instances)

# Raw SQL with text()
stmt = text("SELECT id, email FROM users WHERE email = :email")
result = session.execute(stmt, {"email": "alice@example.com"})
row = result.first()

# INSERT with Core
stmt = insert(User).values(email="alice@example.com", name="Alice").returning(User.id)
result = session.execute(stmt)
user_id = result.scalar_one()
session.commit()

# UPDATE with Core
stmt = update(User).where(User.id == 1).values(name="Alice Smith").returning(User.id)
result = session.execute(stmt)
session.commit()

# DELETE with Core
stmt = delete(User).where(User.is_active == False).returning(User.id)
result = session.execute(stmt)
deleted_ids = result.scalars().all()
session.commit()
```

---

## Migrations and application integration continue separately

`Base.metadata.create_all()` creates missing tables for the disposable examples; it does not evolve an existing deployed schema. [Alembic](06_alembic.md) owns versioned schema changes, autogenerate review, sync/async env.py, and safe nullable-column/backfill/constraint rollout. Keep named constraints and ensure every model module is imported before Alembic reads `Base.metadata`. CHECK comparison behavior depends on the Alembic version and opt-in extension; use the documented configuration in 06 rather than assuming every named CHECK is detected by default.

[Async SQLAlchemy](04_async_sqlalchemy.md) owns the FastAPI lifespan, async session dependency, and async repository integration. For a synchronous application, keep one engine/session factory in `database.py`, mappings in `models/`, and transaction-owning business operations outside reusable CRUD helpers. Importing a model module registers its Table in metadata; a model that has never been imported cannot appear in autogenerate's comparison. Migration implementation remains a separate learning path so it does not interrupt understanding session state.

---

## 7. Common ORM Pitfalls

### The N+1 Problem

If a mapping instead uses `lazy="select"`, selecting N users and then accessing each unloaded posts collection emits an extra SELECT per user: 1 + N queries. The guard used here prevents that pattern before it silently grows. To measure the contrast, use a separate fresh session for each query and temporarily set the demonstration mapping to `lazy="select"`; a previously loaded collection would hide the extra queries.

```python
# With this note's lazy="raise" mapping, unloaded access fails immediately.
users = session.execute(select(User)).scalars().all()
for user in users:
    print(user.posts)  # InvalidRequestError: explicitly load the relationship

# Two queries for one relationship and one parent-key batch; larger sets batch.
users = session.execute(
    select(User).options(selectinload(User.posts))
).scalars().all()
for user in users:
    print(user.posts)  # already loaded
```

### Identity Map Confusion

SQLAlchemy's session maintains an **identity map** — one Python object per row (by primary key). If you load the same row twice, you get the same object:

```python
user1 = session.get(User, 1)
user2 = session.get(User, 1)
assert user1 is user2  # True — same object
```

This is efficient (no redundant queries) but can cause confusion if you expect two independent copies.

### Detached Instance Error

With `lazy="select"`, an unloaded relationship needs the owning session and raises DetachedInstanceError after close. With this note's `lazy="raise"` guard, the failure is InvalidRequestError even while the session is open. Closing also detaches objects; already loaded, unexpired data remains ordinary Python data. The following snippets assume user 1 exists:

```python
# ❌ Session closed before accessing relationship
with SessionLocal() as session:
    user = session.get(User, 1)

print(user.posts)  # InvalidRequestError with lazy="raise": unloaded access is forbidden

# ✅ Load everything you need within the session
with SessionLocal() as session:
    user = session.execute(
        select(User).options(selectinload(User.posts)).where(User.id == 1)
    ).scalar_one_or_none()

print(user.posts)  # works — already loaded
```

### SQLite Differences to Watch For

If you develop with SQLite and deploy with PostgreSQL:

```python
# SQLite doesn't enforce foreign keys by default
# Enable it explicitly for tests
from sqlalchemy import event

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```
