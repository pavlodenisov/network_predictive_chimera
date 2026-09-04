"""Aggregates every feature router. ``intelligence.api.app`` imports ``router`` from here."""

from __future__ import annotations

from fastapi import APIRouter

from intelligence.api.routers import catalog, people, rankings, writes

router = APIRouter()
router.include_router(people.router)
router.include_router(rankings.router)
router.include_router(catalog.router)
router.include_router(writes.router)
