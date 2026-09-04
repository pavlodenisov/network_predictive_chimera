"""Acceptance scenarios run against the full synthetic universe + a real week-2 pipeline
pass, seeded once per test session and committed (spec §62-65)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy.orm import Session

from intelligence.db import get_sessionmaker, session_scope
from intelligence.jobs.pipeline import run_weekly
from intelligence.jobs.seed import seed_all
from tests.conftest import reset_schema

WEEK2 = date(2026, 9, 6)


@pytest.fixture(scope="session")
def weekly_run_id(_schema) -> Iterator[str]:  # noqa: ANN001 - _schema is the session DB fixture
    reset_schema()
    with session_scope() as s:
        seed_all(s)
    with session_scope() as s:
        result = run_weekly(s, as_of=WEEK2, code_version="acceptance")
    yield str(result.run_id)
    reset_schema()  # leave empty tables for the transaction-isolated unit tests


@pytest.fixture
def ro(weekly_run_id: str) -> Iterator[Session]:
    """Read-only session over the committed acceptance universe."""
    s = get_sessionmaker()()
    try:
        yield s
    finally:
        s.close()
