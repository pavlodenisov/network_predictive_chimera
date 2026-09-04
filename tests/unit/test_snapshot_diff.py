"""Repeated-profile-snapshot diffing (spec §49-50, acceptance §62)."""

from __future__ import annotations

from datetime import date

from intelligence.events.taxonomy import EventType
from intelligence.facts import FactType, is_unknown
from intelligence.snapshot.diff import diff_profile_snapshots, headline_is_material_change

WEEK1 = {
    "headline": "Staff ML Engineer at Synthetic AI Labs",
    "current_company": "Synthetic AI Labs",
    "current_title": "Staff ML Engineer",
    "current_seniority": "senior_ic",
    "location": "San Francisco, CA",
}
WEEK2 = {
    "headline": "Building",
    "current_company": None,
    "current_title": None,
    "location": "San Francisco, CA",
}


def _types(items) -> set[str]:
    return {str(getattr(i, "event_type", getattr(i, "fact_type", ""))) for i in items}


def test_headline_materiality_ignores_cosmetic_edits() -> None:
    assert headline_is_material_change("Staff Engineer at X", "staff engineer at x.") is False
    assert headline_is_material_change("Staff Engineer at X", "Senior Staff Engineer at X") is False
    assert headline_is_material_change("Staff ML Engineer at Synthetic AI Labs", "Building") is True
    assert headline_is_material_change(None, None) is False


def test_sarah_chen_week2_diff_produces_expected_signals() -> None:
    out = diff_profile_snapshots(WEEK1, WEEK2, occurred_on=date(2026, 8, 31))

    event_types = _types(out.events)
    assert EventType.EMPLOYMENT_ENDED in event_types
    assert EventType.HEADLINE_CHANGED in event_types

    fact_types = _types(out.facts)
    assert FactType.EMPLOYMENT_ENDED_AT in fact_types
    assert FactType.HEADLINE_CHANGED in fact_types

    # POSSIBLE_COMPANY_FORMATION must be an INFERENCE, not a plain event
    pcf = [e for e in out.events if str(e.event_type) == EventType.POSSIBLE_COMPANY_FORMATION]
    assert pcf and pcf[0].is_inference is True
    assert 0.5 <= pcf[0].probability <= 0.85

    # the EMPLOYMENT_ENDED signal names the prior employer
    ended = [e for e in out.events if str(e.event_type) == EventType.EMPLOYMENT_ENDED][0]
    assert ended.organization_name == "Synthetic AI Labs"
    assert ended.is_inference is False


def test_no_change_snapshot_is_quiet() -> None:
    out = diff_profile_snapshots(WEEK1, dict(WEEK1))
    assert out.is_empty()


def test_promotion_detected_on_seniority_increase() -> None:
    prev = {
        "current_company": "X",
        "current_title": "Senior Engineer",
        "current_seniority": "senior_ic",
    }
    curr = {
        "current_company": "X",
        "current_title": "Director of Eng",
        "current_seniority": "director",
    }
    out = diff_profile_snapshots(prev, curr)
    assert EventType.PROMOTION in _types(out.events)


def test_unknown_helper() -> None:
    assert is_unknown({"status": "unknown"}) is True
    assert is_unknown({"value": 0, "status": "known"}) is False
    assert is_unknown(None) is True
