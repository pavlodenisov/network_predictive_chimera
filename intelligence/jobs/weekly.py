"""``python -m intelligence.jobs.weekly`` — run the weekly intelligence cycle (spec §6).

Flags:
  --as-of YYYY-MM-DD   point-in-time date for the run (default: today)
  --digest-only        print the most recent stored digest, run nothing
  --dry-run            execute every stage then roll back (no writes persisted)
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

from sqlalchemy import select

from intelligence.db import session_scope
from intelligence.digest import render_digest_text
from intelligence.jobs.pipeline import run_weekly
from intelligence.models import WeeklyRun
from intelligence.observability import configure_logging, get_logger


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="intelligence.jobs.weekly")
    p.add_argument("--as-of", type=date.fromisoformat, default=None)
    p.add_argument("--digest-only", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    log = get_logger("chimera.weekly")
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    if args.digest_only:
        with session_scope() as session:
            run = (
                session.execute(select(WeeklyRun).order_by(WeeklyRun.started_at.desc()))
                .scalars()
                .first()
            )
            if run is None or not run.digest:
                print("no weekly run with a digest found — run `make weekly` first")
                return 1
            print(render_digest_text(run.digest))
        return 0

    with session_scope() as session:
        result = run_weekly(session, as_of=args.as_of, dry_run=args.dry_run)
        log.info("weekly.done", run_id=str(result.run_id), status=result.status)
        print(result.digest_text)
        return 0 if result.status in ("success", "partial") else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
