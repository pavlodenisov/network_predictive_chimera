"""``python -m intelligence.jobs.seed`` — load the synthetic week-1 baseline universe
(spec §34). Deterministic (fixed RNG seed + fixed dates). Idempotent: re-running does not
duplicate rows.

Produces >= 40 founders/potential-founders, 20 LPs, 25 talent profiles, 15 connectors,
plus organizations, employments, relationships (incl. Chimera seed nodes), 2x "Alex Lee"
for the entity-ambiguity scenario, stale + conflicting sources, unknown fields, and
week-1 baseline score snapshots (via one pass of the real weekly pipeline).
"""

from __future__ import annotations

import random
from datetime import UTC, date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from intelligence.db import session_scope
from intelligence.discovery.rules import sync_discovery_rules
from intelligence.facts import FactType, known, record_fact, unknown
from intelligence.jobs.pipeline import run_weekly
from intelligence.models import (
    Education,
    Employment,
    Fact,
    Organization,
    Person,
    PersonAlias,
    PersonClassification,
    PortfolioRoleNeed,
    RawObservation,
    RelationshipEdge,
    Source,
    ThesisConfiguration,
)
from intelligence.models.enums import (
    AliasType,
    ContentType,
    EntityResolutionStatus,
    Function,
    MonitoringStatus,
    OrganizationType,
    PersonClass,
    RelationshipStrength,
    RoleNeedStatus,
    Seniority,
    SourceType,
    SubjectType,
)
from intelligence.observability import configure_logging, get_logger, now_utc

WEEK1 = date(2026, 8, 24)
WEEK2 = date(2026, 9, 6)
RNG_SEED = 20260906

_SECTORS = [
    "artificial intelligence",
    "AI infrastructure",
    "developer tools",
    "robotics",
    "industrial technology",
    "fintech",
    "enterprise software",
]
_TOPICS = [
    "inference",
    "distributed systems",
    "GPU",
    "model serving",
    "training infrastructure",
    "robotics control",
    "sensor fusion",
    "payments",
    "data infrastructure",
    "security",
]
_FIRST = [
    "Ava",
    "Liam",
    "Noah",
    "Mia",
    "Ethan",
    "Zoe",
    "Kai",
    "Nina",
    "Omar",
    "Lena",
    "Ravi",
    "Sofia",
    "Théo",
    "Yuki",
    "Hana",
    "Diego",
    "Amara",
    "Ben",
    "Cleo",
    "Ian",
]
_LAST = [
    "Okafor",
    "Nguyen",
    "Silva",
    "Petrov",
    "Haddad",
    "Kim",
    "Rossi",
    "Mbeki",
    "Larsen",
    "Costa",
    "Ito",
    "Dubois",
    "Farah",
    "Reyes",
    "Bauer",
    "Novak",
    "Singh",
    "Weiss",
]
_CHIMERA = ["Rowan Ellis", "Devi Menon", "Grant Sato", "Bianca Ford"]


def _get_or_create_org(session: Session, name: str, **kw) -> Organization:
    row = session.execute(
        select(Organization).where(Organization.canonical_name == name)
    ).scalar_one_or_none()
    if row is None:
        row = Organization(canonical_name=name, **kw)
        session.add(row)
        session.flush()
    return row


def _get_or_create_person(session: Session, name: str, **kw) -> tuple[Person, bool]:
    row = (
        session.execute(
            select(Person).where(Person.canonical_name == name, Person.merged_into_id.is_(None))
        )
        .scalars()
        .first()
    )
    if row is not None:
        return row, False
    row = Person(canonical_name=name, first_seen_at=now_utc(), **kw)
    session.add(row)
    session.flush()
    return row, True


