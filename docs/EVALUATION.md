# EVALUATION.md

`evals/` exists from day one (§33). It is separate from `tests/`: tests assert code
correctness; evals measure model/extraction quality against golden data and are allowed to
report a metric below target without failing CI (thresholds are advisory in V0).

```
evals/
  run.py                     # `python -m evals.run [extraction|entity_resolution|ranking|all]`
  golden/
    profiles/*.json          # synthetic profile snapshot pairs (week1, week2) + expected facts/events
    articles/*.json          # synthetic news items + expected entities/events
    identities/*.json        # entity-resolution cases with ground-truth match/no-match
    rankings/*.json           # ordered person lists with (optional) human relevance labels
  extraction/expectations.py # golden -> expected structured output
  entity_resolution/cases.py
  ranking/metrics.py         # precision@k, recall@k, NDCG, Spearman
```

## 1. Extraction accuracy  (§33)

Run `RuleBasedExtractor` (and `ClaudeExtractor` if `ANTHROPIC_API_KEY` set) over
`golden/profiles` + `golden/articles`. Report **precision / recall / F1** per category:

`employment_changes · founder_signals · fundraising_events · lp_events · talent_events ·
entities · dates`.

A prediction matches gold if `event_type` equal and (where applicable) `organization`
resolves to the same entity and `occurred_at` within ±3 days. Output: a table + JSON to
`artifacts/evals/extraction_<ts>.json`.

## 2. Entity resolution  (§33)

Over `golden/identities`: report **correct-merge rate**, **false-merge rate**,
**missed-match rate**. False merge is weighted 5× in the summary score
(`er_score = correct_rate − 5·false_merge_rate`) — a false merge corrupts two people's
histories and is the costliest error (§9).

Includes the "two Alex Lee" case (§65): an ambiguous article must yield `AMBIGUOUS`
(→ analyst queue), never an auto-merge.

## 3. Ranking  (§33)

When human labels exist in `golden/rankings/*.json` (`relevance: 0..3` per person):
report **Precision@5 / @10 / @25**, **Recall@25**, **NDCG@25**, **Spearman** vs the label
order. Without labels, report distributional diagnostics only (score histogram, dimension
means, missing-feature rates) and the top-25 with contribution breakdowns for eyeballing.

Downstream feedback (`analyst_feedback`) later provides real labels:
`top-decile meeting rate`, `contact rate`, `false-positive rate`. **Feedback is not used
to train production models in V0** (§32) — evaluation only.

## 4. Backtesting  (§35)

`python -m intelligence.backtest --model founder_v0.1 --from 2026-01-01 --to 2026-08-01`

Reconstructs point-in-time `PersonFeatureSnapshot`s from facts/events with
`valid_from <= as_of` and `occurred_at <= as_of` (no future leakage — a fact
`created_at` after `as_of` is excluded even if `valid_from` is earlier and it was not
knowable then; the backtest uses `observed_at`/`detected_at`). Emits: rankings per
weekly step, score distributions, feature-contribution distributions, and label metrics
if labels exist.

## 5. Regression gate

`evals/run.py --check` compares the current run to `artifacts/evals/baseline.json` and
prints deltas. An extraction F1 regression > 0.05 on any category, or any increase in
false-merge rate, prints a red line. CLAUDE.md rule: an extraction change is not approved
because "several examples look good" — the eval numbers must hold.

## 6. Definition-of-done checklist  (§66)

- [ ] multiple source adapters produce observations; repeated snapshots diff correctly
- [ ] weekly pipeline runs end to end and is idempotent on re-run
- [ ] every derived fact has evidence → immutable observation
- [ ] events normalized to the taxonomy; conservative dedup; no auto-merge of ambiguous ids
- [ ] founder / LP / talent / connector models score; decomposition + historical snapshots + rank deltas
- [ ] discovery produces new candidates from rules (staged, not auto-trusted)
- [ ] UI: ranked feed · person drilldown · evidence inspectable · models inspectable · weekly runs · data quality
- [ ] `make test` green (unit + integration + api + acceptance §62-65)
- [ ] `make seed` + deterministic `make weekly` reproducible
- [ ] docs present
