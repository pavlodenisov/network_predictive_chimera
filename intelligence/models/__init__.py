"""ORM models. Importing this package registers every table on ``Base.metadata``.

See ``docs/DATA_MODEL.md`` for the field-level specification.
"""

from __future__ import annotations

from intelligence.db import Base
from intelligence.models.analyst import (
    AnalystFeedback,
    AnalystOverride,
    EntityMergeLog,
    EntityResolutionResult,
)
from intelligence.models.config_tables import ActionRuleSet, ThesisConfiguration
from intelligence.models.discovery import DiscoveryCandidate, DiscoveryRule
from intelligence.models.event import Event
from intelligence.models.industry_event import IndustryEvent
from intelligence.models.network import RelationshipEdge
from intelligence.models.org import Education, Employment, Organization
from intelligence.models.person import Person, PersonAlias, PersonClassification
from intelligence.models.provenance import (
    Evidence,
    Fact,
    Inference,
    RawObservation,
    Source,
    StoryCluster,
)
from intelligence.models.runs import ExtractionRun, WeeklyRun
from intelligence.models.scoring import (
    PersonFeatureSnapshot,
    RankingUniverse,
    ScoreSnapshot,
    ScoringModel,
)
from intelligence.models.talent import CandidateRoleMatch, PortfolioRoleNeed

__all__ = [
    "Base",
    "ActionRuleSet",
    "AnalystFeedback",
    "AnalystOverride",
    "CandidateRoleMatch",
    "DiscoveryCandidate",
    "DiscoveryRule",
    "Education",
    "EntityMergeLog",
    "EntityResolutionResult",
    "Event",
    "Employment",
    "Evidence",
    "ExtractionRun",
    "Fact",
    "Inference",
    "IndustryEvent",
    "Organization",
    "Person",
    "PersonAlias",
    "PersonClassification",
    "PersonFeatureSnapshot",
    "PortfolioRoleNeed",
    "RankingUniverse",
    "RawObservation",
    "RelationshipEdge",
    "ScoreSnapshot",
    "ScoringModel",
    "Source",
    "StoryCluster",
    "ThesisConfiguration",
    "WeeklyRun",
]
