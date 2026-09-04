# REPORT.md — Chimera Network Intelligence V0.1

Build status at handoff. Everything below was executed on the reference machine
(macOS, Python 3.14, Node 24, no Docker/Postgres) and passes.

## 1. Validation results

| Gate | Command | Result |
|---|---|---|
| Lint | `./.venv/bin/ruff check intelligence tests evals` | clean |
| Format | `./.venv/bin/ruff format --check …` | 113 files formatted |
| Types | `./.venv/bin/mypy` | 0 issues, 91 files |
| Unit + integration + API + acceptance | `make test` | **155 passed** |
| Acceptance scenarios §62–65 | `pytest tests/acceptance -m acceptance` | 4/4 pass |
| Migrations | `alembic upgrade head` → `downgrade base` → `upgrade head` | clean roundtrip (SQLite) |
| Seed | `make seed` | 111 people (42 founder / 20 LP / 25 talent / 15 connector) + Chimera seeds + 2× "Alex Lee" + week-1 baseline scores |
| Weekly pipeline | `make weekly` (as of 2026-09-06) | `status=success`, 14 stages logged, digest stored |
| Backtest | `python -m intelligence.backtest --model founder_v0.1 --from 2026-01-01 --to 2026-08-01` | point-in-time steps, no future leakage |
| Evals | `python -m evals.run all --check` | extraction macro-F1 **0.84**, entity-resolution false-merge rate **0.0**, no regressions vs baseline |
| Frontend | `cd apps/web && npm run lint && npm run build` | clean, 108 kB First-Load JS |
| Playwright | `npm run test:e2e` | 3/3 smoke flows pass (Intelligence → Sarah Chen → evidence chain; Models; Weekly Runs) |

### Acceptance scenario evidence (§62, verified end to end in the browser)

