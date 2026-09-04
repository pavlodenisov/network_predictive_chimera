# SCORING.md

> LLMs may extract and classify. **LLMs never produce a score.** Every number below comes
> from explicit structured features run through versioned formulas. Weights live in
> `configs/models/*.yaml`, never in Python. (CLAUDE.md rules 1, 5.)

All dimension and priority scores are reported on **0–100**. Feature values are normalized
to **0–1** first. `confidence_score` (0–1) is computed and displayed **separately** and is
never folded into `priority_score` (§18).

---

## 1. Normalization function catalogue  (`intelligence/features/normalization.py`)

Every numeric feature declares: `raw_unit`, `normalization`, `params`, `cap`, `floor`,
`missing_behavior`, `direction`. `missing_behavior` ∈ {`unknown`, `zero`, `neutral`}.
`unknown` → the feature is excluded from its dimension's weight renormalization and listed
in `missing_features` (never silently treated as 0).

| name | formula (raw `x`) | params | notes |
|---|---|---|---|
| `binary` | `1.0 if x else 0.0` | — | booleans (prior_exit, prior_founder) |
| `capped_count` | `min(x, max) / max` | `max` | counts (patents, promotions) |
| `linear_cap` | `clip(x / divisor, 0, 1)` | `divisor` | continuous (team size / 50) |
| `min_ratio` | `min(x / target, 1.0)` | `target` | "enough is enough" (years / 8) |
| `exp_decay` | `exp(-lambda · days)` | `lambda` | time-decayed signal value; `x` = days_since_event |
| `tiered` | lookup `x` → value in `tiers` | `tiers` (ordered) | e.g. relationship_strength label → access base |
| `passthrough_unit` | `clip(x, 0, 1)` | — | value already 0–1 (embedding similarity) |
| `bucket` | step function over thresholds | `thresholds` | seniority ladder → 0–1 |

`exp_decay` lambda per feature is documented in the model YAML and shown in the UI as
"event age = N days, half-life = M days".

---

## 2. Founder model  `founder_v0.1`

```
priority = quality·0.35 + fit·0.25 + timing·0.25 + access·0.15
```

Weights are V0 and stored in `configs/models/founder_v0.1.yaml` — "Do not treat these
initial weights as truth."

### 2.1 QUALITY (0.35) — demonstrated ability & execution (§11)

| feature | raw_unit | normalization | params | dir | missing |
|---|---|---|---|---|---|
| `prior_exit` | bool | binary | — | + | zero |
| `prior_founder` | count | capped_count | max 3 | + | zero |
| `institutional_fundraise` | bool | binary | — | + | zero |
| `product_shipped` | bool | binary | — | + | zero |
| `org_built_team_size` | people | linear_cap | divisor 50 | + | unknown |
| `verified_scale_milestone` | bool | binary | — | + | zero |
| `years_domain_experience` | years | min_ratio | target 8 | + | unknown |
| `years_engineering_experience` | years | min_ratio | target 10 | + | unknown |
| `research_depth` | count(papers) | capped_count | max 10 | + | zero |
| `patents` | count | capped_count | max 10 | + | zero |
| `oss_major` | bool | binary | — | + | zero |
| `early_employee_rank` | rank (1=first) | bucket | thresholds [10,50,200] → [1.0,0.7,0.4,0.1] | + | unknown |
| `promotions` | count | capped_count | max 4 | + | zero |
| `time_to_leadership_years` | years | min_ratio inverted | target 6, `invert:true` | + | unknown |
| `budget_ownership` | bool | binary | — | + | zero |
| `prestige_weak_signal` | bool | binary | — | + | zero |

`prestige_weak_signal` is capped to a small feature weight (≤ 0.04 of quality) and is the
**only** place pedigree enters. "Stanford = good founder" / "OpenAI = good founder" are
explicitly not encoded (§11). Execution features dominate.

