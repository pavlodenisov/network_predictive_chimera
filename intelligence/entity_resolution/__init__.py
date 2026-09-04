"""Conservative entity resolution (spec §9).

Automatic merge only above a very high threshold with no competing candidate. Ambiguous
matches go to analyst review. Two people are NEVER merged on name similarity alone. Every
merge is reversible.
"""

from intelligence.entity_resolution.merge import merge_persons, unmerge
from intelligence.entity_resolution.resolver import (
    AUTO_MERGE_THRESHOLD,
    POSSIBLE_THRESHOLD,
    ResolutionCandidate,
    ResolutionOutcome,
    normalize_name,
    resolve_person,
    resolve_subject,
)

__all__ = [
    "AUTO_MERGE_THRESHOLD",
    "POSSIBLE_THRESHOLD",
    "ResolutionCandidate",
    "ResolutionOutcome",
    "merge_persons",
    "normalize_name",
    "resolve_person",
    "resolve_subject",
    "unmerge",
]