def _classify(session: Session, person: Person, *classes: str) -> None:
    for c in classes:
        exists = session.execute(
            select(PersonClassification).where(
                PersonClassification.person_id == person.id,
                PersonClassification.person_class == c,
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                PersonClassification(
                    person_id=person.id, person_class=c, source="seed", confidence=0.9
                )
            )
    session.flush()


def _baseline_source(session: Session) -> Source:
    row = session.execute(
        select(Source).where(Source.provider == "seed_baseline")
    ).scalar_one_or_none()
    if row is None:
        row = Source(
            source_type=SourceType.JSON_SNAPSHOT,
            provider="seed_baseline",
            name="Seed Baseline",
            enabled=False,  # not a live adapter
            reliability_tier=3,
        )
        session.add(row)
        session.flush()
    return row


def _baseline_obs(session: Session, src: Source, subject: str) -> RawObservation:
    row = session.execute(
        select(RawObservation).where(
            RawObservation.source_id == src.id,
            RawObservation.provider_record_id == f"baseline:{subject}",
        )
    ).scalar_one_or_none()
    if row is None:
        ts = datetime(WEEK1.year, WEEK1.month, WEEK1.day, tzinfo=UTC)
        row = RawObservation(
            source_id=src.id,
            provider_record_id=f"baseline:{subject}",
            subject_hint=subject,
            observed_at=ts,
            ingested_at=ts,
            occurred_at=ts,
            content_type=ContentType.PROFILE_SNAPSHOT,
            content_hash=f"baseline:{subject}",
            raw_json={"profile": {"note": "seed baseline"}},
            obs_metadata={"seed": True},
        )
        session.add(row)
        session.flush()
    return row


def _fact(session, src, obs, person, ft, value_dict):
    exists = session.scalar(
        select(func.count())
        .select_from(Fact)
        .where(Fact.subject_id == person.id, Fact.fact_type == ft)
    )
    if exists:
        return
    record_fact(
        session,
        subject_type=SubjectType.PERSON,
        subject_id=person.id,
        fact_type=ft,
        value=value_dict,
        observation=obs,
        source=src,
        source_label="Seed Baseline",
        extractor_version="seed",
        extraction_confidence=1.0,
        valid_from=datetime(WEEK1.year, WEEK1.month, WEEK1.day, tzinfo=UTC),
    )


def seed_all(session: Session) -> dict:
    rng = random.Random(RNG_SEED)
    configure_logging()
    log = get_logger("chimera.seed")

    if session.scalar(select(func.count()).select_from(ThesisConfiguration)) == 0:
        session.add(
            ThesisConfiguration(
                name="chimera-sample",
                version="v0.1",
                is_sample=True,
                active=True,
                sectors=_SECTORS,
                technologies=[
                    "inference optimization",
                    "distributed systems",
                    "training infrastructure",
                    "GPU computing",
                    "model serving",
                    "autonomy / perception",
                ],
                technical_topics=_TOPICS,
                business_models=[
                    "usage-based infrastructure",
                    "open-core",
                    "enterprise SaaS",
                    "API platform",
                ],
                stages=["pre-seed", "seed", "series A"],
                geographies=["United States", "Canada", "United Kingdom", "European Union"],
                notes="SAMPLE thesis — replace with the firm's actual thesis.",
            )
        )
        session.flush()

    _ensure_live_sources(session)
    sync_discovery_rules(session)
    src = _baseline_source(session)

    # ---- Chimera team (seed nodes) ---------------------------------------
    chimera_people: list[Person] = []
    for name in _CHIMERA:
        p, _ = _get_or_create_person(
            session,
            name,
            is_chimera_seed=True,
            monitoring_status=MonitoringStatus.ACTIVE_MONITORING,
            entity_resolution_status=EntityResolutionStatus.RESOLVED,
            entity_resolution_confidence=1.0,
        )
        _classify(session, p, PersonClass.INVESTOR)
        chimera_people.append(p)

    orgs = _seed_orgs(session, rng)
    _seed_portfolio(session)

    counts = {"founder": 0, "lp": 0, "talent": 0, "connector": 0}
    people: list[Person] = []

    people += _seed_founders(session, src, rng, orgs, n=42, counts=counts)
    people += _seed_lps(session, src, rng, orgs, n=20, counts=counts)
    people += _seed_talent(session, src, rng, orgs, n=25, counts=counts)
    people += _seed_connectors(session, src, rng, orgs, n=15, counts=counts)
    people += _seed_heroes(session, src, rng)

    _seed_relationships(session, rng, chimera_people, people)
    session.flush()

    # ---- week-1 baseline scoring via the real pipeline --------------------
    result = run_weekly(session, as_of=WEEK1, config_version="v0.1")
    log.info(
        "seed.done",
        people=len(people) + len(chimera_people),
        founders=counts["founder"],
        lps=counts["lp"],
        talent=counts["talent"],
        connectors=counts["connector"],
        baseline_run=str(result.run_id),
    )
    return {
        "people": len(people) + len(chimera_people),
        "counts": counts,
        "baseline_run": str(result.run_id),
    }


def _ensure_live_sources(session: Session) -> None:
    wanted = [
        ("synthetic", SourceType.SYNTHETIC, 2, True),
        ("json_snapshot", SourceType.JSON_SNAPSHOT, 3, True),
        ("manual_csv", SourceType.MANUAL_CSV, 3, True),
        ("rss_news", SourceType.RSS, 4, True),
        ("linkedin_snapshot", SourceType.PROFESSIONAL_PROFILE, 3, False),
        ("crm", SourceType.CRM, 2, False),
        ("crunchbase", SourceType.CRUNCHBASE, 2, False),
        ("pitchbook", SourceType.PITCHBOOK, 2, False),
        ("github", SourceType.GITHUB, 2, False),
    ]
    for provider, stype, tier, enabled in wanted:
        exists = session.execute(
            select(Source).where(Source.provider == provider)
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                Source(
                    source_type=stype,
                    provider=provider,
                    name=provider.replace("_", " ").title(),
                    enabled=enabled,
                    reliability_tier=tier,
                )
            )
    session.flush()


def _seed_orgs(session: Session, rng: random.Random) -> list[Organization]:
    orgs: list[Organization] = []
    for i in range(28):
        sector = _SECTORS[i % len(_SECTORS)]
        o = _get_or_create_org(
            session,
            f"{rng.choice(['Helix', 'Vector', 'Quanta', 'Nimbus', 'Aperture', 'Forge', 'Lumen', 'Cirrus'])} {['Labs', 'AI', 'Systems', 'Compute', 'Robotics', 'Data', 'Cloud'][i % 7]} {i}",
            organization_type=OrganizationType.STARTUP,
            attributes={
                "sector": sector,
                "sectors": [sector],
                "stage": rng.choice(["seed", "series A", "series B"]),
            },
        )
        orgs.append(o)
    for name in [
        "Integral Family Office",
        "Northwind Endowment",
        "Cedar Foundation",
        "Atlas Fund of Funds",
        "Blue Harbor Family Office",
        "Summit Endowment",
    ]:
        orgs.append(
            _get_or_create_org(
                session,
                name,
                organization_type=OrganizationType.FAMILY_OFFICE
                if "Family Office" in name
                else (
                    OrganizationType.ENDOWMENT
                    if "Endowment" in name
                    else OrganizationType.FOUNDATION
                ),
                location="United States",
                aum_usd=rng.choice([2_000_000_000, 6_500_000_000, 12_000_000_000, None]),
            )
        )
    for uni in ["State Polytechnic", "Riverside University", "Cardinal Institute of Technology"]:
        orgs.append(_get_or_create_org(session, uni, organization_type=OrganizationType.UNIVERSITY))
    return orgs


def _seed_portfolio(session: Session) -> list[Organization]:
    roles = [
        (
            "Northstar Robotics",
            "Head of AI",
            Function.RESEARCH,
            Seniority.C_LEVEL,
            ["robotics control", "perception"],
            ["series A", "series B"],
        ),
        (
            "Ledger Rails",
            "VP Engineering",
            Function.ENGINEERING,
            Seniority.VP,
            ["payments", "distributed systems"],
            ["series B"],
        ),
        (
            "Cobalt Analytics",
            "Head of Product",
            Function.PRODUCT,
            Seniority.DIRECTOR,
            ["data infrastructure"],
            ["seed", "series A"],
        ),
    ]
    out: list[Organization] = []
    for org_name, title, func_, sen, domain, stage in roles:
        o = _get_or_create_org(
            session,
            org_name,
            organization_type=OrganizationType.PORTFOLIO_COMPANY,
            is_portfolio=True,
            location="United States",
            attributes={
                "sector": "enterprise software",
                "sectors": ["enterprise software"],
                "stage": stage[-1],
            },
        )
        out.append(o)
        exists = session.execute(
            select(PortfolioRoleNeed).where(
                PortfolioRoleNeed.portfolio_company_id == o.id,
                PortfolioRoleNeed.role_title == title,
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                PortfolioRoleNeed(
                    portfolio_company_id=o.id,
                    role_title=title,
                    function=func_,
                    seniority=sen,
                    domain_requirements=domain,
                    stage_requirements=stage,
                    location_requirements={"country": "united states", "remote_ok": True},
                    status=RoleNeedStatus.OPEN,
                )
            )
    session.flush()
    return out


def _person_name(rng: random.Random, used: set[str]) -> str:
    for _ in range(50):
        name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)}"
        if name not in used:
            used.add(name)
            return name
    name = f"{rng.choice(_FIRST)} {rng.choice(_LAST)} {len(used)}"
    used.add(name)
    return name


