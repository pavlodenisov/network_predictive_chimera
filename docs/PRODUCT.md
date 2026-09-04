# PRODUCT.md — Chimera Network Intelligence

## 1. What this is

An internal quantitative research terminal for a venture firm. It turns permitted data
about the professional world into ranked, decomposable, provenanced intelligence about
**people** — founders, LPs, talent, connectors — and the **changes** around them.

It is **not** a chatbot, a CRM reskin, a social dashboard, or an "AI founder discovery"
app. It never emits subjective prose ("exciting founder", "impressive background").

## 2. Primary product question

> Given everything Chimera knows and everything that changed recently, who should the
> team spend time with now, why, and through whom?

Supporting questions the UI must answer at all times:

| Question | Where answered |
|---|---|
| Who newly entered the opportunity universe this week? | Discovery screen; digest §1 |
| What changed since last week's ranking? | Intelligence Δscore / Δrank columns; digest §2 |
| What evidence moved a person up or down? | Person → Score history → contribution deltas |
| What data is missing? | Person → Data gaps; Data Quality screen |
| Which statements are facts vs inferences? | Distinct objects, distinct UI sections, "inferred" badge |
| How confident are we in the evidence? | `confidence_score` shown separately from `priority_score` |
| Founder / LP / talent / connector opportunity? | `PersonClassification` + per-model scores |
| How do we reach this person? | Person → Warm paths (strongest path, hops, evidence, last verified) |
| Who is emerging before it's obvious? | Discovery + timing-weighted ranking |

## 3. Core principles (non-negotiable)

1. **Evidence over prose.** The UI shows structured evidence (years, counts, dates,
   ranks, source links), not generated sentences.
2. **Facts ≠ inferences.** Separate tables (`fact`, `inference`). An inference always
   carries: type, confidence, evidence IDs, model/extractor version, generated timestamp.
3. **Unknown means unknown.** Missing fundraising status is `unknown`, not "likely
   fundraising". `missing`, `0`, `false`, `unknown` are four distinct states.
4. **Deterministic scoring.** LLMs extract and classify. LLMs never output a
   person-quality or priority number. The scoring engine runs versioned formulas over
   explicit structured features.
5. **Reproducibility.** Any historical score reconstructs from stored observations,
   facts, event state, feature values, model version, normalization rules, weights.
6. **Temporal integrity.** `occurred_at` ≠ `observed_at` ≠ `ingested_at` ≠ `processed_at`.
7. **Point-in-time.** Historical beliefs are never silently overwritten. "What did we
   believe on 15 Aug?" is answerable.
8. **Model versioning.** `founder_v0.1`, `lp_v0.1`, … Every `ScoreSnapshot` names its model.
9. **No AI slop.** Banned vocabulary list in [`docs/SCORING.md` §UI language]. Numbers, events, dates, ranks, percentiles, source links only.

## 4. Personas

- **Investment team** — founder sourcing, emerging-founder detection, thesis-relevant
  discovery, warm intros, meeting prioritization.
- **Fundraising / GP team** — LP discovery, relationship tracking, LP movement signals,
  allocation-relevance signals, warm intros.
- **Talent / portfolio-support team** — executive/technical talent discovery, newly
  available talent, portfolio-role matching, warm intros.
- **Analyst** — inspect evidence, correct merges, annotate relationships, review events,
  inspect scoring, edit models, validate output.

## 5. Person classes (many-to-many)

`FOUNDER · POTENTIAL_FOUNDER · LP · POTENTIAL_LP · INVESTOR · OPERATOR · ENGINEER ·
RESEARCHER · TALENT · CONNECTOR · PORTFOLIO_EXECUTIVE · UNKNOWN`

A person can hold several at once (`PersonClassification` rows, each with source +
confidence + assigned_at). No forced mutually-exclusive label.

## 6. Person monitoring states

`DISCOVERED → REVIEW → ACTIVE_MONITORING → PASSIVE_MONITORING → ARCHIVED → DISMISSED`

Weekly jobs prioritize `ACTIVE_MONITORING` but retain all history.

## 7. Action field (deterministic, versioned — §57)

The system emits a standardized action per person per model, from a versioned rule set
(`configs/actions/v0.1.yaml`), never free-form:

`CONTACT_NOW · CONSIDER_CONTACT · MONITOR · REQUEST_INTRO · VERIFY_DATA ·
MATCH_TO_PORTFOLIO_ROLE · LP_RELATIONSHIP_BUILDING · PASS · UNKNOWN`

Example rule: `priority >= 85 and confidence >= 0.80 and access >= 70 → REQUEST_INTRO`.

## 8. Reason codes (§58)

Every flag carries machine codes rendered readably, e.g.
`EMPLOYMENT_DEPARTURE_RECENT`, `FOUNDER_TITLE_NEW`, `COMPANY_FORMATION`, `PRIOR_EXIT`,
`DOMAIN_MATCH`, `WARM_PATH_AVAILABLE`, `FAMILY_OFFICE_ROLE_NEW`, `VENTURE_MANDATE`,
`PORTFOLIO_ROLE_MATCH`, `DATA_STALE`, `LOW_CONFIDENCE`.

## 9. The central requirement — the explanation chain (§70)

A partner can drill from a rank to its raw source without a gap:

```
Rank #4  (universe: NA founder candidates, active, founder_v0.1, as of 2026-09-06)
  └ priority 87.31 = quality·.35 + fit·.25 + timing·.25 + access·.15
      └ quality 91.20 = Σ (normalized_feature_i · weight_i)
          └ feature prior_exit = 1.0
              └ normalization: binary
                  └ Fact(subject=person, fact_type=PRIOR_EXIT, value=true, valid_from=…)
                      └ Evidence(strength, source_label, quoted_fragment, observed_at)
                          └ RawObservation(immutable, source_url, raw_json, content_hash)
                              └ verified?  → Fact.extraction_method
                              └ inferred?  → Inference(type, probability, model_version)
  └ "what did we believe last week?" → prior ScoreSnapshot + PersonFeatureSnapshot
```

If this chain has a gap, the V0 architecture is incomplete.

## 10. Definition of done (V0.1) — see `docs/EVALUATION.md` for the checklist

Ingestion (multiple adapters, repeated snapshots, weekly pipeline) · Data (provenance,
normalized events, conservative dedup) · Analytics (4 models, decomposition, historical
snapshots, rank deltas) · Discovery (rule-based new people) · UI (ranked feed, person
drilldown, evidence inspection, model inspection, weekly runs, data quality) · Quality
(tests pass, seed works, deterministic weekly demo, docs exist).
