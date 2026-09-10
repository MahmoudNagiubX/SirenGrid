from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import Engine, Integer, String, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

import app.db as db_module
from app.config import REPO_ROOT, Settings, get_settings
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
    """Verify PRAGMA foreign_keys=ON and PRAGMA journal_mode=WAL are active."""
    with isolated_engine.connect() as conn:
        fk_status = conn.execute(text("PRAGMA foreign_keys;")).scalar()
        assert fk_status == 1

        journal_mode = conn.execute(text("PRAGMA journal_mode;")).scalar()
        assert journal_mode is not None
        assert str(journal_mode).lower() == "wal"

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


def test_default_sqlite_database_is_backend_relative_not_cwd_relative(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)

    expected = (REPO_ROOT / "backend" / "sirengrid.db").resolve()
    configured = get_settings().DATABASE_URL

    assert Path(make_url(configured).database).resolve() == expected
    assert Path(make_url(Settings().DATABASE_URL).database).resolve() == expected


def test_database_url_environment_override_is_preserved(
    tmp_db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", tmp_db_url)
    assert get_settings().DATABASE_URL == tmp_db_url


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


def test_default_database_url_is_absolute_regardless_of_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: a real P0 where /health returned 200 but every DB-backed
    endpoint 500'd with "no such table". Root cause: the default
    DATABASE_URL was a bare relative ``sqlite:///./sirengrid.db``, so a
    server launched from an unexpected working directory silently opened
    (and, via CREATE TABLE IF NOT EXISTS, silently created) a different,
    empty database. The default must resolve to the same absolute
    ``backend/sirengrid.db`` no matter what the process's cwd is at launch.
    """
    from app.config import DEFAULT_DATABASE_PATH, get_settings

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)  # simulate launching from an unrelated cwd

    settings = get_settings()

    assert not settings.DATABASE_URL.startswith("sqlite:///./")
    assert not settings.DATABASE_URL.startswith("sqlite:///.")
    assert DEFAULT_DATABASE_PATH.is_absolute()
    assert DEFAULT_DATABASE_PATH.as_posix() in settings.DATABASE_URL


def test_startup_schema_failure_is_logged_not_silently_swallowed() -> None:
    """Regression: a schema-init failure must never leave a server that
    looks healthy without any trace. Previously the exception was caught
    and logged through a logger with no handler configured anywhere in the
    app, so the failure was completely invisible (the exact "false healthy
    server" this test guards against).
    """
    import asyncio
    import logging as logging_module
    from unittest.mock import patch

    import app.main as main_module

    # The fix attaches a handler directly to this logger; a startup failure
    # must never rely on some other part of the app configuring one.
    assert main_module.logger.handlers, (
        "app.main's logger has no handler — a startup failure would be "
        "silently dropped, exactly as in the original P0."
    )

    captured: list[logging_module.LogRecord] = []

    class _Capture(logging_module.Handler):
        def emit(self, record: logging_module.LogRecord) -> None:
            captured.append(record)

    handler = _Capture()
    main_module.logger.addHandler(handler)
    try:
        with patch.object(
            main_module, "init_db", side_effect=RuntimeError("simulated schema failure")
        ):

            async def _run_lifespan() -> None:
                async with main_module.lifespan(main_module.app):
                    pass

            with pytest.raises(RuntimeError, match="simulated schema failure"):
                asyncio.run(_run_lifespan())
    finally:
        main_module.logger.removeHandler(handler)

    assert any(record.levelno >= logging_module.ERROR for record in captured)
    assert any("init_db" in record.getMessage() for record in captured)


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