_USED_NAMES: set[str] = set()


def _seed_founders(session, src, rng, orgs, *, n, counts) -> list[Person]:
    out = []
    startups = [o for o in orgs if o.organization_type == OrganizationType.STARTUP]
    for i in range(n):
        name = _person_name(rng, _USED_NAMES)
        p, _ = _get_or_create_person(
            session,
            name,
            primary_linkedin_url=f"linkedin.com/in/{name.lower().replace(' ', '-')}",
            monitoring_status=MonitoringStatus.ACTIVE_MONITORING,
            entity_resolution_status=EntityResolutionStatus.RESOLVED,
            entity_resolution_confidence=round(rng.uniform(0.8, 1.0), 2),
            primary_location=rng.choice(
                ["San Francisco, CA", "New York, NY", "London, UK", "Berlin, DE", "Toronto, CA"]
            ),
        )
        _classify(
            session,
            p,
            PersonClass.POTENTIAL_FOUNDER if i % 3 else PersonClass.FOUNDER,
            PersonClass.ENGINEER,
        )
        org = rng.choice(startups)
        session.add(
            Employment(
                person_id=p.id,
                organization_id=org.id,
                title=rng.choice(
                    [
                        "Staff Engineer",
                        "Principal Engineer",
                        "Founding Engineer",
                        "Head of ML",
                        "Research Lead",
                    ]
                ),
                seniority=rng.choice([Seniority.SENIOR_IC, Seniority.MANAGER, Seniority.DIRECTOR]),
                function=Function.ENGINEERING,
                current=True,
                started_at=date(2021 + i % 4, 1 + i % 12, 1),
            )
        )
        obs = _baseline_obs(session, src, name)
        topic = rng.choice(_TOPICS)
        _fact(
            session,
            src,
            obs,
            p,
            FactType.HEADLINE_TEXT,
            known(f"{org.attributes.get('sector')} — {topic}"),
        )
        _fact(
            session,
            src,
            obs,
            p,
            FactType.YEARS_DOMAIN_EXPERIENCE,
            known(round(rng.uniform(2, 12), 1), "years"),
        )
        _fact(
            session,
            src,
            obs,
            p,
            FactType.YEARS_ENGINEERING_EXPERIENCE,
            known(round(rng.uniform(4, 16), 1), "years"),
        )
        if rng.random() < 0.35:
            _fact(session, src, obs, p, FactType.PRIOR_EXIT, known(True))
        if rng.random() < 0.5:
            _fact(session, src, obs, p, FactType.PRIOR_FOUNDER, known(True))
            _fact(
                session,
                src,
                obs,
                p,
                FactType.COMPANIES_FOUNDED_COUNT,
                known(rng.randint(1, 2), "count"),
            )
        if rng.random() < 0.6:
            _fact(session, src, obs, p, FactType.PRODUCT_SHIPPED, known(True))
        if rng.random() < 0.3:
            _fact(session, src, obs, p, FactType.PATENT_COUNT, known(rng.randint(1, 12), "count"))
        _fact(session, src, obs, p, FactType.PROMOTION_COUNT, known(rng.randint(0, 4), "count"))
        _fact(session, src, obs, p, FactType.FUNDRAISING_STATUS, unknown())
        counts["founder"] += 1
        out.append(p)
    return out


