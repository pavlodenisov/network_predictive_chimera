"""Runs an extractor over an observation and persists an ``ExtractionRun`` (spec §23).

Gives extraction full observability: prompt/model version, input observation ids, output,
parse status, latency, token usage. Malformed output is recorded, never silently dropped.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from intelligence.extraction.base import ExtractionRequest, ExtractionResult, Extractor
from intelligence.models import ExtractionRun, RawObservation, Source
from intelligence.models.enums import ParseStatus
from intelligence.observability import get_logger

log = get_logger("chimera.extraction")


def build_request(
    session: Session,
    observation: RawObservation,
    *,
    previous_snapshot: dict | None = None,
) -> ExtractionRequest:
    source = session.get(Source, observation.source_id)
    return ExtractionRequest(
        observation_id=str(observation.id),
        content_type=observation.content_type,
        raw_text=observation.raw_text,
        raw_json=observation.raw_json,
        subject_hint=observation.subject_hint,
        source_provider=source.provider if source else "unknown",
        reliability_tier=source.reliability_tier if source else 3,
        previous_snapshot=previous_snapshot,
    )


def run_extraction(
    session: Session,
    extractor: Extractor,
    observation: RawObservation,
    *,
    previous_snapshot: dict | None = None,
) -> ExtractionResult:
    request = build_request(session, observation, previous_snapshot=previous_snapshot)
    result = extractor.extract(request)

    session.add(
        ExtractionRun(
            observation_id=observation.id,
            extractor_name=extractor.name,
            prompt_version=result.prompt_version or getattr(extractor, "prompt_version", ""),
            model_version=result.model_version or getattr(extractor, "model_version", ""),
            input_observation_ids=[str(observation.id)],
            output=result.output.model_dump(mode="json")
            if result.parse_status != "failed"
            else None,
            parse_status=result.parse_status,
            error=result.error,
            latency_ms=result.latency_ms,
            token_usage=result.token_usage,
        )
    )
    session.flush()

    if result.parse_status == ParseStatus.FAILED:
        log.warning(
            "extraction.failed",
            observation_id=str(observation.id),
            extractor=extractor.name,
            error=result.error,
        )
    return result
