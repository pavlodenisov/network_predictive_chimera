"""Test harness.

A throwaway file-backed SQLite database is created once per session via
``Base.metadata.create_all`` (the only sanctioned use of ``create_all`` — CLAUDE.md
rule 7). Each test runs inside a transaction that is rolled back for isolation.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

# --- environment MUST be set before importing intelligence.config / intelligence.db ---
_REPO_ROOT = Path(__file__).resolve().parent.parent
_TMPDIR = tempfile.mkdtemp(prefix="chimera-test-")
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_TMPDIR}/test.db"
os.environ["CHIMERA_CONFIG_DIR"] = str(_REPO_ROOT / "configs")
os.environ["CHIMERA_SEEDS_DIR"] = str(_REPO_ROOT / "db" / "seeds")
os.environ.setdefault("CHIMERA_LOG_LEVEL", "WARNING")
os.environ.setdefault("CHIMERA_CODE_VERSION", "test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from intelligence.config import reload_settings  # noqa: E402

reload_settings()

from intelligence.db import get_engine, reset_engine  # noqa: E402
from intelligence.models import Base  # noqa: E402

reset_engine()


@pytest.fixture(scope="session", autouse=True)
def _schema() -> Iterator[None]:
    engine = get_engine()
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def reset_schema() -> None:
    """Wipe every table and recreate it. Used by fixtures that COMMIT (seed / weekly
    pipeline) so they neither see nor leave data for the transaction-isolated unit tests."""
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = get_engine()
    connection = engine.connect()
    trans = connection.begin()
    local = sessionmaker(bind=connection, autoflush=False, expire_on_commit=False)
    sess = local()
    try:
        yield sess
    finally:
        sess.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    from intelligence.api.app import create_app
    from intelligence.api.deps import get_session

    app = create_app()
    app.dependency_overrides[get_session] = lambda: session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
