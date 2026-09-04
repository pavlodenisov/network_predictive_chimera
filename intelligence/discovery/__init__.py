"""Rule-based discovery of new people (spec §24-25). Candidates are staged, never
auto-promoted to trusted entities."""

from intelligence.discovery.engine import process_discovery_observation, qualify_candidates
from intelligence.discovery.rules import (
    load_discovery_rules_from_configs,
    matches_rule,
    sync_discovery_rules,
)

__all__ = [
    "load_discovery_rules_from_configs",
    "matches_rule",
    "process_discovery_observation",
    "qualify_candidates",
    "sync_discovery_rules",
]
