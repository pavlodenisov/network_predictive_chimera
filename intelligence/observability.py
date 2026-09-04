"""Structured logging + temporal helpers (spec §2.6, §37).

Every pipeline stage logs ``run_id, stage, count, duration_ms, warnings`` via
``stage_logger``. Malformed records are never silently dropped — callers record a warning.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import structlog

from intelligence.config import get_settings

SENSITIVE_LOG_KEYS = {"email", "primary_email", "linkedin_url", "primary_linkedin_url", "api_key"}
_CONFIGURED = False


# --------------------------------------------------------------------------- time
def now_utc() -> datetime:
    """Timezone-aware current time in UTC. The only sanctioned 'now'."""
    return datetime.now(tz=UTC)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Attach/convert tzinfo to UTC. SQLite drops tzinfo on read; this re-attaches it."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def days_between(earlier: datetime | None, later: datetime | None) -> float | None:
    earlier, later = ensure_utc(earlier), ensure_utc(later)
    if earlier is None or later is None:
        return None
    return (later - earlier).total_seconds() / 86400.0


# ------------------------------------------------------------------ log redaction
def _redact(_: Any, __: str, event_dict: structlog.types.EventDict) -> structlog.types.EventDict:
    for key in list(event_dict):
        if key.lower() in SENSITIVE_LOG_KEYS and event_dict[key]:
            event_dict[key] = "***redacted***"
    return event_dict


def configure_logging(force: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED and not force:
        return
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", level=level)

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer()
        if settings.log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _redact,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str = "chimera") -> structlog.stdlib.BoundLogger:
    configure_logging()
    return structlog.get_logger(name)


@contextmanager
def stage_logger(run_id: str, stage: str, **context: Any) -> Iterator[dict[str, Any]]:
    """Context manager for one pipeline stage.

    Yields a mutable ``stats`` dict; populate ``count`` / ``warnings`` / ``errors``.
    Emits one structured log line on exit with the elapsed ``duration_ms``.
    """
    log = get_logger("chimera.pipeline")
    stats: dict[str, Any] = {"count": 0, "warnings": [], "errors": []}
    started = time.perf_counter()
    log.info("stage.start", run_id=run_id, stage=stage, **context)
    try:
        yield stats
    except Exception as exc:  # noqa: BLE001 - stage failures are recorded, then re-raised
        stats.setdefault("errors", []).append(repr(exc))
        log.error(
            "stage.error",
            run_id=run_id,
            stage=stage,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            error=repr(exc),
            **context,
        )
        raise
    finally:
        stats["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
    log.info(
        "stage.done",
        run_id=run_id,
        stage=stage,
        count=stats.get("count", 0),
        duration_ms=stats["duration_ms"],
        warnings=len(stats.get("warnings", [])),
        errors=len(stats.get("errors", [])),
        **context,
    )