`Sarah Chen` founder priority **27.0 → 52.0** week-over-week (rank **#8 → #1**), driven by
decomposable timing contributions: `EMPLOYMENT_ENDED +1.9`, `POSSIBLE_COMPANY_FORMATION
+1.1` (inference, p=0.75), `STEALTH_COMPANY_SIGNAL +0.8`. Access `70.55` via a 1-hop
MODERATE path `Rowan Ellis → Sarah Chen`. Confidence `0.86` shown separately.
`fundraising_status` renders as the literal word **unknown**. The Person screen walks
priority → dimension → feature → normalization rule → Fact → Evidence → RawObservation.

## 2. Local startup commands

```bash
cp .env.example .env
make setup            # .venv + pip install -e . + (cd apps/web && npm install)
make migrate          # alembic upgrade head  →  ./chimera.db (SQLite)
make seed             # synthetic week-1 baseline universe + baseline ScoreSnapshots
make weekly           # 14-stage pipeline over week-2 fixtures (as of 2026-09-06); prints the digest
make test             # unit + integration + api + acceptance
make backtest         # point-in-time backtest of founder_v0.1
make lint             # ruff + mypy
make evals            # python -m evals.run all

# two terminals (or `make dev` for both):
make api              # http://127.0.0.1:8000   (OpenAPI at /docs)
make web              # http://localhost:3000

# frontend gates:
cd apps/web && npm run build && npm run test:e2e
```

`make reset` = drop `chimera.db`, re-migrate, re-seed. Postgres path: set
`DATABASE_URL=postgresql+psycopg://…`, `pip install -e '.[postgres]'`, then the same
targets; `docker compose up` brings up db + api + web (CI-exercised).

Scheduled run: `.github/workflows/weekly.yml` (cron `17 13 * * 1` + `workflow_dispatch`)
invokes the identical `python -m intelligence.jobs.weekly`.

## 3. Replacing synthetic / import sources with authorized production sources

Every source implements `intelligence/ingestion/adapters/base.py::SourceAdapter`
(`discover` / `update_known_entities` / `health_check`). The pipeline downstream of
ingestion is source-agnostic. To bring a real source online:

1. **Implement or configure the adapter.** Working adapters ship for `SyntheticSource`,
   `ManualCSVSource`, `JSONSnapshotSource`, `RSSNewsSource`. Disabled stubs (full class +
   config schema + `health_check` returning `disabled`) ship for
   `LinkedInSnapshotSource`, `CRMSource`, `CrunchbaseSource`, `PitchBookSource`,
   `GitHubSource` — fill in `discover` / `update_known_entities` to return
   `RawObservationDraft`s.
2. **Register a `source` row** (or edit the one `intelligence/jobs/seed.py::_ensure_live_sources`
   creates): `provider`, `source_type`, `reliability_tier` (1 best … 5 weak, per
   `docs/SOURCES.md §4`), `enabled=true`, and `configuration` (JSON — base URLs, dataset
   names; **no secrets here**).
3. **Put credentials in the environment** only, read via `intelligence/config.py`. Add the
   new var to `.env.example`. Adapters that can't authenticate must return
   `SourceHealth(status="disabled")`, never raise.
4. **LinkedIn specifically**: `LinkedInSnapshotSource` expects *authorized* snapshots /
   licensed provider records shaped like `JSONSnapshotSource` input (headline,
   current_company, current_title, current_seniority, location, plus provider IDs). No
   scraping. Repeated captures are diffed by `intelligence/snapshot/diff.py` automatically.
5. **News**: `RSSNewsSource` reads `db/seeds/news/*.xml` by default; set
   `CHIMERA_RSS_LIVE=1` and `source.configuration.feed_urls=[…]` for live fetch (honours
   feed terms + a polite delay). Syndicated copies are clustered (`story_cluster`);
   independent-source confidence counts distinct domains, not articles.
6. **LLM extraction**: default is the deterministic `RuleBasedExtractor`. Set
   `CHIMERA_EXTRACTOR=claude` + `ANTHROPIC_API_KEY` to activate `ClaudeExtractor` (same
   `Extractor` interface, strict Pydantic-validated output, retry-once, `ExtractionRun`
   logged). Re-run `python -m evals.run extraction --check` before trusting it in the
   scoring path.
7. **Run** `make weekly` (or wait for the cron). New sources appear in Stage-1 source
   coverage on the Weekly Runs screen; a failure marks the run `partial` with a visible
   warning — it never silently drops coverage.

## 4. Remaining production risks (ranked)

1. **SQLite → PostgreSQL semantics.** Models + migrations are Postgres-first behind a
   dialect shim (`intelligence/types.py`), but JSONB containment/GIN queries and some
   CHECK constraints differ. V0 keeps all such logic at the ORM/Python layer. *Mitigation:*
   run the suite + `docker compose up` against Postgres 16 in CI before any deploy; add
   JSONB indexes for the feature/score JSON columns.
2. **Authentication is a stub.** `intelligence/api/deps.py::get_current_user` returns a
   static dev principal (overridable by an `X-User-Email` header). *Mitigation:* wire the
   firm's OIDC/SAML into that one function; the rest of the codebase already depends only
   on the abstraction. Deploy behind the firm's SSO/reverse proxy; the API binds
   `127.0.0.1` and restricts CORS by default.
3. **No authorized data yet.** All non-synthetic adapters are disabled stubs. Scores,
   rankings, and the digest are only as good as the data behind them; the current numbers
   reflect deterministic synthetic fixtures. *Mitigation:* stand up `JSONSnapshotSource` +
   `RSSNewsSource` + `CRMSource` first (highest signal, lowest contract friction).
4. **Rule-based extraction has real gaps.** Eval macro-F1 0.84; `fundraising_events` and
   `lp_events` recall ≈ 0.5 on the golden news set (misses some `$X Series A` phrasings and
   `PARTNER_ROLE_STARTED`). *Mitigation:* expand rules for the specific phrasings the real
   feeds use, or enable `ClaudeExtractor` and gate on the eval numbers.
5. **Graph access at scale.** `intelligence/scoring/access.py` does BFS per person per run.
   Fine at 10k–100k people with the shipped indexes; at 1M+ it needs materialized
   shortest paths or a graph store. *Mitigation:* cache the Chimera-seed BFS frontier per
   run; precompute 1–2 hop reachability.
6. **`ContextVar` point-in-time flag.** Backtest correctness relies on
   `POINT_IN_TIME_CUTOFF` being set around scoring calls. A future caller that scores
   outside that scope would silently leak later-recorded facts into a historical run.
   *Mitigation:* thread an explicit `as_of_recorded` parameter through the feature
   builders in V0.2.
7. **`quoted_fragment` retention.** Evidence stores source quotes when
   `metadata.quote_retention_ok`; adapters must set this per source's terms. Getting it
   wrong is a compliance issue, not a bug. *Mitigation:* default it to `false`; require an
   explicit per-source opt-in.

## 5. Next five improvements — ranked by expected analytical value

1. **Analyst-label capture → ranking evaluation loop.** The feedback table and
   `evals/ranking` metrics (P@k, NDCG, Spearman) are built but unfed. Add a one-click
   "CONTACT_NOW / CONSIDER / PASS" control on the Intelligence table that writes
   `analyst_feedback`, then report top-decile contact rate and false-positive rate per
   weekly run. This is the only way to know whether the models are actually good, and it
   turns every analyst action into training/eval data. *Value: highest — it makes every
   other tuning decision measurable.*
2. **Thesis embedding similarity for FIT.** `thesis_embedding_similarity` is wired but
   `unknown` (no provider). Add an authorized embedding provider, store model + version +
   cosine + the nearest thesis snippets. Deterministic keyword overlap alone under-ranks
   founders whose work matches the thesis semantically but not lexically.
3. **Conflict-aware canonical state + point-in-time snapshots.** `docs/SOURCES.md §5`
   specifies the conflict-resolution policy (recency > reliability > directness) and the
   Data Quality screen surfaces conflicts, but the pipeline currently takes the latest
   fact. Implement provisional-canonical selection + effective-dated `Person` snapshots so
   "what did we believe on 15 Aug" is answerable for every field, not just scores.
4. **Real entity resolution for organizations + funds.** Person resolution is
   conservative and tested; org/fund resolution is get-or-create by exact name, which
   fragments "Synthetic AI Labs" vs "Synthetic AI Labs, Inc." Add the same
   blocking+scorecard treatment to organizations (domain, aliases, ticker) — it directly
   improves employer-overlap in person resolution and sector matching in FIT.
5. **Materiality + decay tuning from data.** Half-lives, the headline-materiality
   threshold, and the access base table are hand-set V0 constants. Once #1 provides
   labels, fit the timing decay λ per signal to observed "time from signal to a
   successful meeting", and calibrate the access bands against actual intro success rates.
   Version every change (`founder_v0.2`) and diff via the Models compare endpoint.

---

## Deviations from the spec (all deliberate; see `docs/ARCHITECTURE.md §6`)

- SQLite is the default DB (no Postgres/Docker on the reference machine); Postgres-first
  models + migrations + a `docker-compose.yml` ship for production.
- One importable `intelligence/` package (submodules named per the spec's services)
  instead of a `services/*` + `packages/*` split, so `python -m intelligence.jobs.weekly`
  / `intelligence.backtest` work without packaging indirection.
- npm instead of pnpm; a hand-written dense stylesheet instead of Tailwind (keeps the
  "research terminal, no decoration" bar; TanStack Table/Query still used).
- RSS adapter reads local fixtures by default (deterministic offline demo).
- `make weekly` passes `--as-of 2026-09-06` so the synthetic week-2 fixtures are in range;
  a real deployment runs with no `--as-of`.
