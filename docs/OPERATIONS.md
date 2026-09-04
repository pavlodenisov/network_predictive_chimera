# OPERATIONS.md

## 1. Local startup (native, SQLite)

```bash
cp .env.example .env
make setup            # python venv + pip + `npm install` in apps/web
make migrate          # alembic upgrade head  -> ./chimera.db
make seed             # synthetic week-1 baseline universe + baseline ScoreSnapshots
make weekly           # 14-stage pipeline over week-2 fixtures; prints the digest
make api              # http://127.0.0.1:8000  (OpenAPI at /docs)
make web              # http://localhost:3000
# or:  make dev       # api + web together
```

`make reset` = drop `chimera.db`, re-migrate, re-seed.

## 2. Postgres (spec-faithful path)

```bash
# with a running Postgres 16:
createdb chimera
export DATABASE_URL=postgresql+psycopg://USER:PASS@localhost:5432/chimera
pip install -e '.[postgres]'
make migrate && make seed && make weekly
```

Or `docker compose up` (brings up db + api + web; api container runs migrate+seed then
uvicorn). The compose file is CI-exercised; the reference laptop has no Docker.

## 3. The weekly cycle  (§6)

`python -m intelligence.jobs.weekly [--as-of YYYY-MM-DD] [--digest-only] [--dry-run]`

14 ordered stages, each logged (`run_id, stage, count, duration_ms, warnings`) and
recorded on `weekly_run.stage_stats`:

1. Source health — probe every enabled adapter; record successful/partial/failed/disabled.
   A major source failure sets `weekly_run.status=partial` and a degraded-coverage warning;
   the run continues but the gap is explicit.
2. Update known people — `update_known_entities` for `ACTIVE_MONITORING` (then `PASSIVE`).
3. Discover new people — evaluate active `DiscoveryRule`s → `discovery_candidate` staging.
4. Normalize observations → one `RawObservation` schema.
5. Deduplicate — content hash + provider id; syndicated news → `story_cluster`.
6. Entity resolution — resolve people/orgs/funds; record confidence; ambiguous → analyst queue.
7. Extract structured facts — deterministic parse first; LLM only for unstructured text,
   schema-validated, retry-once, else `extraction_run.parse_status=failed`.
8. Detect events — diff new facts vs historical state → taxonomy `Event` rows (idempotent).
9. Build/update features — per person, per model → `PersonFeatureSnapshot`.
10. Run scoring models — founder/LP/talent/connector over present features.
11. Rank deltas — current vs previous-week rank/score + per-feature contribution deltas.
12. Generate intelligence feed — ranked lists + movers + new events + data-quality issues.
13. Store `WeeklyRun` — full metadata, coverage, counts, errors, warnings, versions.
14. Generate digest — structured (dict + deterministic text); stored on `weekly_run.digest`.

**Idempotency:** re-running with the same inputs/`as-of` creates no duplicate observations
(hash), facts (subject+type+value+valid_from), or events (`dedupe_key`). Safe to retry.

## 4. Scheduling  (§47)

`.github/workflows/weekly.yml` — `schedule: cron` (default `17 13 * * 1`, Mondays 13:17
UTC) **and** `workflow_dispatch` (manual). It runs the identical
`python -m intelligence.jobs.weekly` — no separate "cron logic". Secrets via repo/env
secrets. Change the cadence by editing the one `cron:` line. A non-cron host (systemd
timer, platform scheduler) runs the same command.

Failure visibility: the job always writes a `weekly_run` row (status `failed`/`partial`)
before propagating a non-zero exit, so the Weekly Runs screen shows the failure.

## 5. Observability

- `CHIMERA_LOG_FORMAT=json` for production; `console` locally.
- Weekly Runs screen: per-run duration, per-stage counts/durations, source coverage,
  errors, warnings, model + code versions; click a run for its audit trail.
- Data Quality screen: source failures, stale records, conflicting employment, unresolved
  entities, extraction failures, missing key features, suspicious duplicates.

## 6. Backup / retention

SQLite: back up `chimera.db`. Postgres: standard `pg_dump`. `raw_observation` and all
audit tables are append-only and must be retained for reproducibility (§2.5, §2.7).

## 7. Runbooks

| symptom | check | action |
|---|---|---|
| weekly run `partial` | Weekly Runs → source coverage | inspect the failed adapter's `errors`; re-run stage-scoped `--only-source` once cause fixed |
| person score jumped unexpectedly | Person → Score history → `delta_breakdown` | verify feeding events/facts; if bad extraction → `analyst_override` INCORRECT_EVENT + re-run |
| duplicate person | Data Quality → suspicious duplicates | analyst merge (reversible); or mark not-a-dup |
| wrong merge | Person → Source history shows merged ids | `entity_merge_log` → unmerge; add negative training case to `evals/golden/identities` |
| extraction failures rising | Data Quality → extraction failures; `extraction_run` rows | inspect `error`; fix rule / schema; keep `CHIMERA_EXTRACTOR=rules` if LLM provider degraded |

## 8. Production risks (V0 → V1)

See `docs/REPORT.md` (generated at the end of the build) for the ranked list. Headline
items: SQLite→Postgres semantics, real authenticated SSO, authorized data-source
contracts replacing synthetic/stub adapters, LLM extraction cost/latency/eval gating,
graph access at scale (BFS → materialized paths).
