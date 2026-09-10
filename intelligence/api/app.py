"""FastAPI application factory.

Routers stay thin (validate → repository/service → serialize). Analytical math lives in
``intelligence.scoring`` / ``intelligence.features`` — never here (CLAUDE.md).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from intelligence import __version__
from intelligence.config import get_settings
from intelligence.observability import configure_logging, get_logger


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    app = FastAPI(
        title="Chimera Network Intelligence API",
        version=__version__,
        summary="Structured, auditable intelligence on founders, LPs, talent, and connectors.",
    )
    log = get_logger("chimera.api")

    cors_kwargs: dict = {"allow_methods": ["*"], "allow_headers": ["*"]}
    if "*" in settings.cors_origin_list:
        cors_kwargs["allow_origins"] = ["*"]
    else:
        cors_kwargs["allow_origins"] = settings.cors_origin_list
        if settings.cors_allow_origin_regex:
            cors_kwargs["allow_origin_regex"] = settings.cors_allow_origin_regex
            log.warning(
                "cors.hosted_fallback",
                configured=settings.cors_origin_list,
                regex=settings.cors_allow_origin_regex,
                hint="set CHIMERA_CORS_ORIGINS to the exact web URL once SSO is in front",
            )
    app.add_middleware(CORSMiddleware, **cors_kwargs)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:  # noqa: RUF029
        log.error("api.unhandled", path=request.url.path, error=repr(exc))
        return JSONResponse(status_code=500, content={"detail": "internal error"})

    from intelligence.api.routers import health

    app.include_router(health.router)
    _register_feature_routers(app)
    return app


def _register_feature_routers(app: FastAPI) -> None:
    """Feature routers (people, rankings, events, …). Populated in Wave 7; a missing
    module here simply means that surface is not built yet."""
    import importlib

    try:
        feature_api = importlib.import_module("intelligence.api.routers.api")
    except ModuleNotFoundError:
        return
    app.include_router(feature_api.router)


app = create_app()
