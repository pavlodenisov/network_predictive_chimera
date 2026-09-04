"""Claude-backed extractor (spec §22-23). INACTIVE unless ``CHIMERA_EXTRACTOR=claude``
and ``ANTHROPIC_API_KEY`` are set — the deterministic ``RuleBasedExtractor`` is the default
and powers the reproducible weekly demo.

The LLM is used ONLY to turn unstructured text into the strict ``ExtractionOutput`` schema.
It never produces a score. Output is schema-validated; on invalid output the runner retries
once with the validation error as feedback, then records a failed ``ExtractionRun``.
"""

from __future__ import annotations

import json
import time

from pydantic import ValidationError

from intelligence.config import get_settings
from intelligence.extraction.base import ExtractionRequest, ExtractionResult
from intelligence.schemas.extraction import EXTRACTION_JSON_SCHEMA, ExtractionOutput

_PROMPT_VERSION = "claude_extract_v0.1"

_SYSTEM = (
    "You extract STRUCTURED FACTS AND EVENTS from professional/news text for an analytical "
    "intelligence system. You never rate, score, or editorialize. You never invent values. "
    "If something is not stated, omit it or mark it unknown. Output ONLY JSON matching the "
    "provided schema. Use only the enum values given. Distinguish directly-observed facts "
    "from interpretation (set is_inference=true with a probability for interpretation)."
)


class ClaudeExtractor:
    name = "claude"
    prompt_version = _PROMPT_VERSION

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ClaudeExtractor requires ANTHROPIC_API_KEY. Set CHIMERA_EXTRACTOR=rules "
                "for the offline deterministic pipeline."
            )
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "The 'anthropic' package is not installed. `pip install anthropic` or use "
                "CHIMERA_EXTRACTOR=rules."
            ) from exc
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model_version = settings.claude_model

    def _prompt(self, request: ExtractionRequest, feedback: str | None) -> str:
        parts = [
            "SCHEMA:",
            json.dumps(EXTRACTION_JSON_SCHEMA),
            f"\nCONTENT_TYPE: {request.content_type}",
            f"SUBJECT_HINT: {request.subject_hint or 'unknown'}",
        ]
        if request.previous_snapshot is not None:
            parts.append(f"PREVIOUS_SNAPSHOT: {json.dumps(request.previous_snapshot)}")
        if request.raw_json:
            parts.append(f"RECORD_JSON: {json.dumps(request.raw_json)}")
        if request.raw_text:
            parts.append(f"TEXT:\n{request.raw_text}")
        if feedback:
            parts.append(
                f"\nYOUR PREVIOUS OUTPUT WAS INVALID: {feedback}\nReturn corrected JSON only."
            )
        return "\n".join(parts)

    def _call(self, prompt: str) -> tuple[str, dict]:
        resp = self._client.messages.create(
            model=self.model_version,
            max_tokens=2000,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        usage = {
            "input_tokens": getattr(resp.usage, "input_tokens", None),
            "output_tokens": getattr(resp.usage, "output_tokens", None),
        }
        return text, usage

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        started = time.perf_counter()
        feedback: str | None = None
        last_error: str | None = None
        usage: dict | None = None
        raw: str | None = None
        for attempt in (1, 2):
            try:
                raw, usage = self._call(self._prompt(request, feedback))
                payload = _json_object(raw)
                output = ExtractionOutput.model_validate(payload)
                return ExtractionResult(
                    output=output,
                    parse_status="ok" if attempt == 1 else "invalid_retried_ok",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    token_usage=usage,
                    attempts=attempt,
                    prompt_version=self.prompt_version,
                    model_version=self.model_version,
                    raw_response={"text": raw},
                )
            except (ValidationError, ValueError) as exc:
                last_error = str(exc)
                feedback = last_error[:1200]
            except Exception as exc:  # pragma: no cover - network/API errors
                last_error = repr(exc)
                break
        return ExtractionResult(
            output=ExtractionOutput(),
            parse_status="failed",
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=last_error,
            token_usage=usage,
            attempts=2,
            prompt_version=self.prompt_version,
            model_version=self.model_version,
            raw_response={"text": raw} if raw else None,
        )


def _json_object(text: str) -> dict:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start : end + 1])