Dimension score = `100 · Σ(norm_i · w_i) / Σ(w_i over present features)` (renormalize over
present features so `unknown` doesn't silently deflate).

### 2.2 FIT (0.25) — alignment with Chimera thesis (§12)

| feature | raw_unit | normalization | params | dir |
|---|---|---|---|---|
| `sector_match` | 0–1 | passthrough_unit | — | + |
| `technology_match` | 0–1 | passthrough_unit | — | + |
| `technical_topic_match` | 0–1 | passthrough_unit | — | + |
| `business_model_match` | 0–1 | passthrough_unit | — | + |
| `stage_match` | 0–1 | passthrough_unit | — | + |
| `geography_match` | 0–1 | passthrough_unit | — | + |
| `portfolio_adjacency` | 0–1 | passthrough_unit | — | + |
| `thesis_embedding_similarity` | 0–1 | passthrough_unit | — | + |

Matches are computed by `features/founder.py` against `thesis_configuration`. V0 uses
deterministic keyword/topic overlap for `*_match` and a stored `thesis_embedding_similarity`
(embedding model + version recorded; `0` if no embedding available → `unknown`, not 0).
Evidence keywords/topics are stored alongside so the number is explainable (§12).

### 2.3 TIMING (0.25) — reason to engage now (§13)

Each signal contributes `initial_value · exp_decay(lambda, days_since_event)`. `days` is
`as_of_date − event.occurred_at`. Signals (initial_value, half-life days):

| signal (event/inference) | initial | half-life | lambda |
|---|---|---|---|
| `EMPLOYMENT_ENDED` | 1.00 | 45 | 0.0154 |
| `FOUNDER_TITLE_ADDED` | 1.00 | 60 | 0.0116 |
| `STEALTH_COMPANY_SIGNAL` | 0.85 | 45 | 0.0154 |
| `POSSIBLE_COMPANY_FORMATION` (inference) | `0.9·probability` | 40 | 0.0173 |
| `COMPANY_FORMATION_CONFIRMED` | 1.00 | 120 | 0.0058 |
| `PRODUCT_LAUNCH` | 0.80 | 90 | 0.0077 |
| `FUNDRAISE_ANNOUNCED` | 0.95 | 75 | 0.0092 |
| `COFOUNDER_SEARCH` | 0.80 | 40 | 0.0173 |
| `hiring_started` | 0.70 | 60 | 0.0116 |
| `domain_activity_spike` | 0.50 | 30 | 0.0231 |

`timing = 100 · clip(Σ decayed_signal_values, 0, 1)`. UI shows each signal, its age, its
decayed value, and the half-life.

### 2.4 ACCESS (0.15) — see §5 below (shared by all models).

---

## 3. LP model  `lp_v0.1`  (§15) — distinct from founder; do not reuse quality

```
priority = authority·0.20 + capital_relevance·0.15 + venture_allocation_fit·0.20
         + emerging_manager_fit·0.10 + chimera_fit·0.15 + timing·0.10 + access·0.10
```

| dimension | key features (normalization) |
|---|---|
| `authority` | `is_cio` / `is_partner` / `is_ic_member` / `is_head_of_alternatives` / `is_head_of_venture` / `is_family_office_lead` / `principal_with_mandate` — all `binary`, max-pooled with small additive bonus for multiple |
| `capital_relevance` | `org_is_allocator_type` binary; `disclosed_aum_usd` → `min_ratio(target 5e9)` (only disclosed; missing→unknown); `known_fund_investment_activity` binary. **No private personal wealth estimate.** |
| `venture_allocation_fit` | `allocates_to_vc` / `allocates_to_emerging_managers` / `allocates_early_stage` / `geo_match` / `strategy_match` — binary / passthrough |
| `emerging_manager_fit` | `emerging_manager_program_evidence` binary; `prior_emerging_commitments` capped_count max 5 |
| `chimera_fit` | match of org profile to Chimera fund characteristics (stage, size, sector, geo) — passthrough 0–1 |
| `timing` | `exp_decay` over: `CIO_ROLE_STARTED`, `PARTNER_ROLE_STARTED`, `INVESTMENT_MANDATE_CHANGED`, `LP_ROLE_STARTED`, org formed, new fund program, liquidity/strategy event (initials 0.8–1.0, half-life 60–90d) |
| `access` | §5 |

---

## 4. Talent model  `talent_v0.1`  (§16) — `person × role_need`, not "how talented is X"

A person has **one score per open `portfolio_role_need`**, stored in
`candidate_role_match`. Dimensions:

```
match = functional·0.18 + seniority·0.12 + domain·0.18 + stage_experience·0.12
      + operating_experience·0.10 + execution_evidence·0.12 + location·0.06
      + availability_timing·0.06 + access·0.06
```

| dimension | normalization |
|---|---|
| `functional` | role.function vs person function history → `tiered` (exact 1.0 / adjacent 0.6 / none 0.1) |
| `seniority` | ladder distance → `bucket` (exact 1.0, ±1 0.7, ±2 0.4) |
| `domain` | overlap of `role.domain_requirements` with person facts/topics → 0–1 |
| `stage_experience` | person worked at companies matching `role.stage_requirements` → `binary`/`bucket` |
| `operating_experience` | years in operating (non-founder IC/mgmt) roles → `min_ratio(target 8)` |
| `execution_evidence` | reuse a subset of founder quality execution features → 0–1 |
| `location` | `role.location_requirements` vs `person.primary_location` → `tiered` (same metro 1.0 / same country 0.6 / remote-ok 0.8 / mismatch 0.1) |
| `availability_timing` | `exp_decay` over `PROFESSIONAL_DEPARTURE`, `NEW_EXECUTIVE_ROLE` (negative), `OPEN_TO_WORK_SIGNAL`. **Availability is a labelled inference** unless `OPEN_TO_WORK_DECLARED` fact exists (§64: never state "job searching" without evidence). |
| `access` | §5 |

Person screen shows the per-role table (e.g. `Head of AI — Portfolio A  94.2` /
`VP Eng — Portfolio B  71.3` / `COO — Portfolio C  18.4`) with decomposition.

---

## 5. Access model  `access_v0.1`  (§14) — shared graph layer

`intelligence/scoring/access.py` runs BFS (≤3 hops) over `relationship_edge` from the set
of `person.is_chimera_seed = true` nodes to the target. Base score by strongest path
(`configs/models/access_v0.1.yaml`, all configurable):

| path | base |
|---|---|
| DIRECT relationship (target is/for Chimera) | 100 |
| 1 hop STRONG | 90 |
| 1 hop MODERATE | 75 |
| 1 hop WEAK | 55 |
| 2-hop STRONG (min edge STRONG) | 45 |
| 2-hop MODERATE | 30 |
| 3-hop any | 15 |
| no known path | 0 |
| any edge on path with strength `UNKNOWN` and no better path | `unknown` (not 0) |

Adjustments (bounded, configurable):
- `+ up to 8` for ≥2 independent paths (distinct first hop)
- `− up to 15` for relationship staleness: `last_verified_at` older than
  `freshness.network_relationship` (365d) decays the base by `min(15, 0.04·months_stale)`
- `× confidence` clamp: multiply by `mean(edge.confidence on chosen path)` when present

Output stored on `score_snapshot`: `access_score`, plus `strongest_path` in
`contribution_breakdown.access` = `{hops, strength, node_names, edge_evidence_ids,
last_verified_at, independent_path_count}`.

---

## 6. Connector model  `connector_v0.1`  (§17)

```
priority = relevant_connections·0.28 + founder_connectivity·0.16 + lp_connectivity·0.16
         + portfolio_connectivity·0.12 + cross_sector·0.10 + independent_paths·0.10
         + relationship_freshness·0.04 + intro_track_record·0.04
```

| feature | normalization |
|---|---|
| `relevant_connections` | count of edges to Chimera-relevant people (founder/LP/portfolio classes) → `capped_count(max 40)` |
| `founder_connectivity` / `lp_connectivity` / `portfolio_connectivity` | counts by class → `capped_count` (max 25 / 15 / 15) |
| `cross_sector` | distinct sectors among connections → `capped_count(max 6)` |
| `independent_paths` | count of independent Chimera→X paths this person enables → `capped_count(max 10)` |
| `relationship_freshness` | share of this person's edges verified within 365d → passthrough |
| `intro_track_record` | count of `INTRO_REQUESTED`→`INTRO_COMPLETED`/`MEETING_BOOKED` feedback where this person was the connector → `capped_count(max 10)` |

"Avoid vanity network-size metrics" — follower counts are **not** a feature. 10 relevant
strong relationships beat 10,000 followers (§17).

---

## 7. Confidence  (`intelligence/scoring/confidence.py`, §18)

`confidence_score = w·[reliability, independence, recency, extraction, identity,
completeness]` — default weights `[0.22, 0.18, 0.18, 0.15, 0.12, 0.15]`
(`configs/models/*.yaml → confidence:` block, versioned).

| component | 0–1 definition |
|---|---|
| reliability | mean evidence `evidence_strength` over facts feeding present features |
| independence | `min(1, 0.5 + 0.25·distinct_source_domains)` across feeding observations |
| recency | `mean(exp(-0.005 · age_days))` over feeding facts |
| extraction | mean `fact.extraction_confidence` (deterministic parse = 1.0) |
| identity | `person.entity_resolution` confidence (RESOLVED=1.0, NEEDS_REVIEW=0.6, UNRESOLVED=0.75) |
| completeness | `present_feature_weight / total_feature_weight` for the model |

Displayed as `Priority: 91.4 / Confidence: 0.94`. Never `Adjusted AI score: 85.7`.
Low-confidence rows are filterable, not hidden.

---

## 8. Contributions & deltas  (`intelligence/scoring/contributions.py`, §19)

For the linear V0 models:

```
contribution(feature_i)      = normalized_feature_i · effective_weight_i        # stored per feature
dimension_score              = 100 · Σ contribution_i (present) / Σ eff_weight_i (present)
priority_score               = Σ dimension_score · dimension_weight
delta_contribution(feature_i)= new_contribution_i − old_contribution_i          # vs previous ScoreSnapshot
```

`contribution_breakdown` (JSONB on `score_snapshot`) holds, per feature:
`{raw, status, normalized, weight, effective_weight, contribution, fact_ids, freshness}`.
`delta_breakdown` holds `{feature: {old, new, delta}}` and dimension-level roll-ups,
powering "Why did the score change?":

```
Founder Priority 68.3 → 91.4  (+23.1)
  +14.0  timing: EMPLOYMENT_ENDED  (new, age 6d)
  +6.5   timing: POSSIBLE_COMPANY_FORMATION  (inference 0.74)
  +2.6   fit: technical_topic_match 0.55 → 0.71
```

These numbers are arithmetic on stored features. No LLM (§19).

---

## 9. Universe & percentile  (§53–54)

Every `score_snapshot.rank` is meaningless without its `ranking_universe`
(`{label, model_target, scoring_model_id, filter, as_of_date, member_count}`). UI shows:

```
Founder score 87.2 · Percentile 96.4th · Universe 3,218 monitored founder candidates
Rank #14 / 3,218 — NA founder candidates · active monitoring · founder_v0.1 · as of 2026-09-06
```

Percentile = share of universe with `priority_score ≤ this`.

---

## 10. Action rules  (`configs/actions/v0.1.yaml`, §57)

Ordered, deterministic, versioned. First match wins. Example:

```yaml
version: actions_v0.1
rules:
  - when: {priority_gte: 85, confidence_gte: 0.80, access_gte: 70}
    then: REQUEST_INTRO
    reason_codes: [HIGH_PRIORITY, WARM_PATH_AVAILABLE]
  - when: {priority_gte: 85, confidence_gte: 0.80, access_lt: 70}
    then: CONTACT_NOW
    reason_codes: [HIGH_PRIORITY, NO_WARM_PATH]
  - when: {priority_gte: 70, confidence_lt: 0.6}
    then: VERIFY_DATA
    reason_codes: [LOW_CONFIDENCE]
  - when: {model_target: talent, has_role_match: true}
    then: MATCH_TO_PORTFOLIO_ROLE
    reason_codes: [PORTFOLIO_ROLE_MATCH]
  - when: {model_target: lp, priority_gte: 65}
    then: LP_RELATIONSHIP_BUILDING
    reason_codes: [LP_CANDIDATE]
  - when: {priority_gte: 55}
    then: MONITOR
  - when: {always: true}
    then: PASS
```

---

## 11. Model configuration format  (`configs/models/*.yaml`, §21)

```yaml
name: founder
version: v0.1
target_class: founder
scale: 100
priority:                       # dimension weights — MUST sum to 1.0
  quality: 0.35
  fit: 0.25
  timing: 0.25
  access: 0.15
dimensions:
  quality:
    renormalize_over_present: true
    features:
      prior_exit:      {weight: 0.16, normalization: binary,       missing_behavior: zero,    direction: positive}
      prior_founder:   {weight: 0.12, normalization: capped_count, params: {max: 3}, missing_behavior: zero, direction: positive}
      years_domain_experience:
                       {weight: 0.10, normalization: min_ratio,    params: {target: 8}, missing_behavior: unknown, direction: positive}
      # …
  timing:
    signals:
      EMPLOYMENT_ENDED:            {initial: 1.00, half_life_days: 45}
      POSSIBLE_COMPANY_FORMATION:  {initial_from: probability, factor: 0.9, half_life_days: 40}
      # …
confidence:
  weights: {reliability: 0.22, independence: 0.18, recency: 0.18, extraction: 0.15, identity: 0.12, completeness: 0.15}
access_model: access_v0.1
```

Loader (`scoring/config.py`) validates: dimension weights sum to 1.0 (±1e-6); every
feature names a known normalization; `missing_behavior` ∈ enum; unknown keys rejected. On
`weekly` run the active config is hashed → `scoring_model.config_hash`; a changed hash
requires an explicit new `version` (CLAUDE.md rule 5 — no silent weight changes).

---

## 12. UI language policy  (§9, §30)

**Banned in product output** (unless a formally defined quantitative category):
`exciting`, `compelling`, `impressive`, `strong pedigree`, `amazing`, `fascinating`,
`highly promising`, `great founder`, `visionary`, `strong leader`, `worth keeping an eye
on`, `interesting development`.

**Use instead:** `Employment ended 6 days ago.` · `Founder title added.` · `2 independent
sources.` · `Direct Chimera relationship.` · `3.2 years inference infrastructure
experience.` · `Current employment unknown.` · `Company formation inference: 0.74.`

`tests/unit/test_language_policy.py` greps rendered digest + API string fields for the
banned list.
