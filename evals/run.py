"""``python -m evals.run [extraction|entity_resolution|ranking|all] [--check]``

Writes ``artifacts/evals/<name>_<ts>.json`` and prints a summary table. ``--check``
compares to ``artifacts/evals/baseline.json`` and flags F1 drops > 0.05 on any category
and any increase in the entity-resolution false-merge rate (spec §33, §35).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from evals.metrics import PRF, ndcg_at_k, precision_at_k, recall_at_k, spearman

_ROOT = Path(__file__).resolve().parent
_GOLDEN = _ROOT / "golden"
_ARTIFACTS = _ROOT.parent / "artifacts" / "evals"

_EVENT_CATEGORY = {
    "EMPLOYMENT_ENDED": "employment_changes",
    "EMPLOYMENT_STARTED": "employment_changes",
    "TITLE_CHANGED": "employment_changes",
    "PROMOTION": "employment_changes",
    "HEADLINE_CHANGED": "employment_changes",
    "FOUNDER_TITLE_ADDED": "founder_signals",
    "STEALTH_COMPANY_SIGNAL": "founder_signals",
    "POSSIBLE_COMPANY_FORMATION": "founder_signals",
    "COMPANY_FORMATION_CONFIRMED": "founder_signals",
    "FUNDRAISE_ANNOUNCED": "fundraising_events",
    "FUNDING_ROUND_CONFIRMED": "fundraising_events",
    "COMPANY_ACQUIRED": "fundraising_events",
    "PARTNER_ROLE_STARTED": "lp_events",
    "CIO_ROLE_STARTED": "lp_events",
    "INVESTMENT_MANDATE_CHANGED": "lp_events",
    "LP_ROLE_STARTED": "lp_events",
    "PROFESSIONAL_DEPARTURE": "talent_events",
    "OPEN_TO_WORK_SIGNAL": "talent_events",
    "NEW_EXECUTIVE_ROLE": "talent_events",
    "NEWS_MENTION": "entities",
}


def _cat(event_type: str) -> str:
    return _EVENT_CATEGORY.get(event_type, "other")


# --------------------------------------------------------------------------- extraction
def eval_extraction() -> dict:
    from intelligence.extraction import RuleBasedExtractor
    from intelligence.extraction.base import ExtractionRequest
    from intelligence.snapshot.diff import diff_profile_snapshots

    ex = RuleBasedExtractor()
    per_cat: dict[str, PRF] = {}

    def bucket(name: str) -> PRF:
        return per_cat.setdefault(name, PRF())

    for path in sorted((_GOLDEN / "profiles").glob("*.json")):
        for case in json.loads(path.read_text()):
            out = diff_profile_snapshots(
                case["previous_snapshot"],
                case["snapshot"],
                occurred_on=None,
            )
            pred_events = {str(e.event_type) for e in out.events if not e.is_inference}
            pred_inf = {str(e.event_type) for e in out.events if e.is_inference}
            for cat in {_cat(e) for e in case["expected_events"]} | {_cat(e) for e in pred_events}:
                bucket(cat).add(
                    {e for e in pred_events if _cat(e) == cat},
                    {e for e in case["expected_events"] if _cat(e) == cat},
                )
            bucket("founder_signals").add(pred_inf, set(case.get("expected_inferences", [])))

    for path in sorted((_GOLDEN / "articles").glob("*.json")):
        for case in json.loads(path.read_text()):
            req = ExtractionRequest(
                observation_id="eval",
                content_type="news_article",
                raw_text=case["text"],
                raw_json={"title": "", "summary": case["text"]},
                subject_hint=case["subject"],
            )
            res = ex.extract(req)
            pred = {str(e.event_type) for e in res.output.events}
            gold = set(case["expected_events"]) | set(case.get("expected_inferences", []))
            for cat in {_cat(e) for e in gold} | {_cat(e) for e in pred}:
                bucket(cat).add(
                    {e for e in pred if _cat(e) == cat}, {e for e in gold if _cat(e) == cat}
                )
            pred_ent = {ent.name for ent in res.output.entities if ent.kind == "organization"}
            bucket("entities").add(pred_ent, set(case.get("expected_entities", [])))

    return {
        "categories": {k: v.as_dict() for k, v in sorted(per_cat.items())},
        "macro_f1": round(sum(v.f1 for v in per_cat.values()) / len(per_cat), 4)
        if per_cat
        else 0.0,
    }


# ------------------------------------------------------------------- entity resolution
def eval_entity_resolution() -> dict:
    """Runs against its own throwaway in-memory SQLite engine — never touches the
    process-global engine or ``DATABASE_URL`` (so ``eval_ranking`` still sees the real DB)."""
    from sqlalchemy import StaticPool, create_engine
    from sqlalchemy.orm import sessionmaker

    from intelligence.entity_resolution import ResolutionCandidate, resolve_person
    from intelligence.models import Base, Employment, Organization, Person

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    correct = 0
    false_merge = 0
    missed = 0
    total = 0
    rows = []

    for case in json.loads((_GOLDEN / "identities" / "cases.json").read_text()):
        s = Local()
        try:
            for spec in case["existing_people"]:
                p = Person(
                    canonical_name=spec["name"], primary_linkedin_url=spec.get("linkedin_url")
                )
                s.add(p)
                s.flush()
                for emp in spec.get("employers", []):
                    org = Organization(canonical_name=emp)
                    s.add(org)
                    s.flush()
                    s.add(
                        Employment(person_id=p.id, organization_id=org.id, title="x", current=True)
                    )
            s.flush()
            cand = case["candidate"]
            outcome = resolve_person(
                s,
                ResolutionCandidate(
                    name=cand["name"],
                    linkedin_url=cand.get("linkedin_url"),
                    current_employer=cand.get("current_employer"),
                ),
                persist=False,
            )
            total += 1
            got = str(outcome.decision)
            want = case["expected_decision"]
            is_correct = got == want
            if is_correct:
                correct += 1
            # a "false merge" == said MATCH when the gold was AMBIGUOUS / NO_MATCH / POSSIBLE
            if got == "MATCH" and want != "MATCH":
                false_merge += 1
            if want == "MATCH" and got != "MATCH":
                missed += 1
            rows.append(
                {"case": case["case_id"], "expected": want, "got": got, "score": outcome.score}
            )
        finally:
            s.rollback()
            s.close()

    engine.dispose()
    correct_rate = correct / total if total else 0.0
    false_merge_rate = false_merge / total if total else 0.0
    missed_rate = missed / total if total else 0.0
    return {
        "cases": rows,
        "correct_rate": round(correct_rate, 4),
        "false_merge_rate": round(false_merge_rate, 4),
        "missed_match_rate": round(missed_rate, 4),
        # false merge is weighted 5x — the costliest error (spec §33)
        "er_score": round(correct_rate - 5 * false_merge_rate, 4),
    }


# --------------------------------------------------------------------------- ranking
def eval_ranking() -> dict:
    """Distributional diagnostics from the live DB, plus label metrics if a golden
    ranking with relevance labels exists."""
    from sqlalchemy import select

    from intelligence.db import session_scope
    from intelligence.models import Person, ScoreSnapshot, ScoringModel

    out: dict = {"models": {}}
    with session_scope() as s:
        for target in ("founder", "lp", "talent", "connector"):
            snaps = list(
                s.execute(
                    select(ScoreSnapshot)
                    .join(ScoringModel, ScoringModel.id == ScoreSnapshot.scoring_model_id)
                    .where(ScoringModel.target_class == target)
                    .order_by(ScoreSnapshot.scored_at.desc())
                ).scalars()
            )
            # dedupe to latest per person
            latest: dict = {}
            for sn in snaps:
                latest.setdefault(sn.person_id, sn)
            vals = sorted((sn.priority_score for sn in latest.values()), reverse=True)
            if not vals:
                continue
            ranked_names = [
                (s.get(Person, pid).canonical_name if s.get(Person, pid) else str(pid))
                for pid, sn in sorted(latest.items(), key=lambda kv: -kv[1].priority_score)
            ]
            out["models"][target] = {
                "n": len(vals),
                "mean": round(sum(vals) / len(vals), 2),
                "p50": vals[len(vals) // 2],
                "p90": vals[max(0, int(len(vals) * 0.1) - 1)],
                "max": vals[0],
                "missing_feature_rate": round(_missing_feature_rate(s, target), 4),
                "top10": ranked_names[:10],
            }

        gold_dir = _GOLDEN / "rankings"
        for path in sorted(gold_dir.glob("*.json")) if gold_dir.exists() else []:
            g = json.loads(path.read_text())
            rel = {r["person"]: float(r.get("relevance", 0)) for r in g["items"]}
            model_top = out["models"].get(g["model_target"], {}).get("top10", [])
            relevant = {k for k, v in rel.items() if v >= 2}
            out.setdefault("labelled", {})[g["case_id"]] = {
                "precision@5": round(precision_at_k(model_top, relevant, 5), 4),
                "precision@10": round(precision_at_k(model_top, relevant, 10), 4),
                "recall@10": round(recall_at_k(model_top, relevant, 10), 4),
                "ndcg@10": round(ndcg_at_k(model_top, rel, 10), 4),
                "spearman": round(spearman(model_top, [r["person"] for r in g["items"]]), 4),
            }
    return out


def _missing_feature_rate(session, target: str) -> float:
    from sqlalchemy import select

    from intelligence.models import PersonFeatureSnapshot

    rows = list(
        session.execute(
            select(PersonFeatureSnapshot).where(PersonFeatureSnapshot.model_target == target)
        ).scalars()
    )
    if not rows:
        return 0.0
    total_missing = sum(len(r.missing_features or []) for r in rows)
    total_features = sum(len(r.features or {}) for r in rows) or 1
    return total_missing / total_features


# --------------------------------------------------------------------------- driver
_RUNNERS = {
    "extraction": eval_extraction,
    "entity_resolution": eval_entity_resolution,
    "ranking": eval_ranking,
}


def _check(name: str, result: dict, baseline: dict) -> list[str]:
    flags: list[str] = []
    base = baseline.get(name, {})
    if name == "extraction":
        for cat, m in result.get("categories", {}).items():
            b = base.get("categories", {}).get(cat, {}).get("f1")
            if b is not None and m["f1"] < b - 0.05:
                flags.append(f"REGRESSION extraction.{cat} F1 {b} -> {m['f1']}")
    if name == "entity_resolution":
        b = base.get("false_merge_rate")
        if b is not None and result["false_merge_rate"] > b + 1e-9:
            flags.append(
                f"REGRESSION entity_resolution false_merge_rate {b} -> {result['false_merge_rate']}"
            )
    return flags


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    which = [a for a in argv if not a.startswith("-")]
    do_check = "--check" in argv
    targets = list(_RUNNERS) if (not which or which == ["all"]) else which

    _ARTIFACTS.mkdir(parents=True, exist_ok=True)
    combined: dict = {}
    for t in targets:
        runner = _RUNNERS.get(t)
        if runner is None:
            print(f"unknown eval: {t}")
            return 2
        print(f"\n=== {t} ===")
        result = runner()
        combined[t] = result
        print(json.dumps(result, indent=2, default=str)[:4000])

    ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    (_ARTIFACTS / f"evals_{ts}.json").write_text(json.dumps(combined, indent=2, default=str))

    if do_check:
        base_path = _ARTIFACTS / "baseline.json"
        if not base_path.exists():
            base_path.write_text(json.dumps(combined, indent=2, default=str))
            print("\n(no baseline — wrote current run as baseline)")
        else:
            baseline = json.loads(base_path.read_text())
            flags = [f for t in targets for f in _check(t, combined[t], baseline)]
            if flags:
                print("\n".join("\033[31m" + f + "\033[0m" for f in flags))
                return 1
            print("\nno regressions vs baseline")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
