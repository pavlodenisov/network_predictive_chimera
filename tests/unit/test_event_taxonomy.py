"""The machine taxonomy must stay in sync with docs/EVENT_TAXONOMY.md (CLAUDE.md #9)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from intelligence.events.taxonomy import (
    ALL_EVENT_TYPE_VALUES,
    EVENT_TYPES,
    INFERENCE_TYPES,
    EventType,
    default_confidence,
    spec_for,
)

_DOC = Path(__file__).resolve().parents[2] / "docs" / "EVENT_TAXONOMY.md"
_DOC_TOKENS = set(re.findall(r"`([A-Z][A-Z_]{3,})`", _DOC.read_text()))


@pytest.mark.parametrize("event_type", sorted(ALL_EVENT_TYPE_VALUES))
def test_every_event_type_is_documented(event_type: str) -> None:
    assert event_type in _DOC_TOKENS, f"{event_type} missing from docs/EVENT_TAXONOMY.md"


@pytest.mark.parametrize("event_type", sorted(ALL_EVENT_TYPE_VALUES))
def test_every_event_type_has_a_spec(event_type: str) -> None:
    spec = spec_for(event_type)
    assert spec is not None
    assert spec.severity in {"low", "medium", "high"}
    assert spec.ttl_days > 0
    assert spec.scoring_models  # at least one model consumes it


def test_taxonomy_and_enum_agree() -> None:
    assert set(EVENT_TYPES.keys()) == set(EventType)


def test_inference_types_are_marked() -> None:
    assert "POSSIBLE_COMPANY_FORMATION" in INFERENCE_TYPES
    assert "STEALTH_COMPANY_SIGNAL" in INFERENCE_TYPES
    # a directly-observable change is NOT an inference
    assert "EMPLOYMENT_ENDED" not in INFERENCE_TYPES


def test_default_confidence_is_deterministic_and_bounded() -> None:
    # tier 1, direct, deterministic parse -> 1.0
    assert default_confidence(reliability_tier=1) == 1.0
    # tier 3 self-reported -> 0.7
    assert default_confidence(reliability_tier=3) == 0.7
    # third-party report (directness 0.7) at tier 4 -> 0.55 * 0.7
    assert default_confidence(reliability_tier=4, directness=0.7) == pytest.approx(0.39, abs=0.01)
    assert 0.0 <= default_confidence(reliability_tier=5, extraction=0.1) <= 1.0
