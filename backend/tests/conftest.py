from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
import tempfile

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
import app.db as db_module

ORIGINAL_ENGINE = getattr(db_module, "engine", None)


@pytest.fixture
def tmp_path() -> Generator[Path, None, None]:
    """Provide a reliable temporary directory bypassing pytest-of-user permission conflicts."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def tmp_db_file(tmp_path: Path) -> Path:
    """Path to a temporary SQLite database file for testing."""
    return tmp_path / "test_sirengrid.db"


@pytest.fixture
def tmp_db_url(tmp_db_file: Path) -> str:
    """Database URL pointing to the temporary SQLite file."""
    return f"sqlite:///{tmp_db_file}"


@pytest.fixture
def isolated_engine(tmp_db_url: str) -> Generator[Engine, None, None]:
    """Create an isolated SQLAlchemy engine bound to a temporary SQLite file."""
    engine = create_engine(
        tmp_db_url,
        connect_args={"check_same_thread": False},
    )
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def isolate_test_database(
    isolated_engine: Engine,
    tmp_db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Engine, None, None]:
    """Isolate app.db engine and SessionLocal so tests never touch the repo database."""
    test_sessionmaker = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=isolated_engine,
    )
    monkeypatch.setattr(settings, "database_url", tmp_db_url)
    monkeypatch.setattr(db_module, "engine", isolated_engine)
    monkeypatch.setattr(db_module, "SessionLocal", test_sessionmaker)
    yield isolated_engine


@pytest.fixture
def db_session(isolate_test_database: Engine) -> Generator[Session, None, None]:
    """Provide an isolated database session for a test."""
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def default_db_engine() -> Engine | None:
    """Return the unpatched module-level engine reference for inspection."""
    return ORIGINAL_ENGINE
