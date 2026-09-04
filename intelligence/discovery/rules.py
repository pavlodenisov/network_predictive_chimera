"""Load ``configs/discovery/*.yaml`` into ``discovery_rule`` and match observations."""

from __future__ import annotations

from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from intelligence.config import get_settings
from intelligence.models import DiscoveryRule


def load_discovery_rules_from_configs(directory: Path | None = None) -> list[dict]:
    directory = directory or get_settings().discovery_dir
    if not directory.exists():
        return []
    out = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text()) or {}
        raw["_source_file"] = path.name
        out.append(raw)
    return out


def sync_discovery_rules(session: Session, directory: Path | None = None) -> list[DiscoveryRule]:
    """Upsert config rules into the DB by ``name`` (idempotent)."""
    rows: list[DiscoveryRule] = []
    for raw in load_discovery_rules_from_configs(directory):
        name = raw.get("name")
        if not name:
            continue
        existing = session.execute(
            select(DiscoveryRule).where(DiscoveryRule.name == name)
        ).scalar_one_or_none()
        fields = {
            "active": bool(raw.get("active", True)),
            "target_class": raw.get("target_class", "UNKNOWN"),
            "industries": raw.get("industries", []),
            "technical_topics": raw.get("technical_topics", []),
            "titles": raw.get("titles", []),
            "prior_employers": raw.get("prior_employers", []),
            "geographies": raw.get("geographies", []),
            "keywords": raw.get("keywords", []),
            "excluded_keywords": raw.get("excluded_keywords", []),
            "source_ids": raw.get("source_ids", []),
            "lookback_days": int(raw.get("lookback_days", 120)),
            "minimum_evidence": raw.get("minimum_evidence", {}),
            "created_by": raw.get("created_by", "seed"),
        }
        if existing is None:
            rule = DiscoveryRule(name=name, **fields)
            session.add(rule)
        else:
            for k, v in fields.items():
                setattr(existing, k, v)
            rule = existing
        session.flush()
        rows.append(rule)
    return rows


def matches_rule(
    rule: DiscoveryRule, *, text: str, event_types: set[str]
) -> tuple[bool, list[str]]:
    """Deterministic match of an observation's text + detected events against a rule."""
    low = (text or "").lower()
    reasons: list[str] = []

    for bad in rule.excluded_keywords or []:
        if bad.lower() in low:
            return False, [f"excluded:{bad}"]

    kw_hits = [k for k in (rule.keywords or []) if k.lower() in low]
    topic_hits = [t for t in (rule.technical_topics or []) if t.lower() in low]
    title_hits = [t for t in (rule.titles or []) if t.lower() in low]

    me = rule.minimum_evidence or {}
    required_events = set(me.get("require_any_event_types", []))
    event_hit = bool(required_events & event_types) if required_events else True

    if kw_hits:
        reasons.append(f"keywords:{','.join(kw_hits[:4])}")
    if topic_hits:
        reasons.append(f"topics:{','.join(topic_hits[:4])}")
    if title_hits:
        reasons.append(f"titles:{','.join(title_hits[:3])}")
    if event_hit and required_events:
        reasons.append(f"events:{','.join(sorted(required_events & event_types))}")

    min_signals = int(me.get("min_signals", 1))
    signal_count = len(kw_hits) + len(topic_hits) + len(title_hits) + (1 if event_hit else 0)
    ok = event_hit and signal_count >= min_signals and bool(reasons)
    return ok, reasons
