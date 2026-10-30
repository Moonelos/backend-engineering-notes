"""Run only in the explicitly selected SQLAlchemy 2.1 upgrade environment."""
import sqlalchemy
from sqlalchemy import Integer, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

assert sqlalchemy.__version__.startswith('2.1.'), sqlalchemy.__version__
assert make_url('postgresql://localhost/example').get_dialect().driver == 'psycopg'

class Base(DeclarativeBase): pass
class Item(Base):
    __tablename__ = 'items'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    required: Mapped[int]

engine = create_engine('sqlite://')
Base.metadata.create_all(engine)
try:
    with Session(engine) as session:
        session.add(Item(required=None))
        try:
            session.execute(text('SELECT 1'))
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError('expected autoflush before textual SELECT')
        assert session.scalar(text('SELECT count(*) FROM items')) == 0
finally:
    engine.dispose()
print('2.1 explicit upgrade: psycopg default; textual execution autoflush; rollback leaves zero rows')
