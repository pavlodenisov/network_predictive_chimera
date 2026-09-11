"""One-off import: run the real Kaggle "LinkedIn Influencers Data" CSV through the actual
pipeline (extraction -> facts/events -> features -> scoring -> ranking), to prove the
source-agnostic architecture on real text rather than synthetic fixtures.

Dataset: https://www.kaggle.com/datasets/shreyasajal/linkedin-influencers-data
Columns used: name, headline, location, about, content (a post's text), reactions,
comments, views. `time_spent` is a relative string ("1 day ago") with no absolute date in
the source, so post `occurred_at` is recorded as unknown — only `observed_at`/`ingested_at`
(import time) are known, which is itself a realistic data-quality case for this system
(spec §2.6: never invent a time you don't have).

Reliability: this is a third-party, publicly-redistributed dataset of posts these
"influencers" themselves published on LinkedIn — tier 4 (secondary reporting/aggregator),
not tier 3 self-reported, since we cannot verify it against the live profile.

Runs against whatever DATABASE_URL is currently configured. LOCAL BY DEFAULT — do not
point this at a shared/deployed database without deciding that deliberately (these are
real, named people).

Usage:
    python -m scripts.import_linkedin_kaggle --csv /path/to/influencers_data.csv \
        [--max-people 69] [--max-posts-per-person 5]
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import csv
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select

from intelligence.db import session_scope
from intelligence.events.detector import persist_extraction
from intelligence.extraction.rules import RuleBasedExtractor
from intelligence.extraction.runner import run_extraction
from intelligence.jobs.pipeline import run_weekly
from intelligence.models import Person, RawObservation, Source
from intelligence.models.enums import (
    ContentType,
    EntityResolutionStatus,
    MonitoringStatus,
    SourceType,
)
from intelligence.observability import configure_logging, get_logger, now_utc

SOURCE_PROVIDER = "linkedin_kaggle_influencers"
csv.field_size_limit(sys.maxsize)


def _engagement(row: dict) -> float:
    total = 0.0
    for key in ("reactions", "comments", "views", "votes"):
        with contextlib.suppress(ValueError):
            total += float(row.get(key) or 0)
    return total


def _clean_location(raw: str | None) -> str | None:
    """The source CSV stores `location` as a Python list literal stringified by the
    original scraper (e.g. "['Mercer', 'Island,', 'Washington,', 'United', 'States']") —
    parse it back into a normal "Mercer Island, Washington, United States" string rather
    than storing the literal repr as a fact value."""
    if not raw:
        return None
    if raw.startswith("[") and raw.endswith("]"):
        try:
            parts = ast.literal_eval(raw)
            if isinstance(parts, list):
                return " ".join(str(p) for p in parts).strip() or None
        except (ValueError, SyntaxError):
            pass
    return raw


def load_people(csv_path: str, max_people: int, max_posts: int) -> list[dict]:
    by_name: dict[str, dict] = {}
    order: list[str] = []
    with Path(csv_path).open(newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("name") or "").strip()
            if not name:
                continue
            if name not in by_name:
                if len(order) >= max_people:
                    continue
                by_name[name] = {
                    "name": name,
                    "headline": (row.get("headline") or "").strip() or None,
                    "location": _clean_location((row.get("location") or "").strip() or None),
                    "about": (row.get("about") or "").strip() or None,
                    "posts": [],
                }
                order.append(name)
            if name in by_name:
                content = (row.get("content") or "").strip()
                if content:
                    by_name[name]["posts"].append({"content": content, "score": _engagement(row)})
    for p in by_name.values():
        p["posts"].sort(key=lambda x: x["score"], reverse=True)
        p["posts"] = p["posts"][:max_posts]
    return [by_name[n] for n in order]


def get_or_create_source(session) -> Source:
    row = session.execute(
        select(Source).where(Source.provider == SOURCE_PROVIDER)
    ).scalar_one_or_none()
    if row is None:
        row = Source(
            source_type=SourceType.PROFESSIONAL_ACTIVITY,
            provider=SOURCE_PROVIDER,
            name="LinkedIn Influencers (Kaggle export)",
            enabled=False,  # not a live adapter; this is a one-off historical import
            reliability_tier=4,  # secondary/redistributed, unverified against the live profile
            configuration={"dataset": "shreyasajal/linkedin-influencers-data"},
        )
        session.add(row)
        session.flush()
    return row


def get_or_create_person(session, name: str) -> tuple[Person, bool]:
    existing = session.execute(
        select(Person).where(Person.canonical_name == name)
    ).scalar_one_or_none()
    if existing:
        return existing, False
    person = Person(
        canonical_name=name,
        monitoring_status=MonitoringStatus.ACTIVE_MONITORING,
        entity_resolution_status=EntityResolutionStatus.RESOLVED,
        entity_resolution_confidence=1.0,
        first_seen_at=now_utc(),
        last_observed_at=now_utc(),
    )
    session.add(person)
    session.flush()
    return person, True


def make_observation(
    session,
    source: Source,
    *,
    provider_record_id: str,
    subject: str,
    content_type: str,
    raw_json: dict | None,
    raw_text: str | None,
) -> RawObservation:
    existing = session.execute(
        select(RawObservation).where(
            RawObservation.source_id == source.id,
            RawObservation.provider_record_id == provider_record_id,
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    ts = now_utc()
    obs = RawObservation(
        source_id=source.id,
        provider_record_id=provider_record_id,
        subject_hint=subject,
        observed_at=ts,
        ingested_at=ts,
        occurred_at=None,  # genuinely unknown — the dataset has no absolute post date
        content_type=content_type,
        content_hash=provider_record_id,
        raw_json=raw_json,
        raw_text=raw_text,
        obs_metadata={"import": SOURCE_PROVIDER},
    )
    session.add(obs)
    session.flush()
    return obs


def import_all(csv_path: str, max_people: int, max_posts: int, as_of: date) -> dict:
    configure_logging()
    log = get_logger("chimera.import.linkedin_kaggle")
    people_rows = load_people(csv_path, max_people, max_posts)
    log.info("linkedin_kaggle.loaded", people=len(people_rows))

    extractor = RuleBasedExtractor()
    new_people = 0
    observations = 0
    facts = 0
    events = 0
    inferences = 0

    with session_scope() as session:
        source = get_or_create_source(session)
        for row in people_rows:
            person, created = get_or_create_person(session, row["name"])
            new_people += int(created)

            profile_obs = make_observation(
                session,
                source,
                provider_record_id=f"profile:{row['name']}",
                subject=row["name"],
                content_type=ContentType.PROFILE_SNAPSHOT,
                raw_json={
                    "profile": {
                        "headline": row["headline"],
                        "location": row["location"],
                    },
                    # not a recognized profile key (no scored feature maps to free bio
                    # text) — kept on the observation so it's visible as provenance on
                    # the Person screen rather than silently dropped.
                    "about": row["about"],
                },
                raw_text=None,
            )
            observations += 1
            result = run_extraction(session, extractor, profile_obs)
            det = persist_extraction(
                session,
                person_id=person.id,
                observation=profile_obs,
                output=result.output,
                source=source,
            )
            facts += len(det.facts)
            events += len(det.events)
            inferences += len(det.inferences)

            for i, post in enumerate(row["posts"]):
                post_obs = make_observation(
                    session,
                    source,
                    provider_record_id=f"post:{row['name']}:{i}",
                    subject=row["name"],
                    content_type=ContentType.ACTIVITY_POST,
                    raw_json={"engagement_score": post["score"]},
                    raw_text=post["content"][:4000],
                )
                observations += 1
                presult = run_extraction(session, extractor, post_obs)
                pdet = persist_extraction(
                    session,
                    person_id=person.id,
                    observation=post_obs,
                    output=presult.output,
                    source=source,
                )
                facts += len(pdet.facts)
                events += len(pdet.events)
                inferences += len(pdet.inferences)

        log.info(
            "linkedin_kaggle.ingested",
            people=len(people_rows),
            new_people=new_people,
            observations=observations,
            facts=facts,
            events=events,
            inferences=inferences,
        )

    # One real pipeline pass: builds features, scores founder/lp/connector for every
    # ACTIVE_MONITORING person (real + synthetic together — the whole point is that the
    # scoring/ranking layer does not know or care where a person came from), and ranks.
    with session_scope() as session:
        weekly = run_weekly(session, as_of=as_of, config_version="v0.1")

    return {
        "people": len(people_rows),
        "new_people": new_people,
        "observations": observations,
        "facts": facts,
        "events": events,
        "inferences": inferences,
        "weekly_run_id": str(weekly.run_id),
        "weekly_status": weekly.status,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="scripts.import_linkedin_kaggle")
    p.add_argument("--csv", required=True, help="path to influencers_data.csv")
    p.add_argument("--max-people", type=int, default=69)
    p.add_argument("--max-posts-per-person", type=int, default=5)
    p.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = p.parse_args(argv)

    summary = import_all(args.csv, args.max_people, args.max_posts_per_person, args.as_of)
    print("\n=== LinkedIn Kaggle import complete ===")
    for k, v in summary.items():
        print(f"{k:>16}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
