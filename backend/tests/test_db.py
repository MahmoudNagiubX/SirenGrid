from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import Engine, Integer, String, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

import app.db as db_module
from app.db import Base, get_db, init_db


def test_db_module_exposures() -> None:
    """Verify that backend.app.db exposes the required objects and contracts."""
    assert hasattr(db_module, "Base")
    assert hasattr(db_module, "engine")
    assert hasattr(db_module, "SessionLocal")
    assert hasattr(db_module, "get_db")
    assert hasattr(db_module, "init_db")

    assert issubclass(Base, DeclarativeBase)
    assert isinstance(db_module.engine, Engine)
    assert isinstance(db_module.SessionLocal, sessionmaker)
    assert callable(get_db)
    assert callable(init_db)


def test_sqlite_engine_connect_args(default_db_engine: Engine | None) -> None:
    """Verify that SQLite engine has check_same_thread=False in connect_args."""
    target_engine = default_db_engine or db_module.engine
    assert target_engine.dialect.name == "sqlite"
    assert db_module.connect_args.get("check_same_thread") is False


def test_sqlite_pragmas_enabled(isolated_engine: Engine) -> None:
    """Verify SQLite safety and concurrency pragmas are active."""
    with isolated_engine.connect() as conn:
        fk_status = conn.execute(text("PRAGMA foreign_keys;")).scalar()
        assert fk_status == 1

        journal_mode = conn.execute(text("PRAGMA journal_mode;")).scalar()
        assert journal_mode is not None
        assert str(journal_mode).lower() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout;")).scalar() == 5000

        # Verify foreign keys are actively enforced
        conn.execute(
            text("CREATE TABLE parent_test (id INTEGER PRIMARY KEY);")
        )
        conn.execute(
            text(
                "CREATE TABLE child_test ("
                "id INTEGER PRIMARY KEY, "
                "parent_id INTEGER NOT NULL REFERENCES parent_test(id)"
                ");"
            )
        )
        conn.commit()

        # Inserting a child with a non-existent parent must raise IntegrityError
        with pytest.raises(IntegrityError):
            conn.execute(
                text("INSERT INTO child_test (id, parent_id) VALUES (1, 999);")
            )
            conn.commit()


def test_sqlite_busy_timeout_is_explicit_when_driver_default_is_disabled(
    tmp_path: Path,
) -> None:
    target_engine = db_module.create_engine(
        f"sqlite:///{tmp_path / 'busy-timeout.db'}",
        connect_args={"timeout": 0},
    )
    try:
        with target_engine.connect() as conn:
            assert conn.execute(text("PRAGMA busy_timeout;")).scalar() == 5000
    finally:
        target_engine.dispose()


def test_non_sqlite_database_url_has_no_sqlite_connect_args() -> None:
    assert db_module._connect_args_for_database_url("postgresql://db/test") == {}


def test_existing_hospital_state_gets_overlay_column_additively(tmp_path: Path) -> None:
    target_engine = db_module.create_engine(
        f"sqlite:///{tmp_path / 'legacy-hospital.db'}",
        connect_args={"check_same_thread": False},
    )
    try:
        with target_engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE hospital_operational_states ("
                    "hospital_id VARCHAR(255) PRIMARY KEY, "
                    "version INTEGER, accepting_state VARCHAR, "
                    "simulated_load_ratio FLOAT, simulated_free_capacity INTEGER, "
                    "incoming_cases INTEGER, freshness_status VARCHAR, "
                    "last_updated DATETIME, source VARCHAR, data_reality VARCHAR, "
                    "provenance_json JSON)"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO hospital_operational_states "
                    "(hospital_id, version, accepting_state) "
                    "VALUES ('osm:legacy', 3, 'UNKNOWN')"
                )
            )

        db_module.init_db(target_engine=target_engine)

        columns = {
            column["name"]
            for column in db_module.inspect(target_engine).get_columns(
                "hospital_operational_states"
            )
        }
        assert "simulated_capability_tags_json" in columns
        with target_engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT hospital_id, version, accepting_state "
                    "FROM hospital_operational_states"
                )
            ).one()
        assert tuple(row) == ("osm:legacy", 3, "UNKNOWN")
    finally:
        target_engine.dispose()


