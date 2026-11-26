"""SQLAlchemy 2.0 base, engine factory and portable upsert."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, Table, create_engine, event
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base shared by all project models."""


def make_engine(url: str, *, echo: bool = False) -> Engine:
    engine = create_engine(url, echo=echo, future=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn: Any, _record: Any) -> None:  # pragma: no cover - driver hook
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def upsert(
    session: Session,
    table: Table,
    rows: Sequence[dict[str, Any]],
    key_cols: Sequence[str],
) -> int:
    """Insert rows, updating non-key columns on key conflict. Supports SQLite and PostgreSQL."""
    if not rows:
        return 0
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        stmt: Any = postgresql.insert(table).values(list(rows))
    elif dialect == "sqlite":
        stmt = sqlite.insert(table).values(list(rows))
    else:  # pragma: no cover - guarded by supported deployments
        raise NotImplementedError(f"upsert not supported for dialect {dialect!r}")
    update_cols = {
        c.name: stmt.excluded[c.name]
        for c in table.columns
        if c.name not in key_cols and c.name in rows[0]
    }
    stmt = (
        stmt.on_conflict_do_update(index_elements=list(key_cols), set_=update_cols)
        if update_cols
        else stmt.on_conflict_do_nothing(index_elements=list(key_cols))
    )
    session.execute(stmt)
    return len(rows)
