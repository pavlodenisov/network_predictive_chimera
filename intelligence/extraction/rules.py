"""Deterministic rule-based extractor (default; spec §22).

Fully offline and reproducible. Handles three shapes:
1. profile snapshots (with an optional ``previous_snapshot``) -> ``snapshot.diff``
2. structured records carrying explicit ``fact_type`` / ``event_type`` keys -> pass-through
3. free text (news / activity posts) -> keyword rules

It never guesses a value it cannot support; unsupported input yields an empty output, not
a fabricated one.
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime

from intelligence.events.taxonomy import EventType
from intelligence.extraction.base import ExtractionRequest, ExtractionResult
from intelligence.facts import FactType, known, unknown
from intelligence.schemas.extraction import (
    ExtractedEntity,
    ExtractedEvent,
    ExtractedFact,
    ExtractionOutput,
)
from intelligence.snapshot.diff import diff_profile_snapshots

_PROMPT_VERSION = "rules_v0.1"
_MODEL_VERSION = "rules_v0.1"

_ORG_AFTER = re.compile(
    r"\b(?:at|from|joined|joins|joining|left|leaving|departs?|departing)\s+"
    r"([A-Z][A-Za-z0-9&.\- ]{1,40}?)(?=[\s,.;:]|$)"
)
_RAISED = re.compile(r"\brais(?:e|ed|ing)\s+\$?\s?(\d[\d.,]*)\s*(k|m|bn|b|million|billion)?", re.I)
_SERIES = re.compile(r"\b(pre-?seed|seed|series\s+[a-e])\b", re.I)
_LAUNCH = re.compile(r"\b(launch(?:ed|ing)?|introducing|unveil(?:ed|ing)?|now available)\b", re.I)
_STEALTH = re.compile(r"\bstealth\b", re.I)
# "building a company", "working on something new", "starting a company", "new startup" —
# deliberately NOT "a new venture allocation" / "new fund" (that's LP language).
_BUILDING = re.compile(
    r"\b(building (?:a|his|her|their|out) \w+|working on something new|starting (?:a|his|her|their) "
    r"(?:company|startup|venture)|(?:new|early-stage) startup|(?:in|now in) stealth)\b",
    re.I,
)
_OPEN_TO_WORK = re.compile(r"\bopen to (?:work|new (?:roles|opportunities))\b", re.I)
_PARTNER = re.compile(r"\b(joined|promoted to|named)\s+(?:as\s+)?partner\b", re.I)
_CIO = re.compile(r"\b(chief investment officer|\bCIO\b)\b")
_MANDATE = re.compile(
    r"\b(venture (?:allocation|mandate)|allocate to venture|alternatives mandate)\b", re.I
)
_PATENT = re.compile(r"\bpatent\b", re.I)
_PAPER = re.compile(r"\b(arxiv|published a paper|paper accepted|preprint)\b", re.I)
_ACQUIRED = re.compile(r"\b(acquired by|acquisition of|has acquired)\b", re.I)


def _clean_org(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip(" .,-")


class RuleBasedExtractor:
    name = "rules"
    prompt_version = _PROMPT_VERSION
    model_version = _MODEL_VERSION

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        started = time.perf_counter()
        try:
            output = self._dispatch(request)
            status = "ok"
            error = None
        except Exception as exc:  # noqa: BLE001 - recorded as a failed run, never silent
            output, status, error = ExtractionOutput(), "failed", repr(exc)
        return ExtractionResult(
            output=output,
            parse_status=status,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error=error,
            prompt_version=self.prompt_version,
            model_version=self.model_version,
        )

    # ------------------------------------------------------------------ dispatch
    def _dispatch(self, request: ExtractionRequest) -> ExtractionOutput:
        ctype = request.content_type
        rj = request.raw_json or {}

        if ctype == "profile_snapshot":
            profile = rj.get("profile", rj)
            occurred = _as_date(rj.get("observed_on") or rj.get("as_of"))
            if request.previous_snapshot is not None:
                return diff_profile_snapshots(
                    request.previous_snapshot, profile, occurred_on=occurred
                )
            return self._baseline_profile(profile, occurred)

        if ctype in ("json_record", "csv_row") and ("fact_type" in rj or "event_type" in rj):
            return self._structured_record(rj)

        text = " ".join(
            p for p in (request.raw_text, rj.get("title"), rj.get("body"), rj.get("summary")) if p
        ).strip()
        if text:
            return self._free_text(text, request)
        return ExtractionOutput()

    # --------------------------------------------------------- baseline profile
    def _baseline_profile(self, profile: dict, occurred: date | None) -> ExtractionOutput:
        out = ExtractionOutput()
        if profile.get("headline"):
            out.facts.append(
                ExtractedFact(
                    fact_type=FactType.HEADLINE_TEXT,
                    value=known(profile["headline"]),
                    confidence=0.99,
                    occurred_at=occurred,
                )
            )
        if profile.get("current_title") and profile.get("current_company"):
            out.facts.append(
                ExtractedFact(
                    fact_type=FactType.CURRENT_TITLE,
                    value=known(profile["current_title"]),
                    confidence=0.95,
                    organization_name=profile["current_company"],
                    occurred_at=occurred,
                )
            )
        if profile.get("location"):
            out.facts.append(
                ExtractedFact(
                    fact_type=FactType.LOCATION,
                    value=known(profile["location"]),
                    confidence=0.9,
                    occurred_at=occurred,
                )
            )
        for key, ft in (
            ("years_domain_experience", FactType.YEARS_DOMAIN_EXPERIENCE),
            ("years_engineering_experience", FactType.YEARS_ENGINEERING_EXPERIENCE),
            ("patent_count", FactType.PATENT_COUNT),
            ("publication_count", FactType.PUBLICATION_COUNT),
            ("companies_founded", FactType.COMPANIES_FOUNDED_COUNT),
            ("promotion_count", FactType.PROMOTION_COUNT),
            ("team_size_managed", FactType.TEAM_SIZE_MANAGED),
            ("early_employee_rank", FactType.EARLY_EMPLOYEE_RANK),
        ):
            if key in profile and profile[key] is not None:
                out.facts.append(
                    ExtractedFact(
                        fact_type=ft,
                        value=known(profile[key], _unit_for(key)),
                        confidence=0.9,
                        occurred_at=occurred,
                    )
                )
        for key, ft in (
            ("prior_exit", FactType.PRIOR_EXIT),
            ("prior_founder", FactType.PRIOR_FOUNDER),
            ("institutional_fundraise", FactType.INSTITUTIONAL_FUNDRAISE),
            ("product_shipped", FactType.PRODUCT_SHIPPED),
            ("budget_ownership", FactType.BUDGET_OWNERSHIP),
            ("oss_major", FactType.OSS_PROJECT_MAJOR),
            ("verified_scale_milestone", FactType.VERIFIED_SCALE_MILESTONE),
        ):
            if key in profile:
                out.facts.append(
                    ExtractedFact(
                        fact_type=ft,
                        value=known(bool(profile[key])),
                        confidence=0.9,
                        occurred_at=occurred,
                    )
                )
        # explicit unknowns are recorded as unknown, never as a default
        if profile.get("fundraising_status") in (None, "unknown", ""):
            out.facts.append(
                ExtractedFact(
                    fact_type=FactType.FUNDRAISING_STATUS,
                    value=unknown(),
                    confidence=1.0,
                    occurred_at=occurred,
                )
            )
        return out

    # --------------------------------------------------------- structured record
    def _structured_record(self, rj: dict) -> ExtractionOutput:
        out = ExtractionOutput()
        occurred = _as_date(rj.get("occurred_at"))
        if "fact_type" in rj:
            if isinstance(rj.get("value"), dict):
                value = rj["value"]
            elif rj.get("raw_value") is not None:
                value = known(rj["raw_value"], rj.get("unit"))
            else:
                value = unknown()
            out.facts.append(
                ExtractedFact(
                    fact_type=rj["fact_type"],
                    value=value,
                    confidence=float(rj.get("confidence", 0.9)),
                    occurred_at=occurred,
                    organization_name=rj.get("organization_name"),
                    evidence_quote=rj.get("evidence_quote"),
                )
            )
        if "event_type" in rj:
            out.events.append(
                ExtractedEvent(
                    event_type=rj["event_type"],
                    organization_name=rj.get("organization_name"),
                    occurred_at=occurred,
                    confidence=float(rj.get("confidence", 0.9)),
                    is_inference=bool(rj.get("is_inference", False)),
                    probability=rj.get("probability"),
                    explanation_code=rj.get("explanation_code"),
                )
            )
        return out

    # ------------------------------------------------------------------ free text
    def _free_text(self, text: str, request: ExtractionRequest) -> ExtractionOutput:
        out = ExtractionOutput()
        low = text.lower()
        orgs = [_clean_org(m.group(1)) for m in _ORG_AFTER.finditer(text)]
        for o in dict.fromkeys(orgs):
            out.entities.append(ExtractedEntity(kind="organization", name=o))
        if request.subject_hint:
            out.entities.append(ExtractedEntity(kind="person", name=request.subject_hint))

        if request.content_type == "news_article" and request.subject_hint:
            out.events.append(ExtractedEvent(event_type=EventType.NEWS_MENTION, confidence=0.75))

        if any(k in low for k in ("left ", "leaving ", "departed", "stepping down", "after ")) and (
            "years at" in low or "left " in low or "departing" in low
        ):
            org = orgs[0] if orgs else None
            out.events.append(
                ExtractedEvent(
                    event_type=EventType.EMPLOYMENT_ENDED, organization_name=org, confidence=0.8
                )
            )
            out.facts.append(
                ExtractedFact(
                    fact_type=FactType.EMPLOYMENT_ENDED_AT,
                    value=known(True),
                    confidence=0.8,
                    organization_name=org,
                    evidence_quote=_snippet(text, "left", "after", "depart"),
                )
            )

        m = _RAISED.search(text)
        if m and _SERIES.search(text):
            out.events.append(
                ExtractedEvent(event_type=EventType.FUNDRAISE_ANNOUNCED, confidence=0.85)
            )
            out.facts.append(
                ExtractedFact(
                    fact_type=FactType.INSTITUTIONAL_FUNDRAISE,
                    value=known(True),
                    confidence=0.85,
                    evidence_quote=_snippet(text, "rais", "seed", "series"),
                )
            )

        if _LAUNCH.search(text) and any(
            k in low
            for k in ("product", "platform", "app", "tool", "model", "project", "infrastructure")
        ):
            is_infra = "infrastructure" in low or "infra" in low
            out.events.append(
                ExtractedEvent(
                    event_type=EventType.TECHNICAL_PROJECT_LAUNCHED
                    if is_infra
                    else EventType.PRODUCT_LAUNCH,
                    confidence=0.75,
                )
            )
            out.facts.append(
                ExtractedFact(
                    fact_type=FactType.PRODUCT_SHIPPED,
                    value=known(True),
                    confidence=0.7,
                    evidence_quote=_snippet(text, "launch", "introduc", "unveil"),
                )
            )

        if _STEALTH.search(text):
            out.events.append(
                ExtractedEvent(
                    event_type=EventType.STEALTH_COMPANY_SIGNAL,
                    confidence=0.75,
                    is_inference=True,
                    probability=0.65,
                    explanation_code="TEXT_STEALTH_LANGUAGE",
                )
            )
        if _BUILDING.search(text) and request.content_type != "profile_snapshot":
            out.events.append(
                ExtractedEvent(
                    event_type=EventType.POSSIBLE_COMPANY_FORMATION,
                    confidence=0.55,
                    is_inference=True,
                    probability=0.5,
                    explanation_code="TEXT_BUILDING_LANGUAGE",
                )
            )
        if re.search(r"looking for a (?:technical )?co-?founder", low):
            out.events.append(ExtractedEvent(event_type=EventType.COFOUNDER_SEARCH, confidence=0.8))
        if _OPEN_TO_WORK.search(text):
            out.events.append(
                ExtractedEvent(event_type=EventType.OPEN_TO_WORK_SIGNAL, confidence=0.85)
            )
            out.facts.append(
                ExtractedFact(
                    fact_type=FactType.OPEN_TO_WORK_DECLARED,
                    value=known(True),
                    confidence=0.85,
                )
            )
        if _PARTNER.search(text):
            out.events.append(
                ExtractedEvent(
                    event_type=EventType.PARTNER_ROLE_STARTED,
                    organization_name=orgs[0] if orgs else None,
                    confidence=0.8,
                )
            )
        if _CIO.search(text) and any(
            k in low for k in ("appointed", "named", "joins", "joined", "new")
        ):
            out.events.append(
                ExtractedEvent(
                    event_type=EventType.CIO_ROLE_STARTED,
                    organization_name=orgs[0] if orgs else None,
                    confidence=0.8,
                )
            )
        if _MANDATE.search(text):
            out.events.append(
                ExtractedEvent(event_type=EventType.INVESTMENT_MANDATE_CHANGED, confidence=0.8)
            )
            out.facts.append(
                ExtractedFact(
                    fact_type=FactType.INVESTMENT_MANDATE,
                    value=known("venture allocation"),
                    confidence=0.8,
                    evidence_quote=_snippet(text, "venture", "mandate", "allocat"),
                )
            )
        if _PATENT.search(text):
            out.events.append(ExtractedEvent(event_type=EventType.PATENT_FILED, confidence=0.7))
        if _PAPER.search(text):
            out.events.append(ExtractedEvent(event_type=EventType.PAPER_PUBLISHED, confidence=0.7))
        if _ACQUIRED.search(text):
            out.events.append(
                ExtractedEvent(
                    event_type=EventType.COMPANY_ACQUIRED,
                    organization_name=orgs[0] if orgs else None,
                    confidence=0.8,
                )
            )
        return out


def _unit_for(key: str) -> str | None:
    if key.startswith("years_"):
        return "years"
    if key.endswith(("_count", "_size", "_rank")) or "founded" in key:
        return "count"
    return None


def _as_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
    return None


def _snippet(text: str, *needles: str, width: int = 120) -> str:
    low = text.lower()
    for n in needles:
        i = low.find(n.lower())
        if i >= 0:
            start = max(0, i - width // 3)
            return text[start : start + width].strip()
    return text[:width].strip()