def _seed_lps(session, src, rng, orgs, *, n, counts) -> list[Person]:
    out = []
    allocators = [
        o
        for o in orgs
        if o.organization_type
        in (OrganizationType.FAMILY_OFFICE, OrganizationType.ENDOWMENT, OrganizationType.FOUNDATION)
    ]
    for i in range(n):
        name = _person_name(rng, _USED_NAMES)
        p, _ = _get_or_create_person(
            session,
            name,
            primary_linkedin_url=f"linkedin.com/in/{name.lower().replace(' ', '-')}",
            monitoring_status=MonitoringStatus.ACTIVE_MONITORING,
            entity_resolution_status=EntityResolutionStatus.RESOLVED,
            entity_resolution_confidence=0.95,
            primary_location="United States",
        )
        _classify(
            session, p, PersonClass.LP if i % 3 else PersonClass.POTENTIAL_LP, PersonClass.INVESTOR
        )
        org = rng.choice(allocators)
        title = rng.choice(
            ["CIO", "Partner", "Head of Alternatives", "Investment Director", "Principal"]
        )
        session.add(
            Employment(
                person_id=p.id,
                organization_id=org.id,
                title=title,
                seniority=Seniority.C_LEVEL if title == "CIO" else Seniority.PARTNER,
                function=Function.INVESTING,
                current=True,
                started_at=date(2020 + i % 5, 3, 1),
            )
        )
        obs = _baseline_obs(session, src, name)
        _fact(session, src, obs, p, FactType.CURRENT_TITLE, known(title))
        _fact(
            session,
            src,
            obs,
            p,
            FactType.DECISION_AUTHORITY_ROLE,
            known(title.lower().replace("head of ", "").strip()),
        )
        if rng.random() < 0.5:
            _fact(session, src, obs, p, FactType.VENTURE_ALLOCATION_EVIDENCE, known(True))
        if rng.random() < 0.3:
            _fact(
                session,
                src,
                obs,
                p,
                FactType.EMERGING_MANAGER_EVIDENCE,
                known(rng.randint(1, 4), "count"),
            )
        counts["lp"] += 1
        out.append(p)
    return out


