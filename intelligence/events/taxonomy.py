"""Versioned event taxonomy — the machine copy of ``docs/EVENT_TAXONOMY.md``.

``tests/unit/test_event_taxonomy.py`` asserts the two stay in sync. Adding an event type
requires: a row in the doc, an entry here, a detector branch, and a test (CLAUDE.md #9).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

EVENT_TAXONOMY_VERSION = "events_v0.1"

# Source reliability tier -> weight (spec §55; docs/EVENT_TAXONOMY.md).
TIER_WEIGHT: dict[int, float] = {1: 1.0, 2: 0.85, 3: 0.7, 4: 0.55, 5: 0.35}


class EventType(StrEnum):
    # --- employment ---
    EMPLOYMENT_STARTED = "EMPLOYMENT_STARTED"
    EMPLOYMENT_ENDED = "EMPLOYMENT_ENDED"
    TITLE_CHANGED = "TITLE_CHANGED"
    PROMOTION = "PROMOTION"
    SENIORITY_INCREASED = "SENIORITY_INCREASED"
    BOARD_ROLE_STARTED = "BOARD_ROLE_STARTED"
    ADVISOR_ROLE_STARTED = "ADVISOR_ROLE_STARTED"
    # --- founder ---
    FOUNDER_TITLE_ADDED = "FOUNDER_TITLE_ADDED"
    COMPANY_FORMATION_CONFIRMED = "COMPANY_FORMATION_CONFIRMED"
    POSSIBLE_COMPANY_FORMATION = "POSSIBLE_COMPANY_FORMATION"
    STEALTH_COMPANY_SIGNAL = "STEALTH_COMPANY_SIGNAL"
    COFOUNDER_SEARCH = "COFOUNDER_SEARCH"
    PRODUCT_LAUNCH = "PRODUCT_LAUNCH"
    COMPANY_WEBSITE_LAUNCHED = "COMPANY_WEBSITE_LAUNCHED"
    FUNDRAISE_ANNOUNCED = "FUNDRAISE_ANNOUNCED"
    FUNDING_ROUND_CONFIRMED = "FUNDING_ROUND_CONFIRMED"
    ACCELERATOR_JOINED = "ACCELERATOR_JOINED"
    COMPANY_EXIT = "COMPANY_EXIT"
    COMPANY_ACQUIRED = "COMPANY_ACQUIRED"
    HIRING_STARTED = "HIRING_STARTED"
    DOMAIN_ACTIVITY_SPIKE = "DOMAIN_ACTIVITY_SPIKE"
    HEADLINE_CHANGED = "HEADLINE_CHANGED"
    # --- research / technical ---
    PAPER_PUBLISHED = "PAPER_PUBLISHED"
    PATENT_FILED = "PATENT_FILED"
    OPEN_SOURCE_PROJECT_LAUNCHED = "OPEN_SOURCE_PROJECT_LAUNCHED"
    TECHNICAL_PROJECT_LAUNCHED = "TECHNICAL_PROJECT_LAUNCHED"
    RESEARCH_COMMERCIALIZATION_SIGNAL = "RESEARCH_COMMERCIALIZATION_SIGNAL"
    # --- lp ---
    LP_ROLE_STARTED = "LP_ROLE_STARTED"
    FAMILY_OFFICE_ROLE_STARTED = "FAMILY_OFFICE_ROLE_STARTED"
    CIO_ROLE_STARTED = "CIO_ROLE_STARTED"
    PARTNER_ROLE_STARTED = "PARTNER_ROLE_STARTED"
    INVESTMENT_MANDATE_CHANGED = "INVESTMENT_MANDATE_CHANGED"
    VENTURE_ALLOCATION_SIGNAL = "VENTURE_ALLOCATION_SIGNAL"
    FUND_INVESTMENT_ACTIVITY = "FUND_INVESTMENT_ACTIVITY"
    EMERGING_MANAGER_SIGNAL = "EMERGING_MANAGER_SIGNAL"
    INVESTMENT_COMMITTEE_ROLE = "INVESTMENT_COMMITTEE_ROLE"
    # --- talent ---
    PROFESSIONAL_DEPARTURE = "PROFESSIONAL_DEPARTURE"
    OPEN_TO_WORK_SIGNAL = "OPEN_TO_WORK_SIGNAL"
    NEW_EXECUTIVE_ROLE = "NEW_EXECUTIVE_ROLE"
    FUNCTIONAL_LEADERSHIP_ROLE = "FUNCTIONAL_LEADERSHIP_ROLE"
    PORTFOLIO_ROLE_MATCH_CREATED = "PORTFOLIO_ROLE_MATCH_CREATED"
    # --- network ---
    NEW_CHIMERA_CONNECTION = "NEW_CHIMERA_CONNECTION"
    RELATIONSHIP_STRENGTH_UPDATED = "RELATIONSHIP_STRENGTH_UPDATED"
    WARM_PATH_CREATED = "WARM_PATH_CREATED"
    WARM_PATH_LOST = "WARM_PATH_LOST"
    # --- general ---
    NEWS_MENTION = "NEWS_MENTION"
    AWARD = "AWARD"
    CONFERENCE_APPEARANCE = "CONFERENCE_APPEARANCE"
    PUBLIC_TALK = "PUBLIC_TALK"
    MAJOR_COMPANY_MILESTONE = "MAJOR_COMPANY_MILESTONE"


@dataclass(frozen=True, slots=True)
class EventTypeSpec:
    event_type: EventType
    category: str
    severity: str  # low | medium | high
    definition: str
    required_evidence: str
    ttl_days: int
    scoring_models: tuple[str, ...]
    #: when True the detector routes this to the ``inference`` table, not ``event``.
    is_inference: bool = False
    optional_evidence: str = ""
    notes: str = ""


def _s(*a, **kw) -> EventTypeSpec:  # brevity helper
    return EventTypeSpec(*a, **kw)


EVENT_TYPES: dict[EventType, EventTypeSpec] = {
    EventType.EMPLOYMENT_STARTED: _s(
        EventType.EMPLOYMENT_STARTED,
        "employment",
        "low",
        "A new current employment appears.",
        "employment record OR profile snapshot with a new current company",
        365,
        ("founder", "talent", "lp"),
    ),
    EventType.EMPLOYMENT_ENDED: _s(
        EventType.EMPLOYMENT_ENDED,
        "employment",
        "medium",
        "A previously-current employment gains an end date or leaves the current slot.",
        "prior snapshot with company X current + new snapshot without it, OR an explicit 'left' statement",
        240,
        ("founder", "talent"),
    ),
    EventType.TITLE_CHANGED: _s(
        EventType.TITLE_CHANGED,
        "employment",
        "low",
        "normalized_title changes at the same organization.",
        "two snapshots / employment records",
        180,
        ("founder", "talent", "lp"),
    ),
    EventType.PROMOTION: _s(
        EventType.PROMOTION,
        "employment",
        "medium",
        "Title change that increases seniority rank at the same organization.",
        "TITLE_CHANGED evidence + a seniority-ladder step up",
        240,
        ("founder", "lp", "talent"),
    ),
    EventType.SENIORITY_INCREASED: _s(
        EventType.SENIORITY_INCREASED,
        "employment",
        "low",
        "Seniority rank increases across a job change.",
        "employment history",
        240,
        ("talent", "lp"),
    ),
    EventType.BOARD_ROLE_STARTED: _s(
        EventType.BOARD_ROLE_STARTED,
        "employment",
        "low",
        "A new board seat.",
        "board listing / announcement",
        400,
        ("founder", "connector", "lp"),
    ),
    EventType.ADVISOR_ROLE_STARTED: _s(
        EventType.ADVISOR_ROLE_STARTED,
        "employment",
        "low",
        "A new advisory role.",
        "profile / announcement",
        300,
        ("connector",),
    ),
    EventType.FOUNDER_TITLE_ADDED: _s(
        EventType.FOUNDER_TITLE_ADDED,
        "founder",
        "high",
        "Person adds a founder / co-founder / 'building' title.",
        "profile snapshot diff OR announcement",
        200,
        ("founder",),
    ),
    EventType.COMPANY_FORMATION_CONFIRMED: _s(
        EventType.COMPANY_FORMATION_CONFIRMED,
        "founder",
        "high",
        "A company associated with the person is confirmed formed.",
        "registry / press / company site naming the person as founder",
        400,
        ("founder",),
    ),
    EventType.POSSIBLE_COMPANY_FORMATION: _s(
        EventType.POSSIBLE_COMPANY_FORMATION,
        "founder",
        "medium",
        "INFERENCE: signals suggest company formation.",
        ">=1 of: recent EMPLOYMENT_ENDED, 'building' headline, stealth language",
        150,
        ("founder",),
        is_inference=True,
    ),
    EventType.STEALTH_COMPANY_SIGNAL: _s(
        EventType.STEALTH_COMPANY_SIGNAL,
        "founder",
        "medium",
        "Headline / text indicates stealth work.",
        "profile text / post",
        150,
        ("founder",),
        is_inference=True,
    ),
    EventType.COFOUNDER_SEARCH: _s(
        EventType.COFOUNDER_SEARCH,
        "founder",
        "medium",
        "Person publicly seeking a co-founder.",
        "post / profile",
        120,
        ("founder",),
    ),
    EventType.PRODUCT_LAUNCH: _s(
        EventType.PRODUCT_LAUNCH,
        "founder",
        "medium",
        "A product tied to the person is launched.",
        "launch post / press / product site",
        200,
        ("founder",),
    ),
    EventType.COMPANY_WEBSITE_LAUNCHED: _s(
        EventType.COMPANY_WEBSITE_LAUNCHED,
        "founder",
        "low",
        "Company domain goes live.",
        "crawl / whois-style record",
        200,
        ("founder",),
    ),
    EventType.FUNDRAISE_ANNOUNCED: _s(
        EventType.FUNDRAISE_ANNOUNCED,
        "founder",
        "high",
        "A round is publicly announced.",
        "press / filing / announcement",
        300,
        ("founder",),
    ),
    EventType.FUNDING_ROUND_CONFIRMED: _s(
        EventType.FUNDING_ROUND_CONFIRMED,
        "founder",
        "high",
        "Round confirmed by a tier-1/2 source.",
        "database record / filing",
        400,
        ("founder",),
    ),
    EventType.ACCELERATOR_JOINED: _s(
        EventType.ACCELERATOR_JOINED,
        "founder",
        "medium",
        "Cohort membership.",
        "program list / announcement",
        300,
        ("founder",),
    ),
    EventType.COMPANY_EXIT: _s(
        EventType.COMPANY_EXIT,
        "founder",
        "high",
        "Company the person founded / led exits.",
        "press / database",
        3650,
        ("founder",),
    ),
    EventType.COMPANY_ACQUIRED: _s(
        EventType.COMPANY_ACQUIRED,
        "founder",
        "high",
        "Company acquired.",
        "press / database",
        3650,
        ("founder", "talent"),
    ),
    EventType.HIRING_STARTED: _s(
        EventType.HIRING_STARTED,
        "founder",
        "low",
        "Person / their company begins hiring.",
        "job posts / announcement",
        120,
        ("founder",),
    ),
    EventType.DOMAIN_ACTIVITY_SPIKE: _s(
        EventType.DOMAIN_ACTIVITY_SPIKE,
        "founder",
        "low",
        "Marked increase in domain/project activity.",
        "repo / post cadence",
        90,
        ("founder",),
    ),
    EventType.HEADLINE_CHANGED: _s(
        EventType.HEADLINE_CHANGED,
        "founder",
        "low",
        "Profile headline text materially changed.",
        "two profile snapshots",
        90,
        ("founder", "talent", "lp"),
    ),
    EventType.PAPER_PUBLISHED: _s(
        EventType.PAPER_PUBLISHED,
        "research",
        "low",
        "New publication authored.",
        "index record (arXiv / DOI-style)",
        730,
        ("founder", "talent"),
    ),
    EventType.PATENT_FILED: _s(
        EventType.PATENT_FILED,
        "research",
        "low",
        "Patent application with the person as inventor.",
        "patent record",
        1460,
        ("founder", "talent"),
    ),
    EventType.OPEN_SOURCE_PROJECT_LAUNCHED: _s(
        EventType.OPEN_SOURCE_PROJECT_LAUNCHED,
        "research",
        "low",
        "Notable new open-source repo.",
        "repo record above a stars/commits threshold",
        365,
        ("founder", "talent"),
    ),
    EventType.TECHNICAL_PROJECT_LAUNCHED: _s(
        EventType.TECHNICAL_PROJECT_LAUNCHED,
        "research",
        "low",
        "Non-OSS technical project shipped.",
        "post / site",
        200,
        ("founder",),
    ),
    EventType.RESEARCH_COMMERCIALIZATION_SIGNAL: _s(
        EventType.RESEARCH_COMMERCIALIZATION_SIGNAL,
        "research",
        "medium",
        "Researcher moving technology toward a company.",
        "lab->startup transition / spinout language",
        180,
        ("founder",),
        is_inference=True,
    ),
    EventType.LP_ROLE_STARTED: _s(
        EventType.LP_ROLE_STARTED,
        "lp",
        "medium",
        "Person starts an allocator / LP-side role.",
        "employment at family_office / endowment / foundation / fund_of_funds",
        400,
        ("lp",),
    ),
    EventType.FAMILY_OFFICE_ROLE_STARTED: _s(
        EventType.FAMILY_OFFICE_ROLE_STARTED,
        "lp",
        "medium",
        "Role at a family office.",
        "employment record + org type",
        400,
        ("lp",),
    ),
    EventType.CIO_ROLE_STARTED: _s(
        EventType.CIO_ROLE_STARTED,
        "lp",
        "high",
        "Person becomes CIO / head of investments.",
        "title + org type",
        500,
        ("lp",),
    ),
    EventType.PARTNER_ROLE_STARTED: _s(
        EventType.PARTNER_ROLE_STARTED,
        "lp",
        "high",
        "Promotion / hire into Partner at an allocator or fund.",
        "title change",
        400,
        ("lp",),
    ),
    EventType.INVESTMENT_MANDATE_CHANGED: _s(
        EventType.INVESTMENT_MANDATE_CHANGED,
        "lp",
        "high",
        "Bio / mandate text adds venture or alternatives allocation responsibility.",
        "official bio diff / announcement",
        300,
        ("lp",),
    ),
    EventType.VENTURE_ALLOCATION_SIGNAL: _s(
        EventType.VENTURE_ALLOCATION_SIGNAL,
        "lp",
        "medium",
        "Evidence the organization allocates to VC / emerging managers.",
        "disclosed commitment / program page",
        365,
        ("lp",),
    ),
    EventType.FUND_INVESTMENT_ACTIVITY: _s(
        EventType.FUND_INVESTMENT_ACTIVITY,
        "lp",
        "medium",
        "Organization made a fund commitment.",
        "database / disclosure",
        365,
        ("lp",),
    ),
    EventType.EMERGING_MANAGER_SIGNAL: _s(
        EventType.EMERGING_MANAGER_SIGNAL,
        "lp",
        "medium",
        "Organization runs / joins an emerging-manager program.",
        "program page / announcement",
        365,
        ("lp",),
    ),
    EventType.INVESTMENT_COMMITTEE_ROLE: _s(
        EventType.INVESTMENT_COMMITTEE_ROLE,
        "lp",
        "medium",
        "Person joins an investment committee.",
        "announcement / bio",
        400,
        ("lp",),
    ),
    EventType.PROFESSIONAL_DEPARTURE: _s(
        EventType.PROFESSIONAL_DEPARTURE,
        "talent",
        "medium",
        "Person left a role (talent lens on EMPLOYMENT_ENDED).",
        "as EMPLOYMENT_ENDED",
        180,
        ("talent",),
    ),
    EventType.OPEN_TO_WORK_SIGNAL: _s(
        EventType.OPEN_TO_WORK_SIGNAL,
        "talent",
        "medium",
        "Person DECLARES availability.",
        "explicit profile flag / post",
        120,
        ("talent",),
        notes="Fact only if declared; never inferred from a departure (spec §64).",
    ),
    EventType.NEW_EXECUTIVE_ROLE: _s(
        EventType.NEW_EXECUTIVE_ROLE,
        "talent",
        "medium",
        "Person starts a C-level / VP role.",
        "employment record",
        365,
        ("talent",),
    ),
    EventType.FUNCTIONAL_LEADERSHIP_ROLE: _s(
        EventType.FUNCTIONAL_LEADERSHIP_ROLE,
        "talent",
        "low",
        "Person starts a function-head role.",
        "employment record",
        365,
        ("talent",),
    ),
    EventType.PORTFOLIO_ROLE_MATCH_CREATED: _s(
        EventType.PORTFOLIO_ROLE_MATCH_CREATED,
        "talent",
        "low",
        "System created a candidate<->role match above threshold.",
        "candidate_role_match row",
        90,
        ("talent",),
    ),
    EventType.NEW_CHIMERA_CONNECTION: _s(
        EventType.NEW_CHIMERA_CONNECTION,
        "network",
        "medium",
        "A new relationship_edge between a Chimera person and the subject.",
        "edge record",
        730,
        ("founder", "lp", "talent", "connector"),
    ),
    EventType.RELATIONSHIP_STRENGTH_UPDATED: _s(
        EventType.RELATIONSHIP_STRENGTH_UPDATED,
        "network",
        "low",
        "Edge strength label changed.",
        "two edge states",
        365,
        ("founder", "lp", "talent", "connector"),
    ),
    EventType.WARM_PATH_CREATED: _s(
        EventType.WARM_PATH_CREATED,
        "network",
        "medium",
        "A path Chimera->person appeared where none existed.",
        "path computation diff",
        180,
        ("founder", "lp", "talent", "connector"),
    ),
    EventType.WARM_PATH_LOST: _s(
        EventType.WARM_PATH_LOST,
        "network",
        "medium",
        "A previously-known path no longer exists.",
        "path computation diff",
        180,
        ("founder", "lp", "talent", "connector"),
    ),
    EventType.NEWS_MENTION: _s(
        EventType.NEWS_MENTION,
        "general",
        "low",
        "Person named in a news article.",
        "article observation + entity resolution >= POSSIBLE_MATCH",
        120,
        ("founder", "lp", "talent", "connector"),
    ),
    EventType.AWARD: _s(
        EventType.AWARD,
        "general",
        "low",
        "Named award / recognition.",
        "announcement",
        400,
        ("founder", "talent"),
    ),
    EventType.CONFERENCE_APPEARANCE: _s(
        EventType.CONFERENCE_APPEARANCE,
        "general",
        "low",
        "Speaker / panelist listing.",
        "agenda / announcement",
        120,
        ("connector",),
    ),
    EventType.PUBLIC_TALK: _s(
        EventType.PUBLIC_TALK,
        "general",
        "low",
        "Recorded talk / keynote.",
        "listing",
        180,
        ("connector",),
    ),
    EventType.MAJOR_COMPANY_MILESTONE: _s(
        EventType.MAJOR_COMPANY_MILESTONE,
        "general",
        "low",
        "Verified milestone at the person's company (scale / users / revenue).",
        "tier-1/2 figure only — never an estimate",
        240,
        ("founder",),
    ),
}

INFERENCE_TYPES: frozenset[str] = frozenset(
    et.value for et, spec in EVENT_TYPES.items() if spec.is_inference
)


def is_inference_type(event_type: str) -> bool:
    return event_type in INFERENCE_TYPES


def default_confidence(
    *,
    reliability_tier: int,
    directness: float = 1.0,
    extraction: float = 1.0,
    independence: float | None = None,
) -> float:
    """``confidence = R * D * X * I`` (docs/EVENT_TAXONOMY.md 'Common confidence inputs')."""
    r = TIER_WEIGHT.get(reliability_tier, 0.5)
    i = independence if independence is not None else 1.0
    return round(max(0.0, min(1.0, r * directness * extraction * i)), 2)


ALL_EVENT_TYPE_VALUES: frozenset[str] = frozenset(e.value for e in EventType)


def is_known_event_type(value: str) -> bool:
    return value in ALL_EVENT_TYPE_VALUES


def spec_for(value: str) -> EventTypeSpec | None:
    try:
        return EVENT_TYPES.get(EventType(value))
    except ValueError:
        return None


def ttl_days_for(value: str, default: int = 180) -> int:
    spec = spec_for(value)
    return spec.ttl_days if spec else default


def specs_for_model(model_target: str) -> list[EventTypeSpec]:
    return [s for s in EVENT_TYPES.values() if model_target in s.scoring_models]
