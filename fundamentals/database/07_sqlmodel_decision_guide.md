# SQLModel: When One Model Can Serve Two Boundaries

> **Who this is for**: FastAPI engineers deciding whether SQLModel's combined Pydantic and
> SQLAlchemy surface is simpler than direct SQLAlchemy models plus separate API schemas.

SQLModel is a thin integration over Pydantic and SQLAlchemy. Start with it for small, CRUD-shaped
services where shared field declarations remove meaningful duplication. Prefer direct SQLAlchemy
when advanced mappings, dialect features, or independent API/database evolution dominate the work.

> **Key insight**: Sharing field declarations removes syntax, not boundaries; table state and API
> input still need distinct model roles whenever their allowed fields differ.

---

## 1. Run one table, write, and read

This complete baseline uses an in-memory SQLite database, so its only prerequisite is
`pip install sqlmodel`:

```python
from sqlmodel import Field, Session, SQLModel, create_engine, select


class Order(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    description: str


engine = create_engine("sqlite://")
SQLModel.metadata.create_all(engine)

with Session(engine) as session:
    session.add(Order(description="keyboard"))
    session.commit()
    order = session.exec(select(Order)).one()
    print(order.id, order.description)

# 1 keyboard
```

`table=True` registers `Order` as a SQLAlchemy table mapping. The engine owns database connectivity,
`SQLModel.metadata.create_all()` creates registered tables, and the session owns the unit of work.

**Success signal:** the program prints `1 keyboard`. `no such table: order` usually means model
modules were not imported before `create_all()` ran. In production, use Alembic migrations rather
than `create_all()` to evolve an existing schema.

---

## 2. Table and data models remain different roles

Accepting a table model directly at an API boundary can expose database-owned fields such as primary
keys. Define a data model for client input and let the table model own persistence. This is a
separate example in a fresh process, with the `Field` and `SQLModel` imports from the first
example; do not redefine its table on the existing metadata:

```python
class OrderCreate(SQLModel):
    description: str


class Order(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    description: str


payload = OrderCreate.model_validate({"description": "keyboard"})
row = Order.model_validate(payload)
print(payload.model_dump(), row.id)
# {'description': 'keyboard'} None
```

The duplicated `description` line is intentional boundary design: the client may choose it, while
the database chooses `id`. Update and public-response models often diverge further through optional
fields, server-only columns, and redaction.

> **Core:** `table=True` answers “is this persisted?” It does not answer “may a client send or see
> every field?”

---

## 3. The decision turns on how far the boundaries diverge

| Scenario | Initial choice | Why |
|----------|----------------|-----|
| Small CRUD service, simple relationships | SQLModel | Shared declarations reduce glue while retaining sessions and SQLAlchemy expressions |
| Separate create/update/read payloads | SQLModel can still fit | Use non-table data models; expect some deliberate duplication |
| Complex joins, inheritance, events, custom mappings | Direct SQLAlchemy | Its full mapping vocabulary is the main tool rather than an implementation detail |
| Heavy PostgreSQL/dialect-specific modeling | Direct SQLAlchemy | Direct types, constraints, and mapper configuration keep advanced behavior explicit |
| API and schema evolve independently | SQLAlchemy + separate Pydantic models | Separate ownership makes compatibility changes reviewable |
| Team already fluent in SQLAlchemy | Usually direct SQLAlchemy | A second abstraction may save little and complicate debugging |

SQLModel does not replace transaction design, loading strategy, migrations, indexes, or pool
operations. Those mechanisms remain owned by [SQLAlchemy ORM](03_sqlalchemy_orm.md),
[Async SQLAlchemy](04_async_sqlalchemy.md), [Connection Pooling](05_connection_pooling.md), and
[Alembic](06_alembic.md).

---

## 4. What breaks first, and when not to use it

⚠️ `SQLModel.metadata.create_all()` only sees models imported before it runs; an empty metadata
registry can produce a successful startup with missing tables.

⚠️ Reusing one table model for create, update, and response payloads leaks server-owned fields or
makes partial updates ambiguous. Separate model roles before adding endpoint logic.

Do not choose SQLModel merely to avoid learning SQLAlchemy: queries, sessions, transactions, and
loader behavior still come from SQLAlchemy. Do not choose direct SQLAlchemy merely because the
service might grow; start from today's concrete mapping needs and keep escape hatches explicit.

> **Production:** use Alembic for schema evolution, one session per unit of work, explicit loading
> across async boundaries, and database constraints for invariants that must survive every writer.

---

**Next**: [Async SQLAlchemy](04_async_sqlalchemy.md)

## Check your understanding

Shared declarations can reduce glue, but table identity and public field authority remain separate contracts.

**Prediction:** Order adds an internal fraud_score that clients cannot send or receive. Must SQLModel be abandoned?

<details><summary>Answer</summary>
No. Keep separate non-table create/read schemas and the table model. Choose direct SQLAlchemy when broader mapping/evolution needs outweigh declaration savings.
</details>

**Diagnosis:** Does a generated database ID belong in the create schema?

<details><summary>Answer</summary>
Only if clients are authorized to choose it. A table column alone does not grant that authority.
</details>
