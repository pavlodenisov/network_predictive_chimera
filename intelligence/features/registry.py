"""Feature-set version + the sensitive-attribute guard entry point (spec §39)."""

from __future__ import annotations

from intelligence.features.base import (
    FORBIDDEN_FEATURE_SUBSTRINGS,
    assert_feature_name_allowed,
)

FEATURE_SET_VERSION = "v0.1"

__all__ = ["FEATURE_SET_VERSION", "FORBIDDEN_FEATURE_SUBSTRINGS", "assert_feature_name_allowed"]