def _seed_talent(session, src, rng, orgs, *, n, counts) -> list[Person]:
    out = []
    companies = [o for o in orgs if o.organization_type == OrganizationType.STARTUP]
    for i in range(n):
        name = _person_name(rng, _USED_NAMES)
        p, _ = _get_or_create_person(
            session,
            name,
            primary_linkedin_url=f"linkedin.com/in/{name.lower().replace(' ', '-')}",
            monitoring_status=MonitoringStatus.ACTIVE_MONITORING,
            entity_resolution_status=EntityResolutionStatus.RESOLVED,
            entity_resolution_confidence=0.9,
            primary_location=rng.choice(
                ["San Francisco, CA", "Austin, TX", "Remote", "New York, NY"]
            ),
        )
        _classify(session, p, PersonClass.TALENT, PersonClass.OPERATOR)
        org = rng.choice(companies)
        session.add(
            Employment(
                person_id=p.id,
                organization_id=org.id,
                title=rng.choice(
                    [
                        "VP Engineering",
                        "Head of Product",
                        "Director of Engineering",
                        "Staff Engineer",
                    ]
                ),
                seniority=rng.choice([Seniority.VP, Seniority.DIRECTOR, Seniority.SENIOR_IC]),
                function=rng.choice([Function.ENGINEERING, Function.PRODUCT]),
                current=True,
                started_at=date(2019 + i % 6, 6, 1),
            )
        )
        obs = _baseline_obs(session, src, name)
        _fact(session, src, obs, p, FactType.HEADLINE_TEXT, known(rng.choice(_TOPICS)))
        _fact(session, src, obs, p, FactType.PROMOTION_COUNT, known(rng.randint(0, 3), "count"))
        if rng.random() < 0.5:
            _fact(
                session,
                src,
                obs,
                p,
                FactType.TEAM_SIZE_MANAGED,
                known(rng.randint(3, 60), "people"),
            )
        if rng.random() < 0.4:
            _fact(session, src, obs, p, FactType.BUDGET_OWNERSHIP, known(True))
        counts["talent"] += 1
        out.append(p)
    return out


