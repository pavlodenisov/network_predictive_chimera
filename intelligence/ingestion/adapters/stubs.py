"""Provider stubs (spec §48). Full class + config schema + a health_check that reports
``disabled`` with the reason. Enabling one = supply ``source.configuration`` + credentials
in the environment. NONE of these scrape (spec §5, §39).
"""

from __future__ import annotations

from intelligence.ingestion.adapters.base import DisabledAdapter
from intelligence.models.enums import SourceType


class LinkedInSnapshotSource(DisabledAdapter):
    """Authorized LinkedIn-derived snapshots / provider records ONLY — never automated
    scraping. Expects the same JSON shape as ``JSONSnapshotSource`` plus provider IDs.
    Configure ``source.configuration = {"provider": "<authorized vendor>", "dataset": "..."}``.
    """

    source_name = "linkedin_snapshot"
    source_type = SourceType.PROFESSIONAL_PROFILE
    reliability_tier = 3
    reason = (
        "LinkedInSnapshotSource is disabled: requires an authorized snapshot/provider feed. "
        "Unauthorized scraping is prohibited (spec §5, §39)."
    )


class CRMSource(DisabledAdapter):
    """Firm CRM export/API. Configure ``{"base_url": ..., "auth_env": "CHIMERA_CRM_TOKEN"}``.
    Supplies relationships, interaction history, and analyst feedback."""

    source_name = "crm"
    source_type = SourceType.CRM
    reliability_tier = 2
    reason = "CRMSource is disabled: no CRM credentials configured."


class CrunchbaseSource(DisabledAdapter):
    """Licensed Crunchbase API. Configure ``{"auth_env": "CRUNCHBASE_API_KEY"}``."""

    source_name = "crunchbase"
    source_type = SourceType.CRUNCHBASE
    reliability_tier = 2
    reason = "CrunchbaseSource is disabled: CRUNCHBASE_API_KEY not set."


class PitchBookSource(DisabledAdapter):
    """Licensed PitchBook API + permitted access. Configure ``{"auth_env": "PITCHBOOK_API_KEY"}``."""

    source_name = "pitchbook"
    source_type = SourceType.PITCHBOOK
    reliability_tier = 2
    reason = "PitchBookSource is disabled: PITCHBOOK_API_KEY not set / access not permitted."


class GitHubSource(DisabledAdapter):
    """Public GitHub API. Configure ``{"auth_env": "GITHUB_TOKEN", "orgs": [...]}``.
    Supplies repo / contribution activity for OSS features."""

    source_name = "github"
    source_type = SourceType.GITHUB
    reliability_tier = 2
    reason = "GitHubSource is disabled: GITHUB_TOKEN not set."


STUB_ADAPTERS: tuple[type[DisabledAdapter], ...] = (
    LinkedInSnapshotSource,
    CRMSource,
    CrunchbaseSource,
    PitchBookSource,
    GitHubSource,
)
