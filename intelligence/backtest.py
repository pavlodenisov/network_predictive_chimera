"""``python -m intelligence.backtest --model founder_v0.1 --from 2026-01-01 --to 2026-08-01``

Reconstructs point-in-time features for each weekly step in the window and reports
rankings, score distributions, and feature-contribution distributions. No future
information leaks in: a fact/event is visible at ``as_of`` only if its
``observed_at`` / ``detected_at`` <= ``as_of`` (spec §35).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from intelligence.db import session_scope
from intelligence.features import build_feature_bundle
from intelligence.features.base import POINT_IN_TIME_CUTOFF
from intelligence.models import Person
from intelligence.models.enums import MonitoringStatus
from intelligence.observability import configure_logging, get_logger
from intelligence.scoring.config import load_model_config
from intelligence.scoring.engine import score_person

_TARGET_BY_MODEL = {"founder": "founder", "lp": "lp", "talent": "talent", "connector": "connector"}


@dataclass(slots=True)
class StepResult:
    as_of: str
    ranked: list[dict]
    score_distribution: dict
    contribution_distribution: dict


def _weekly_steps(start: date, end: date) -> list[date]:
    steps, cur = [], start
    while cur <= end:
        steps.append(cur)
        cur += timedelta(days=7)
    return steps


def run_backtest(model_name: str, start: date, end: date, *, limit: int = 25) -> list[StepResult]:
    cfg = load_model_config(
        model_name if model_name.endswith(tuple("0123456789")) else f"{model_name}_v0.1"
    )
    target = _TARGET_BY_MODEL[cfg.target]
    if target == "talent":
        raise SystemExit("talent backtest needs a role_need; not supported in V0 backtest")

    out: list[StepResult] = []
    with session_scope() as session:
        people = list(
            session.execute(
                select(Person).where(
                    Person.merged_into_id.is_(None),
                    Person.monitoring_status != MonitoringStatus.DISMISSED,
                )
            ).scalars()
        )
        for step in _weekly_steps(start, end):
            as_of_dt = datetime(step.year, step.month, step.day, 23, 59, 59, tzinfo=UTC)
            rows: list[dict] = []
            all_contribs: dict[str, list[float]] = {}
            token = POINT_IN_TIME_CUTOFF.set(as_of_dt)  # no future knowledge leaks in
            try:
                for person in people:
                    bundle = build_feature_bundle(session, person.id, target, as_of_dt)
                    res = score_person(session, person, cfg, bundle, as_of_dt)
                    rows.append(
                        {
                            "person": person.canonical_name,
                            "priority": round(res.priority, 2),
                            "confidence": round(res.confidence, 3),
                            "quality": res.quality,
                            "fit": res.fit,
                            "timing": res.timing,
                            "access": res.access,
                        }
                    )
                    for dname, d in res.contribution_breakdown["dimensions"].items():
                        for fname, f in d.get("features", {}).items():
                            if isinstance(f, dict) and f.get("included"):
                                all_contribs.setdefault(f"{dname}.{fname}", []).append(
                                    f.get("contribution", 0.0)
                                )
            finally:
                POINT_IN_TIME_CUTOFF.reset(token)
            rows.sort(key=lambda r: r["priority"], reverse=True)
            for i, r in enumerate(rows, 1):
                r["rank"] = i
            priorities = [r["priority"] for r in rows] or [0.0]
            out.append(
                StepResult(
                    as_of=step.isoformat(),
                    ranked=rows[:limit],
                    score_distribution={
                        "n": len(priorities),
                        "mean": round(statistics.fmean(priorities), 2),
                        "median": round(statistics.median(priorities), 2),
                        "p90": round(sorted(priorities)[int(0.9 * (len(priorities) - 1))], 2),
                        "max": round(max(priorities), 2),
                    },
                    contribution_distribution={
                        k: round(statistics.fmean(v), 4) for k, v in sorted(all_contribs.items())
                    },
                )
            )
        session.rollback()  # backtest never writes
    return out


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    log = get_logger("chimera.backtest")
    p = argparse.ArgumentParser(prog="intelligence.backtest")
    p.add_argument("--model", default="founder_v0.1")
    p.add_argument("--from", dest="start", type=date.fromisoformat, required=True)
    p.add_argument("--to", dest="end", type=date.fromisoformat, required=True)
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--json", action="store_true", help="emit full JSON instead of a summary")
    args = p.parse_args(argv if argv is not None else sys.argv[1:])

    results = run_backtest(args.model, args.start, args.end, limit=args.limit)
    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2, default=str))
        return 0

    for step in results:
        print(f"\n=== as of {step.as_of} ===")
        print(
            f"scores: n={step.score_distribution['n']} mean={step.score_distribution['mean']} "
            f"p90={step.score_distribution['p90']} max={step.score_distribution['max']}"
        )
        for r in step.ranked[: args.limit]:
            print(
                f"  #{r['rank']:>3}  {r['priority']:>6.2f}  conf {r['confidence']:.2f}  {r['person']}"
            )
    log.info("backtest.done", steps=len(results), model=args.model)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