def _seed_connectors(session, src, rng, orgs, *, n, counts) -> list[Person]:
    out = []
    for _ in range(n):
        name = _person_name(rng, _USED_NAMES)
        p, _ = _get_or_create_person(
            session,
            name,
            primary_linkedin_url=f"linkedin.com/in/{name.lower().replace(' ', '-')}",
            monitoring_status=MonitoringStatus.PASSIVE_MONITORING,
            entity_resolution_status=EntityResolutionStatus.RESOLVED,
            entity_resolution_confidence=0.9,
        )
        _classify(session, p, PersonClass.CONNECTOR, PersonClass.OPERATOR)
        counts["connector"] += 1
        out.append(p)
    return out


def _seed_heroes(session: Session, src: Source, rng: random.Random) -> list[Person]:
    out: list[Person] = []

    # -- Sarah Chen: founder acceptance scenario (§62) --
    sarah, _ = _get_or_create_person(
        session,
        "Sarah Chen",
        primary_linkedin_url="linkedin.com/in/sarah-chen-ml",
        monitoring_status=MonitoringStatus.ACTIVE_MONITORING,
        entity_resolution_status=EntityResolutionStatus.RESOLVED,
        entity_resolution_confidence=0.97,
        primary_location="San Francisco, CA",
        current_title="Staff ML Engineer",
    )
    _classify(session, sarah, PersonClass.POTENTIAL_FOUNDER, PersonClass.ENGINEER)
    lab = _get_or_create_org(
        session,
        "Synthetic AI Labs",
        organization_type=OrganizationType.STARTUP,
        attributes={
            "sector": "AI infrastructure",
            "sectors": ["AI infrastructure"],
            "stage": "series B",
        },
    )
    if not session.scalar(
        select(func.count()).select_from(Employment).where(Employment.person_id == sarah.id)
    ):
        session.add(
            Employment(
                person_id=sarah.id,
                organization_id=lab.id,
                title="Staff ML Engineer",
                seniority=Seniority.SENIOR_IC,
                function=Function.ENGINEERING,
                current=True,
                started_at=date(2021, 3, 1),
            )
        )
        sarah.current_organization_id = lab.id
    obs = _baseline_obs(session, src, "Sarah Chen")
    _fact(
        session,
        src,
        obs,
        sarah,
        FactType.HEADLINE_TEXT,
        known("Staff ML Engineer at Synthetic AI Labs — inference infrastructure"),
    )
    _fact(session, src, obs, sarah, FactType.CURRENT_TITLE, known("Staff ML Engineer"))
    _fact(session, src, obs, sarah, FactType.YEARS_DOMAIN_EXPERIENCE, known(5.4, "years"))
    _fact(session, src, obs, sarah, FactType.YEARS_ENGINEERING_EXPERIENCE, known(8.0, "years"))
    _fact(session, src, obs, sarah, FactType.PRIOR_FOUNDER, known(True))
    _fact(session, src, obs, sarah, FactType.COMPANIES_FOUNDED_COUNT, known(1, "count"))
    _fact(session, src, obs, sarah, FactType.PRODUCT_SHIPPED, known(True))
    _fact(session, src, obs, sarah, FactType.EARLY_EMPLOYEE_RANK, known(11, "rank"))
    _fact(session, src, obs, sarah, FactType.PROMOTION_COUNT, known(2, "count"))
    _fact(session, src, obs, sarah, FactType.FUNDRAISING_STATUS, unknown())
    session.add(
        Education(
            person_id=sarah.id,
            institution_name_raw="Cardinal Institute of Technology",
            degree="MS",
            field="Computer Science",
            evidence_ids=[],
        )
    )
    out.append(sarah)

    # -- Marcus Webb: LP acceptance scenario (§63) --
    marcus, _ = _get_or_create_person(
        session,
        "Marcus Webb",
        primary_linkedin_url="linkedin.com/in/marcus-webb-invest",
        monitoring_status=MonitoringStatus.ACTIVE_MONITORING,
        entity_resolution_status=EntityResolutionStatus.RESOLVED,
        entity_resolution_confidence=0.95,
        primary_location="New York, NY",
        current_title="Principal",
    )
    _classify(session, marcus, PersonClass.POTENTIAL_LP, PersonClass.INVESTOR)
    integral = _get_or_create_org(
        session,
        "Integral Family Office",
        organization_type=OrganizationType.FAMILY_OFFICE,
        location="New York, NY",
        aum_usd=4_500_000_000,
    )
    if not session.scalar(
        select(func.count()).select_from(Employment).where(Employment.person_id == marcus.id)
    ):
        session.add(
            Employment(
                person_id=marcus.id,
                organization_id=integral.id,
                title="Principal",
                seniority=Seniority.SENIOR_IC,
                function=Function.INVESTING,
                current=True,
                started_at=date(2022, 5, 1),
            )
        )
        marcus.current_organization_id = integral.id
    obs = _baseline_obs(session, src, "Marcus Webb")
    _fact(
        session,
        src,
        obs,
        marcus,
        FactType.HEADLINE_TEXT,
        known("Principal at Integral Family Office"),
    )
    _fact(session, src, obs, marcus, FactType.CURRENT_TITLE, known("Principal"))
    _fact(session, src, obs, marcus, FactType.DECISION_AUTHORITY_ROLE, known("principal"))
    out.append(marcus)

    # -- Priya Nair: talent acceptance scenario (§64) --
    priya, _ = _get_or_create_person(
        session,
        "Priya Nair",
        primary_linkedin_url="linkedin.com/in/priya-nair-eng",
        monitoring_status=MonitoringStatus.ACTIVE_MONITORING,
        entity_resolution_status=EntityResolutionStatus.RESOLVED,
        entity_resolution_confidence=0.94,
        primary_location="Austin, TX",
        current_title="VP Engineering",
    )
    _classify(session, priya, PersonClass.TALENT, PersonClass.OPERATOR)
    meridian = _get_or_create_org(
        session,
        "Meridian Payments",
        organization_type=OrganizationType.STARTUP,
        attributes={"sector": "fintech", "sectors": ["fintech"], "stage": "series B"},
    )
    if not session.scalar(
        select(func.count()).select_from(Employment).where(Employment.person_id == priya.id)
    ):
        session.add(
            Employment(
                person_id=priya.id,
                organization_id=meridian.id,
                title="VP Engineering",
                seniority=Seniority.VP,
                function=Function.ENGINEERING,
                current=True,
                started_at=date(2020, 9, 1),
            )
        )
        priya.current_organization_id = meridian.id
    obs = _baseline_obs(session, src, "Priya Nair")
    _fact(
        session,
        src,
        obs,
        priya,
        FactType.HEADLINE_TEXT,
        known("VP Engineering — payments, distributed systems"),
    )
    _fact(session, src, obs, priya, FactType.CURRENT_TITLE, known("VP Engineering"))
    _fact(session, src, obs, priya, FactType.TEAM_SIZE_MANAGED, known(45, "people"))
    _fact(session, src, obs, priya, FactType.PROMOTION_COUNT, known(2, "count"))
    _fact(session, src, obs, priya, FactType.BUDGET_OWNERSHIP, known(True))
    out.append(priya)

    # -- two "Alex Lee" for the entity-ambiguity scenario (§65) --
    stripe = _get_or_create_org(
        session, "Stripe", organization_type=OrganizationType.PRIVATE_COMPANY
    )
    google = _get_or_create_org(
        session, "Google", organization_type=OrganizationType.PUBLIC_COMPANY
    )
    for tag, org in (("stripe", stripe), ("google", google)):
        al, created = _get_or_create_person(
            session,
            "Alex Lee",
            primary_linkedin_url=f"linkedin.com/in/alex-lee-{tag}",
            monitoring_status=MonitoringStatus.ACTIVE_MONITORING,
            entity_resolution_status=EntityResolutionStatus.RESOLVED,
            entity_resolution_confidence=0.85,
        )
        # _get_or_create matches by name, so the 2nd call returns the 1st — force a distinct row
        if (
            not created
            and not session.scalar(
                select(func.count())
                .select_from(Employment)
                .where(Employment.person_id == al.id, Employment.organization_id == org.id)
            )
            and org is google
        ):
            al = Person(
                canonical_name="Alex Lee",
                primary_linkedin_url="linkedin.com/in/alex-lee-google",
                monitoring_status=MonitoringStatus.ACTIVE_MONITORING,
                entity_resolution_status=EntityResolutionStatus.RESOLVED,
                entity_resolution_confidence=0.85,
                first_seen_at=now_utc(),
            )
            session.add(al)
            session.flush()
        session.add(
            PersonAlias(
                person_id=al.id,
                alias_type=AliasType.LINKEDIN_URL,
                alias_value=f"linkedin.com/in/alex-lee-{tag}",
                confidence=1.0,
            )
        )
        if not session.scalar(
            select(func.count())
            .select_from(Employment)
            .where(Employment.person_id == al.id, Employment.organization_id == org.id)
        ):
            session.add(
                Employment(
                    person_id=al.id,
                    organization_id=org.id,
                    title="Engineer",
                    seniority=Seniority.SENIOR_IC,
                    function=Function.ENGINEERING,
                    current=True,
                    started_at=date(2020, 1, 1),
                )
            )
        _classify(session, al, PersonClass.ENGINEER)
        out.append(al)

    session.flush()
    return out


