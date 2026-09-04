"""Generic profile-snapshot diff + materiality rules.

Input: two normalized profile snapshots (``dict``), ``prev`` and ``curr``. Each may carry:
``headline``, ``current_company``, ``current_title``, ``current_seniority``,
``current_function``, ``location``, ``founder_status`` (bool), ``open_to_work`` (bool),
``building`` (bool), ``board_roles`` (list[str]).

Output: an ``ExtractionOutput`` — directly-observed changes as ``facts`` / non-inference
``events``; interpretation as ``events`` with ``is_inference=True`` (routed to the
``inference`` table by the writer).

"Do not consider every text edit a major event" (spec §50) — see ``headline_is_material_change``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from intelligence.events.taxonomy import EventType
from intelligence.facts import FactType, known
from intelligence.models.enums import SENIORITY_LADDER
from intelligence.schemas.extraction import ExtractedEvent, ExtractedFact, ExtractionOutput

MATERIAL_PROFILE_FIELDS = (
    "headline",
    "current_company",
    "current_title",
    "current_seniority",
    "location",
    "founder_status",
    "open_to_work",
    "building",
)

_BUILDING_RE = re.compile(
    r"\b(building|stealth|working on something new|founder|co[- ]?founder|"
    r"something new|new (?:company|venture|thing)|0\s*to\s*1)\b",
    re.IGNORECASE,
)
_STEALTH_RE = re.compile(r"\b(stealth|quietly building|under wraps)\b", re.IGNORECASE)
_FOUNDER_RE = re.compile(
    r"\b(founder|co[- ]?founder|founding (?:team|engineer)|ceo & founder)\b", re.IGNORECASE
)
_COFOUNDER_SEARCH_RE = re.compile(
    r"\b(looking for a (?:technical )?co[- ]?founder|cofounder wanted)\b", re.IGNORECASE
)
_HIRING_RE = re.compile(r"\b(we'?re hiring|now hiring|join us|hiring across)\b", re.IGNORECASE)
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "at",
        "of",
        "in",
        "on",
        "for",
        "to",
        "and",
        "or",
        "with",
        "building",
        "builds",
        "is",
        "are",
        "i'm",
        "im",
        "my",
        "me",
        "new",
    ]
)


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 1}


def headline_is_material_change(old: str | None, new: str | None) -> bool:
    """A headline change is material only if the meaningful token set shifts enough — not
    for casing, punctuation, or a one-word tweak (spec §50 materiality rules)."""
    if (old or "").strip() == (new or "").strip():
        return False
    old_t, new_t = _tokens(old), _tokens(new)
    if not old_t and not new_t:
        return False
    symdiff = old_t.symmetric_difference(new_t)
    union = old_t | new_t or {"x"}
    # material if >=2 meaningful tokens changed OR >35% of the token set turned over
    return len(symdiff) >= 2 or (len(symdiff) / len(union)) > 0.35


@dataclass(slots=True)
class ProfileDiff:
    changed_fields: dict[str, tuple[object, object]] = field(default_factory=dict)
    output: ExtractionOutput = field(default_factory=ExtractionOutput)


def _seniority_rank(value: str | None) -> int:
    return SENIORITY_LADDER.get((value or "").lower(), 0)


def diff_profile_snapshots(
    prev: dict | None,
    curr: dict,
    *,
    occurred_on: date | None = None,
) -> ExtractionOutput:
    prev = prev or {}
    out = ExtractionOutput()
    changed: dict[str, tuple[object, object]] = {}
    for f in MATERIAL_PROFILE_FIELDS:
        if prev.get(f) != curr.get(f):
            changed[f] = (prev.get(f), curr.get(f))

    prev_company = (prev.get("current_company") or "").strip()
    curr_company = (curr.get("current_company") or "").strip()
    prev_headline = prev.get("headline")
    curr_headline = curr.get("headline")

    employment_ended = False

    # --- employment transitions -------------------------------------------------
    if prev_company and prev_company != curr_company:
        employment_ended = True
        out.facts.append(
            ExtractedFact(
                fact_type=FactType.EMPLOYMENT_ENDED_AT,
                value=known(True),
                confidence=0.95,
                occurred_at=occurred_on,
                organization_name=prev_company,
                evidence_quote=f"snapshot: current_company '{prev_company}' -> "
                f"'{curr_company or 'none'}'",
            )
        )
        out.events.append(
            ExtractedEvent(
                event_type=EventType.EMPLOYMENT_ENDED,
                organization_name=prev_company,
                occurred_at=occurred_on,
                confidence=0.95,
            )
        )
    if curr_company and curr_company != prev_company:
        out.facts.append(
            ExtractedFact(
                fact_type=FactType.CURRENT_TITLE,
                value=known(curr.get("current_title") or "unknown"),
                confidence=0.9,
                occurred_at=occurred_on,
                organization_name=curr_company,
            )
        )
        out.events.append(
            ExtractedEvent(
                event_type=EventType.EMPLOYMENT_STARTED,
                organization_name=curr_company,
                occurred_at=occurred_on,
                confidence=0.9,
            )
        )

    # --- title / promotion at the same employer ------------------------------
    if (
        prev_company
        and prev_company == curr_company
        and prev.get("current_title") != curr.get("current_title")
    ):
        out.events.append(
            ExtractedEvent(
                event_type=EventType.TITLE_CHANGED,
                organization_name=curr_company,
                occurred_at=occurred_on,
                confidence=0.9,
            )
        )
        if _seniority_rank(curr.get("current_seniority")) > _seniority_rank(
            prev.get("current_seniority")
        ):
            out.events.append(
                ExtractedEvent(
                    event_type=EventType.PROMOTION,
                    organization_name=curr_company,
                    occurred_at=occurred_on,
                    confidence=0.9,
                )
            )

    # --- headline -------------------------------------------------------------
    headline_material = headline_is_material_change(prev_headline, curr_headline)
    if headline_material:
        out.facts.append(
            ExtractedFact(
                fact_type=FactType.HEADLINE_CHANGED,
                value=known({"from": prev_headline, "to": curr_headline}),
                confidence=0.98,
                occurred_at=occurred_on,
                evidence_quote=f"headline: '{prev_headline}' -> '{curr_headline}'",
            )
        )
        out.facts.append(
            ExtractedFact(
                fact_type=FactType.HEADLINE_TEXT,
                value=known(curr_headline or ""),
                confidence=0.99,
                occurred_at=occurred_on,
            )
        )
        out.events.append(
            ExtractedEvent(
                event_type=EventType.HEADLINE_CHANGED, occurred_at=occurred_on, confidence=0.98
            )
        )

    building_now = bool(curr.get("building")) or bool(_BUILDING_RE.search(curr_headline or ""))
    building_before = bool(prev.get("building")) or bool(_BUILDING_RE.search(prev_headline or ""))
    founder_now = bool(curr.get("founder_status")) or bool(_FOUNDER_RE.search(curr_headline or ""))
    founder_before = bool(prev.get("founder_status")) or bool(
        _FOUNDER_RE.search(prev_headline or "")
    )

    if founder_now and not founder_before:
        out.events.append(
            ExtractedEvent(
                event_type=EventType.FOUNDER_TITLE_ADDED, occurred_at=occurred_on, confidence=0.95
            )
        )
    if _STEALTH_RE.search(curr_headline or "") and not _STEALTH_RE.search(prev_headline or ""):
        out.events.append(
            ExtractedEvent(
                event_type=EventType.STEALTH_COMPANY_SIGNAL,
                occurred_at=occurred_on,
                confidence=0.8,
                is_inference=True,
                probability=0.7,
                explanation_code="HEADLINE_STEALTH_LANGUAGE",
            )
        )
    if _COFOUNDER_SEARCH_RE.search(curr_headline or ""):
        out.events.append(
            ExtractedEvent(
                event_type=EventType.COFOUNDER_SEARCH, occurred_at=occurred_on, confidence=0.85
            )
        )
    if _HIRING_RE.search(curr_headline or "") and not _HIRING_RE.search(prev_headline or ""):
        out.events.append(
            ExtractedEvent(
                event_type=EventType.HIRING_STARTED, occurred_at=occurred_on, confidence=0.7
            )
        )

    # --- combination inference: possible company formation ---------------------
    signals = 0
    reasons: list[str] = []
    if employment_ended:
        signals += 1
        reasons.append("EMPLOYMENT_ENDED")
    if building_now and not building_before:
        signals += 1
        reasons.append("BUILDING_HEADLINE")
    if _STEALTH_RE.search(curr_headline or ""):
        signals += 1
        reasons.append("STEALTH_LANGUAGE")
    if founder_now and not founder_before:
        signals += 1
        reasons.append("FOUNDER_TITLE")
    if signals >= 1 and (building_now or founder_now or _STEALTH_RE.search(curr_headline or "")):
        probability = min(0.85, 0.35 + 0.2 * signals)
        out.events.append(
            ExtractedEvent(
                event_type=EventType.POSSIBLE_COMPANY_FORMATION,
                occurred_at=occurred_on,
                confidence=round(probability, 2),
                is_inference=True,
                probability=round(probability, 4),
                explanation_code=("+".join(reasons) or "SNAPSHOT_SIGNALS")[:64],
            )
        )

    # --- availability (declared only) & location ---------------------------
    if curr.get("open_to_work") and not prev.get("open_to_work"):
        out.facts.append(
            ExtractedFact(
                fact_type=FactType.OPEN_TO_WORK_DECLARED,
                value=known(True),
                confidence=0.95,
                occurred_at=occurred_on,
            )
        )
        out.events.append(
            ExtractedEvent(
                event_type=EventType.OPEN_TO_WORK_SIGNAL, occurred_at=occurred_on, confidence=0.9
            )
        )
    if "location" in changed and curr.get("location"):
        out.facts.append(
            ExtractedFact(
                fact_type=FactType.LOCATION,
                value=known(curr.get("location")),
                confidence=0.85,
                occurred_at=occurred_on,
            )
        )

    return out
