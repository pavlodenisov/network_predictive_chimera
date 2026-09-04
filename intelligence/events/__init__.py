"""Event taxonomy + detection. See ``docs/EVENT_TAXONOMY.md`` (spec of record)."""

from intelligence.events.taxonomy import (
    EVENT_TAXONOMY_VERSION,
    EVENT_TYPES,
    EventType,
    default_confidence,
    is_inference_type,
)

__all__ = [
    "EVENT_TAXONOMY_VERSION",
    "EVENT_TYPES",
    "EventType",
    "default_confidence",
    "is_inference_type",
]