def _seed_relationships(session, rng, chimera_people, people) -> None:
    def has_edge(a, b) -> bool:
        return bool(
            session.scalar(
                select(func.count())
                .select_from(RelationshipEdge)
                .where(
                    RelationshipEdge.source_person_id == a.id,
                    RelationshipEdge.target_person_id == b.id,
                )
            )
        )

    strengths = [
        RelationshipStrength.WEAK,
        RelationshipStrength.MODERATE,
        RelationshipStrength.STRONG,
    ]
    for cp in chimera_people:
        targets = rng.sample(people, k=min(len(people), rng.randint(8, 14)))
        for t in targets:
            if has_edge(cp, t):
                continue
            s = rng.choice(strengths)
            session.add(
                RelationshipEdge(
                    source_person_id=cp.id,
                    target_person_id=t.id,
                    relationship_type="colleague",
                    relationship_strength=s,
                    confidence=round(rng.uniform(0.6, 0.95), 2),
                    source="seed",
                    first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
                    last_verified_at=datetime(
                        2026, rng.randint(1, 8), rng.randint(1, 28), tzinfo=UTC
                    ),
                    evidence_ids=[],
                )
            )
    # connectors bridge to many
    connectors = [p for p in people if _has_class(session, p, PersonClass.CONNECTOR)]
    for c in connectors:
        for t in rng.sample(people, k=min(len(people), rng.randint(10, 20))):
            if t.id != c.id and not has_edge(c, t):
                session.add(
                    RelationshipEdge(
                        source_person_id=c.id,
                        target_person_id=t.id,
                        relationship_type="colleague",
                        relationship_strength=rng.choice(strengths),
                        confidence=round(rng.uniform(0.5, 0.9), 2),
                        source="seed",
                        first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
                        last_verified_at=datetime(2026, rng.randint(1, 8), 15, tzinfo=UTC),
                        evidence_ids=[],
                    )
                )
    # ensure Sarah has a MODERATE Chimera relationship (acceptance §62)
    sarah = (
        session.execute(select(Person).where(Person.canonical_name == "Sarah Chen"))
        .scalars()
        .first()
    )
    if sarah and not has_edge(chimera_people[0], sarah):
        session.add(
            RelationshipEdge(
                source_person_id=chimera_people[0].id,
                target_person_id=sarah.id,
                relationship_type="colleague",
                relationship_strength=RelationshipStrength.MODERATE,
                confidence=0.85,
                source="seed",
                first_seen_at=datetime(2026, 1, 1, tzinfo=UTC),
                last_verified_at=datetime(2026, 6, 1, tzinfo=UTC),
                evidence_ids=[],
            )
        )
    session.flush()


def _has_class(session, person, cls) -> bool:
    return bool(
        session.scalar(
            select(func.count())
            .select_from(PersonClassification)
            .where(
                PersonClassification.person_id == person.id,
                PersonClassification.person_class == cls,
            )
        )
    )


def main() -> int:
    with session_scope() as session:
        existing = int(session.scalar(select(func.count()).select_from(Person)) or 0)
        if existing > 5:
            print("universe already seeded — run `make reset` to rebuild")
            return 0
        summary = seed_all(session)
    print(f"seeded {summary['people']} people  {summary['counts']}")
    print(f"week-1 baseline run: {summary['baseline_run']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
