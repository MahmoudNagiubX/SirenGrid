from __future__ import annotations

from collections.abc import Generator
import sqlite3

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

__all__ = ["Base", "engine", "SessionLocal", "get_db", "init_db"]


class Base(DeclarativeBase):
    pass


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(
    dbapi_connection: object,
    connection_record: object,
) -> None:
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.close()


connect_args = (
    {"check_same_thread": False}
    if settings.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def init_db(target_engine: Engine | None = None) -> None:
    """Create all database tables defined on Base.metadata."""
    target = target_engine if target_engine is not None else engine
    Base.metadata.create_all(bind=target)
    if target.dialect.name == "sqlite":
        _ensure_sqlite_phase07_columns(target)


def _ensure_sqlite_phase07_columns(target: Engine) -> None:
    """Apply additive Phase 07 columns to an existing local SQLite database."""
    inspector = inspect(target)
    incident_columns = {
        column["name"] for column in inspector.get_columns("incidents")
    }
    if "pending_replan_plan_id" not in incident_columns:
        with target.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE incidents "
                    "ADD COLUMN pending_replan_plan_id VARCHAR(36)"
                )
            )


def get_db() -> Generator[Session, None, None]:
    """Yield an active database session and close it reliably after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
