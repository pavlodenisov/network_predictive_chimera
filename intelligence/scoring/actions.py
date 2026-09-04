"""Deterministic, versioned action rules (spec §57). First match wins. No LLM.

Conditions operate on a scored person's public signals:
  priority, confidence, access, quality, fit, timing, model_target,
  has_role_match, has_warm_path, is_newly_discovered, data_stale
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from intelligence.config import get_settings

_OPS = {
    "priority_gte": lambda ctx, v: ctx.get("priority", 0) >= v,
    "priority_lt": lambda ctx, v: ctx.get("priority", 0) < v,
    "confidence_gte": lambda ctx, v: ctx.get("confidence", 0) >= v,
    "confidence_lt": lambda ctx, v: ctx.get("confidence", 0) < v,
    "access_gte": lambda ctx, v: (ctx.get("access") or 0) >= v,
    "access_lt": lambda ctx, v: (ctx.get("access") or 0) < v,
    "quality_gte": lambda ctx, v: (ctx.get("quality") or 0) >= v,
    "model_target": lambda ctx, v: ctx.get("model_target") == v,
    "has_role_match": lambda ctx, v: bool(ctx.get("has_role_match")) == bool(v),
    "has_warm_path": lambda ctx, v: bool(ctx.get("has_warm_path")) == bool(v),
    "is_newly_discovered": lambda ctx, v: bool(ctx.get("is_newly_discovered")) == bool(v),
    "data_stale": lambda ctx, v: bool(ctx.get("data_stale")) == bool(v),
    "always": lambda ctx, v: bool(v),
}


@dataclass(slots=True)
class ActionRuleSet:
    version: str
    rules: list[dict[str, Any]]


def load_action_rules(*, actions_dir: Path | None = None, name: str = "v0.1") -> ActionRuleSet:
    actions_dir = actions_dir or get_settings().actions_dir
    raw = yaml.safe_load((actions_dir / f"{name}.yaml").read_text())
    return ActionRuleSet(version=raw.get("version", name), rules=raw.get("rules", []))


def decide_action(rules: ActionRuleSet, ctx: dict[str, Any]) -> tuple[str, list[str]]:
    for rule in rules.rules:
        when = rule.get("when", {})
        if all(_OPS.get(k, lambda *_: False)(ctx, v) for k, v in when.items()):
            return rule.get("then", "UNKNOWN"), list(rule.get("reason_codes", []))
    return "UNKNOWN", []
