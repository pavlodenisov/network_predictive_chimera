from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import inspect, text

from intelligence import __version__
from intelligence.api.deps import SessionDep
from intelligence.config import get_settings

router = APIRouter(tags=["system"])


@router.get("/health")
def health(session: SessionDep) -> dict:
    settings = get_settings()
    db_ok = True
    migration_head: str | None = None
    table_count = 0
    try:
        session.execute(text("SELECT 1"))
        insp = inspect(session.get_bind())
        tables = insp.get_table_names()
        table_count = len(tables)
        if "alembic_version" in tables:
            migration_head = session.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
    except Exception:  # noqa: BLE001 - health must report, not raise
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "version": __version__,
        "code_version": settings.code_version,
        "database": {
            "dialect": "sqlite" if settings.is_sqlite else "postgresql",
            "connected": db_ok,
            "migration_head": migration_head,
            "tables": table_count,
        },
        "extraction": {
            "extractor": settings.extractor,
            "llm_available": settings.llm_extraction_available,
        },
    }
