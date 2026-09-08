from __future__ import annotations

from collections.abc import Generator
import sqlite3

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.schema import CreateTable

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
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()


def _connect_args_for_database_url(database_url: str) -> dict[str, object]:
    return {"check_same_thread": False} if database_url.startswith("sqlite") else {}


connect_args = _connect_args_for_database_url(settings.DATABASE_URL)

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
        _ensure_sqlite_nullable_incident_location(target)


def _ensure_sqlite_nullable_incident_location(target: Engine) -> None:
    """Relax legacy incident coordinate constraints without losing rows.

    SQLite cannot alter a column from NOT NULL to nullable. Rebuild only the
    legacy table, copying every column shared with the current model inside a
    single transaction. Current databases are detected and left untouched.
    """
    inspector = inspect(target)
    if "incidents" not in inspector.get_table_names():
        return
    existing_columns = {
        column["name"]: column for column in inspector.get_columns("incidents")
    }
    latitude = existing_columns.get("latitude")
    longitude = existing_columns.get("longitude")
    if (
        latitude is None
        or longitude is None
        or (latitude.get("nullable", True) and longitude.get("nullable", True))
    ):
        return

    table = Base.metadata.tables.get("incidents")
    if table is None:  # pragma: no cover - model registration is a runtime invariant
        return
    create_sql = str(CreateTable(table).compile(target))
    shared_columns = [
        column.name for column in table.columns if column.name in existing_columns
    ]
    column_list = ", ".join(f'"{name}"' for name in shared_columns)
    with target.begin() as connection:
        connection.execute(text("ALTER TABLE incidents RENAME TO incidents_legacy"))
        connection.execute(text(create_sql))
        connection.execute(
            text(
                f"INSERT INTO incidents ({column_list}) "
                f"SELECT {column_list} FROM incidents_legacy"
            )
        )
        connection.execute(text("DROP TABLE incidents_legacy"))


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
