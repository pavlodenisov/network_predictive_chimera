"""Strict extraction schemas (spec §23).

Every LLM extraction MUST validate against ``ExtractionOutput``:
- strict enum event / fact types (no uncontrolled free-form labels)
- explicit confidence in [0, 1]
- nullable unknowns (never invented values)
- ``extra="forbid"`` — unexpected keys are rejected

The runner validates, retries once with the validation error as feedback, then records an
``ExtractionRun(parse_status="failed")``. Malformed output is never silently accepted.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from intelligence.events.taxonomy import EventType
from intelligence.facts import FactType

_Strict = ConfigDict(extra="forbid", use_enum_values=True)


class ExtractedEntity(BaseModel):
    model_config = _Strict
    kind: Literal["person", "organization", "product", "technology", "role"]
    name: str = Field(min_length=1, max_length=300)
    role: str | None = None
    context: str | None = Field(default=None, max_length=500)


class ExtractedFact(BaseModel):
    model_config = _Strict
    fact_type: FactType
    #: {"value": …, "unit": …}  OR  {"status": "unknown"}. Never a bare scalar.
    value: dict = Field(default_factory=lambda: {"status": "unknown"})
    confidence: float = Field(ge=0.0, le=1.0)
    occurred_at: date | None = None
    organization_name: str | None = None
    evidence_quote: str | None = Field(default=None, max_length=800)

    @field_validator("value")
    @classmethod
    def _value_shape(cls, v: dict) -> dict:
        if "status" not in v and "value" not in v:
            raise ValueError("value must contain 'value' or 'status'")
        if v.get("status") not in (None, "known", "unknown"):
            raise ValueError("status must be 'known' or 'unknown'")
        return v


class ExtractedEvent(BaseModel):
    model_config = _Strict
    event_type: EventType
    organization_name: str | None = None
    occurred_at: date | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    #: True routes this to the ``inference`` table rather than ``event`` (spec §2.2).
    is_inference: bool = False
    probability: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_quote: str | None = Field(default=None, max_length=800)
    explanation_code: str | None = Field(default=None, max_length=64)


class ExtractionOutput(BaseModel):
    model_config = _Strict
    entities: list[ExtractedEntity] = Field(default_factory=list)
    facts: list[ExtractedFact] = Field(default_factory=list)
    events: list[ExtractedEvent] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.entities or self.facts or self.events)


EXTRACTION_JSON_SCHEMA: dict = ExtractionOutput.model_json_schema()
