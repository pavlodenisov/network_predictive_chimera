"""Repeated-profile-snapshot change detection (spec §49-50).

A generic field diff plus materiality rules that emit the correct mix of factual
observations (directly observed) and labelled inferences (interpretation). The first two
of ``EMPLOYMENT_ENDED`` / ``HEADLINE_CHANGED`` are factual; ``POSSIBLE_COMPANY_FORMATION``
is an inference — stored differently (spec §49).
"""

from intelligence.snapshot.diff import (
    MATERIAL_PROFILE_FIELDS,
    ProfileDiff,
    diff_profile_snapshots,
    headline_is_material_change,
)

__all__ = [
    "MATERIAL_PROFILE_FIELDS",
    "ProfileDiff",
    "diff_profile_snapshots",
    "headline_is_material_change",
]
