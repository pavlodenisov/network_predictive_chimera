"""The 14-stage weekly pipeline: runs end to end, is idempotent, records a WeeklyRun and a
structured digest (spec §6, §38, §29)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select

from intelligence.db import get_sessionmaker, session_scope
from intelligence.jobs.pipeline import run_weekly
from intelligence.jobs.seed import seed_all
from intelligence.models import Event, Fact, RawObservation, ScoreSnapshot, WeeklyRun
from tests.conftest import reset_schema

pytestmark = pytest.mark.integration

WEEK2 = date(2026, 9, 6)


@pytest.fixture(scope="module")
def universe(_schema):  # noqa: ANN001
    reset_schema()
    with session_scope() as s:
        seed_all(s)
    yield
    reset_schema()


def _counts(s):
    return {
        "obs": s.scalar(select(func.count()).select_from(RawObservation)),
        "facts": s.scalar(select(func.count()).select_from(Fact)),
        "events": s.scalar(select(func.count()).select_from(Event)),
        "scores": s.scalar(select(func.count()).select_from(ScoreSnapshot)),
        "runs": s.scalar(select(func.count()).select_from(WeeklyRun)),
    }


def test_weekly_runs_and_is_idempotent(universe):
    with session_scope() as s:
        run_weekly(s, as_of=WEEK2, code_version="itest")
    with get_sessionmaker()() as s:
        after_first = _counts(s)
        run = s.execute(select(WeeklyRun).order_by(WeeklyRun.started_at.desc())).scalars().first()
        assert run.status in ("success", "partial")
        assert run.finished_at is not None
        assert run.observations_ingested >= 1
        assert run.stage_stats and len(run.stage_stats) >= 8
        assert {s["stage"] for s in run.stage_stats} >= {
            "source_health",
            "features_and_scoring",
            "rank_deltas",
            "digest",
        }
        assert run.digest and "sections" in run.digest
        assert run.digest["sections"]["largest_founder_score_increases"]

    # re-run the SAME week -> no duplicate observations / facts / events
    with session_scope() as s:
        run_weekly(s, as_of=WEEK2, code_version="itest")
    with get_sessionmaker()() as s:
        after_second = _counts(s)
    assert after_second["obs"] == after_first["obs"]
    assert after_second["events"] == after_first["events"]
    assert after_second["facts"] == after_first["facts"]
    # a second run *does* add another set of score snapshots (a new run) — that's expected
    assert after_second["runs"] == after_first["runs"] + 1


def test_digest_has_no_marketing_prose(universe):
    with session_scope() as s:
        run_weekly(s, as_of=WEEK2)
    with get_sessionmaker()() as s:
        run = s.execute(select(WeeklyRun).order_by(WeeklyRun.started_at.desc())).scalars().first()
        blob = str(run.digest).lower()
    for banned in ("exciting", "compelling", "impressive", "promising", "visionary", "amazing"):
        assert banned not in blob
