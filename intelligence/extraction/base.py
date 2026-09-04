from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from intelligence.schemas.extraction import ExtractionOutput


@dataclass(slots=True)
class ExtractionRequest:
    observation_id: str
    content_type: str
    raw_text: str | None
    raw_json: dict | None
    subject_hint: str | None = None
    source_provider: str = "unknown"
    reliability_tier: int = 3
    #: prior structured profile snapshot, when this observation is a repeated snapshot.
    previous_snapshot: dict | None = None


@dataclass(slots=True)
class ExtractionResult:
    output: ExtractionOutput
    parse_status: str  # ok | invalid_retried_ok | failed
    latency_ms: int = 0
    error: str | None = None
    token_usage: dict | None = None
    attempts: int = 1
    prompt_version: str = ""
    model_version: str = ""
    raw_response: dict | None = field(default=None)


@runtime_checkable
class Extractor(Protocol):
    name: str
    prompt_version: str
    model_version: str

    def extract(self, request: ExtractionRequest) -> ExtractionResult: ...