def test_isolated_temporary_db(isolated_engine: Engine, tmp_db_file: Path) -> None:
    """Verify tests run against an isolated temporary database, not a persistent repo DB."""
    repo_root = Path(__file__).resolve().parents[2]
    backend_root = Path(__file__).resolve().parents[1]
    repo_db = repo_root / "sirengrid.db"
    backend_db = backend_root / "sirengrid.db"

    # Confirm neither persistent file exists
    assert not repo_db.exists()
    assert not backend_db.exists()

    # Confirm isolated engine points to the temporary directory
    assert str(tmp_db_file) in str(isolated_engine.url)

    # Perform a query on the temporary database
    with isolated_engine.connect() as conn:
        val = conn.execute(text("SELECT 42;")).scalar()
        assert val == 42

    # The temporary DB file must exist, and the persistent repo DB must NOT exist
    assert tmp_db_file.exists()
    assert not repo_db.exists()
    assert not backend_db.exists()


def test_init_db_creates_tables(isolated_engine: Engine, db_session: Session) -> None:
    """Verify init_db() creates tables registered on Base.metadata."""
    # Define a tiny test model using Base
    class DummyItem(Base):
        __tablename__ = "dummy_items_test"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String(50))

    try:
        # Before init_db, the table should not exist in the isolated DB
        inspector_before = inspect(isolated_engine)
        assert "dummy_items_test" not in inspector_before.get_table_names()

        # Run init_db()
        init_db()

        # Table should now exist
        inspector_after = inspect(isolated_engine)
        assert "dummy_items_test" in inspector_after.get_table_names()

        # Verify operational CRUD on the created table
        item = DummyItem(id=1, name="operational-test")
        db_session.add(item)
        db_session.commit()

        queried = db_session.get(DummyItem, 1)
        assert queried is not None
        assert queried.name == "operational-test"
    finally:
        # Clean up the dummy model from Base metadata
        Base.metadata.remove(DummyItem.__table__)
        with isolated_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS dummy_items_test;"))


def test_init_db_accepts_target_engine(tmp_path: Path) -> None:
    """Verify init_db(target_engine=...) creates tables on the passed engine."""
    custom_db = tmp_path / "custom_target.db"
    custom_engine = db_module.create_engine(
        f"sqlite:///{custom_db}",
        connect_args={"check_same_thread": False},
    )

    class CustomTargetItem(Base):
        __tablename__ = "custom_target_test"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)

    try:
        init_db(target_engine=custom_engine)
        inspector = inspect(custom_engine)
        assert "custom_target_test" in inspector.get_table_names()
    finally:
        Base.metadata.remove(CustomTargetItem.__table__)
        custom_engine.dispose()


def test_get_db_session_lifecycle(isolated_engine: Engine) -> None:
    """Verify get_db() yields an active Session and reliably closes it on normal exit."""
    gen = get_db()
    session = next(gen)
    assert isinstance(session, Session)

    # Verify session is usable
    result = session.execute(text("SELECT 1;")).scalar()
    assert result == 1

    with patch.object(session, "close", wraps=session.close) as mock_close:
        mock_close.assert_not_called()
        with pytest.raises(StopIteration):
            next(gen)
        mock_close.assert_called_once()


def test_get_db_session_cleanup_on_exception() -> None:
    """Verify get_db() reliably closes the Session if an exception is raised in caller."""
    gen = get_db()
    session = next(gen)
    assert isinstance(session, Session)

    with patch.object(session, "close", wraps=session.close) as mock_close:
        mock_close.assert_not_called()
        with pytest.raises(RuntimeError, match="Caller failure"):
            gen.throw(RuntimeError("Caller failure"))
        mock_close.assert_called_once()
