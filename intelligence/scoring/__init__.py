"""Deterministic scoring (spec §2.4, §19-21). LLMs never produce a number here."""

from intelligence.scoring.config import (
    ModelConfig,
    config_hash,
    load_all_model_configs,
    load_model_config,
)
from intelligence.scoring.engine import ScoreResult, score_person

__all__ = [
    "ModelConfig",
    "ScoreResult",
    "config_hash",
    "load_all_model_configs",
    "load_model_config",
    "score_person",
]
