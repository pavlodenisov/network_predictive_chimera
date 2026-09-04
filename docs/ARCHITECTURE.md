# ARCHITECTURE.md

## 1. Shape

A single Python package (`intelligence/`) exposes both a FastAPI service and a set of
batch job modules, over one relational database. A Next.js app (`apps/web/`) is a thin
analytical client of the API. No message queue, no worker fleet — the weekly cycle is a
synchronous, ordered, idempotent pipeline (§39: "Do not require Celery unless queueing
genuinely becomes necessary").

```
sources ──▶ ingestion ──▶ RawObservation (immutable)
                              │
                    normalize + dedupe + story-cluster
                              │
                     extraction (rules | claude)  ──▶ ExtractionRun (observability)
                              │
                   Evidence ──▶ Fact ──▶ ┬─ Event      (versioned taxonomy)
                              │           └─ Inference  (labelled, probabilistic)
                              │
                  entity resolution (conservative, reversible)
                              │
                     features (per person, per model)  ──▶ PersonFeatureSnapshot
                              │
             scoring engine (deterministic, config-driven)  ──▶ ScoreSnapshot
                              │
                ranking + rank/score deltas + universe metadata
                              │
                 weekly digest (structured)  +  API  +  UI
```

## 2. Why these boundaries

| Concern | Module | Rule it enforces |
|---|---|---|
| Provenance | `ingestion/`, `models/observation.py`, `models/evidence.py` | RawObservation immutable; every Fact → Evidence → Observation |
| Fact/inference separation | `models/fact.py` vs `models/inference.py`; `snapshot/diff.py` | different objects, never merged |
| Deterministic scoring | `scoring/engine.py` + `configs/models/*.yaml` | no LLM in the number path; weights in YAML only |
| Reproducibility | `PersonFeatureSnapshot`, `ScoreSnapshot`, `ScoringModel.version`, `WeeklyRun.config_version` | rebuild any historical score |
| Temporal integrity | `intelligence/observability.py` timestamp helpers | 4 distinct time fields on observations/facts/events |
| Conservative identity | `entity_resolution/` + `EntityMergeLog` | auto-merge only above high threshold; every merge reversible |
| LLM containment | `extraction/base.py` Protocol | LLMs only behind strict Pydantic schemas; retry-once then record failure |

## 3. Package layout

```
intelligence/
  config.py            Settings (pydantic-settings): DATABASE_URL, config dir, extractor, log
  db.py                Engine, SessionLocal, Base, session dependency
  types.py             GUID + JSONB + UTCDateTime column types (dialect-portable)
  observability.py     structlog config; stage_logger(run_id, stage); now_utc(); temporal helpers
  models/              SQLAlchemy 2.0 ORM — one file per aggregate (see docs/DATA_MODEL.md)
  schemas/             Pydantic — api/ (responses) and extraction/ (strict LLM output schemas)
  repositories/        query helpers: list(filter, sort, page), get, provenance walkers
  api/
    app.py             FastAPI app factory, CORS, exception handlers, /health
    deps.py            get_session, pagination params
    routers/           people, rankings, events, discoveries, models, weekly_runs,
                       data_quality, feedback, overrides, imports, search
  ingestion/
    adapters/base.py   SourceAdapter Protocol + SourceHealth + RawObservationDraft
    adapters/*.py      manual_csv, json_snapshot, rss_news, synthetic (working);
                       linkedin_snapshot, crm, crunchbase, pitchbook, github (disabled stubs)
    normalize.py       provider record -> RawObservation
    dedupe.py          content-hash + provider-id dedupe; StoryCluster grouping
  extraction/
    base.py            Extractor Protocol; ExtractionRequest / ExtractionResult
    rules.py           RuleBasedExtractor (deterministic; default)
    claude.py          ClaudeExtractor (Anthropic API; inactive without ANTHROPIC_API_KEY)
    runner.py          run(extractor, obs) -> persists ExtractionRun; retry-once-on-invalid
  snapshot/
    diff.py            generic profile-snapshot diff + materiality rules -> facts/events/inferences
  entity_resolution/
    resolver.py        blocking + scorecard -> MATCH/POSSIBLE_MATCH/AMBIGUOUS/NO_MATCH
    merge.py           merge()/unmerge() via EntityMergeLog (reversible)
  events/
    taxonomy.py        versioned EVENT_TYPES registry (definition/evidence/confidence/expiry/models)
    detector.py        compare new facts to historical state -> Event rows (idempotent, supersede)
  features/
    normalization.py   pure-function registry: binary, capped_count, linear_cap, min_ratio,
                       exp_decay, tiered, passthrough_unit  (each: unit/cap/floor/missing/direction)
    freshness.py       per-feature-type stale thresholds (configurable)
    founder.py lp.py talent.py connector.py    feature builders -> {value,status} dicts
    registry.py        FEATURE_SETS[version] -> ordered feature specs
  scoring/
    config.py          load + validate configs/models/*.yaml -> ModelConfig
    engine.py          score(person, model_config, feature_snapshot) -> ScoreResult
    contributions.py   contribution_i = normalized_i * weight_i ; delta vs prior snapshot
    confidence.py      confidence_score from reliability/independence/age/extraction/ER/completeness
    access.py          BFS over RelationshipEdge from Chimera seed nodes -> strongest path
    actions.py         deterministic action rules (configs/actions/*.yaml) -> action + reason codes
  ranking/
    ranker.py          rank within a universe; percentile
    universe.py        Universe descriptor + stored metadata (filter, model, as_of)
    deltas.py          rank delta + score delta + per-feature contribution delta
  discovery/
    rules.py           DiscoveryRule evaluation against adapter output
    engine.py          candidate staging -> ER -> qualify -> feature -> rank
  digest/
    weekly.py          build structured digest (dict + deterministic text); 9 sections
  jobs/
    weekly.py          the 14-stage pipeline; writes WeeklyRun; --digest-only
    seed.py            load db/seeds/*  -> synthetic universe + week-1 baseline snapshots
  backtest.py          python -m intelligence.backtest  (point-in-time, no future leakage)
```

## 4. Database portability

`intelligence/types.py` is the only place that knows about dialects:

- `GUID` — `postgresql.UUID(as_uuid=True)` on PG, `CHAR(36)` on SQLite. App code always
  sees `uuid.UUID`.
- `JSONB` — `postgresql.JSONB` on PG, SQLAlchemy `JSON` (TEXT) on SQLite.
- `UTCDateTime` — `DateTime(timezone=True)`; values normalized to timezone-aware UTC on
  bind, re-attached as UTC on load (SQLite drops tzinfo).

Alembic migrations are authored once using these types. `alembic/env.py` reads
`DATABASE_URL`. SQLite connections set `PRAGMA foreign_keys=ON`.

**Known divergence (production risk):** JSONB containment/GIN queries and some CHECK
constraints behave differently on SQLite. V0 keeps all such logic at the ORM/Python layer
and never issues raw JSONB SQL. Postgres DDL is reviewed in `db/migrations` comments.

## 5. Determinism

The synthetic weekly pipeline has no network dependency and no clock dependency beyond an
injectable `as_of` date:

- extractor defaults to `RuleBasedExtractor`
- RSS adapter reads `db/seeds/news/*.xml`
- `jobs/seed.py` and `jobs/weekly.py` accept `--as-of YYYY-MM-DD`
- all IDs derived from content where a stable identity is needed (observations), random
  UUIDs elsewhere; tests seed a fixed RNG

Re-running `weekly` on the same inputs produces the same events, scores, and digest.

## 6. Deviations from the spec's suggested layout

| Spec §41 | Here | Reason |
|---|---|---|
| `services/{api,ingestion,…}` + `packages/{schemas,scoring,shared}` | one importable `intelligence/` package with those names as submodules | `python -m intelligence.jobs.weekly` / `intelligence.backtest` must work with no packaging indirection; a multi-package monorepo adds no V0 value |
| Postgres + Docker Compose as the dev path | SQLite default; compose file shipped for prod/CI | reference machine has no Docker/Postgres; `DATABASE_URL` restores the spec path |
| pnpm | npm | pnpm not available; lockfile-compatible |
| lightweight charting library | small in-house SVG components | keeps the "research terminal, no decoration" bar and the bundle lean |

## 7. Observability

`structlog` JSON or console (`CHIMERA_LOG_FORMAT`). Every pipeline stage logs
`run_id, stage, source_id?, count, duration_ms, warnings, errors`. Stage stats persist on
`WeeklyRun.stage_stats` (JSONB) and render on the Weekly Runs screen. Malformed records
are never silently dropped — they become `ExtractionRun(parse_status=failed)` or
`WeeklyRun.warnings` entries.
