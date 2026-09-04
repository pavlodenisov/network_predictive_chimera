"""Metric primitives (spec §33)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(slots=True)
class PRF:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 1.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def add(self, predicted: set[str], gold: set[str]) -> None:
        self.tp += len(predicted & gold)
        self.fp += len(predicted - gold)
        self.fn += len(gold - predicted)

    def as_dict(self) -> dict:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
        }


def precision_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    top = ranked_ids[:k]
    return sum(1 for i in top if i in relevant) / k if k else 0.0


def recall_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0
    return sum(1 for i in ranked_ids[:k] if i in relevant) / len(relevant)


def ndcg_at_k(ranked_ids: list[str], relevance: dict[str, float], k: int) -> float:
    def dcg(order: list[str]) -> float:
        return sum(
            (relevance.get(i, 0.0)) / math.log2(rank + 2) for rank, i in enumerate(order[:k])
        )

    ideal = sorted(relevance, key=lambda i: relevance[i], reverse=True)
    idcg = dcg(ideal)
    return dcg(ranked_ids) / idcg if idcg else 0.0


def spearman(order_a: list[str], order_b: list[str]) -> float:
    common = [i for i in order_a if i in set(order_b)]
    if len(common) < 2:
        return 0.0
    ra = {i: r for r, i in enumerate(order_a)}
    rb = {i: r for r, i in enumerate(order_b)}
    n = len(common)
    d2 = sum((ra[i] - rb[i]) ** 2 for i in common)
    return 1 - (6 * d2) / (n * (n**2 - 1))
