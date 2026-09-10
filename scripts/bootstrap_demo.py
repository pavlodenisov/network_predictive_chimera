"""Idempotent demo bootstrap for a hosted deployment (Render / Docker / Fly).

migrate  ->  seed (no-op if the universe already exists)  ->  ensure a week-2 pipeline
pass so the UI shows week-over-week deltas (only if fewer than 2 WeeklyRun rows)  ->
exec uvicorn. Safe to run on every container start.
"""

from __future__ import annotations

import os
import subprocess
import sys

WEEKLY_AS_OF = os.environ.get("CHIMERA_DEMO_AS_OF", "2026-09-06")


def _run(*args: str, check: bool = True) -> int:
    print(f"[bootstrap] $ python -m {' '.join(args)}", flush=True)
    return subprocess.run([sys.executable, "-m", *args], check=check).returncode


def main() -> None:
    _run("alembic", "upgrade", "head")
    _run("intelligence.jobs.seed")

    from sqlalchemy import func, select

    from intelligence.db import session_scope
    from intelligence.models import WeeklyRun

    with session_scope() as session:
        runs = int(session.scalar(select(func.count()).select_from(WeeklyRun)) or 0)

    if runs < 2:
        _run("intelligence.jobs.weekly", "--as-of", WEEKLY_AS_OF, check=False)
    else:
        print(f"[bootstrap] {runs} weekly runs already present — skipping the demo pass", flush=True)

    port = os.environ.get("PORT", "8000")
    print(f"[bootstrap] starting uvicorn on :{port}", flush=True)
    os.execvp(  # noqa: S606 - replace this process with the server
        sys.executable,
        [
            sys.executable,
            "-m",
            "uvicorn",
            "intelligence.api.app:app",
            "--host",
            "0.0.0.0",
            "--port",
            port,
        ],
    )


if __name__ == "__main__":
    main()
