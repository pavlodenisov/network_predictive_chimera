"""Structured extraction (spec §22-23).

LLMs may extract and classify. LLMs never produce a score. The default extractor is
deterministic (``RuleBasedExtractor``); ``ClaudeExtractor`` activates only when
``CHIMERA_EXTRACTOR=claude`` and ``ANTHROPIC_API_KEY`` is set.
"""

from __future__ import annotations

from intelligence.config import get_settings
from intelligence.extraction.base import ExtractionRequest, ExtractionResult, Extractor
from intelligence.extraction.rules import RuleBasedExtractor


def get_extractor() -> Extractor:
    settings = get_settings()
    if settings.extractor == "claude" and settings.anthropic_api_key:
        from intelligence.extraction.claude import ClaudeExtractor

        return ClaudeExtractor()
    return RuleBasedExtractor()


__all__ = [
    "Extractor",
    "ExtractionRequest",
    "ExtractionResult",
    "RuleBasedExtractor",
    "get_extractor",
]
