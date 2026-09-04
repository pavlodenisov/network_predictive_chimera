# Chimera Network Intelligence

An internal analytical intelligence platform for a venture capital firm. It continuously
converts professional-network activity, company activity, public news, portfolio
information, and relationship data into **structured, auditable intelligence** about:

1. founders Chimera should know
2. potential LPs Chimera should develop relationships with
3. exceptional potential hires for Chimera or its portfolio companies
4. high-value connectors in Chimera's network
5. newly discovered people outside Chimera's existing network
6. meaningful changes involving already-known people
7. the strongest available relationship path from Chimera to each person

This is a quantitative research terminal, not an AI chatbot. The product standard:

> Every recommendation explainable. Every score decomposable. Every fact has provenance.
> Every inference labeled as an inference. Every model versioned. Every historical output
> reproducible. Every unknown left unknown.

See [`docs/PRODUCT.md`](docs/PRODUCT.md) for the full product definition and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the system design.

---

## Quick start (local, native — no Docker required)

Requires Python 3.11+ and Node 20+. The reference machine has neither Docker nor
PostgreSQL, so local development runs against **SQLite** by default. Everything is
Postgres-ready via `DATABASE_URL` (see [`docs/OPERATIONS.md`](docs/OPERATIONS.md)).

```bash
cp .env.example .env

make setup       # venv + backend deps + frontend deps
make migrate     # create ./chimera.db and apply all migrations
make seed        # load the synthetic week-1 baseline universe
make weekly      # run the full 14-stage weekly intelligence pipeline; prints the digest

# two terminals (or `make dev` to run both):
make api         # FastAPI backend  -> http://127.0.0.1:8000  (/docs for OpenAPI)
make web         # Next.js frontend -> http://localhost:3000
```

Then open <http://localhost:3000>:

- **Intelligence** — ranked people, sortable on every numeric column, filter by class.
- Click **Sarah Chen** → Founder Priority, weekly Δ, and Confidence (shown separately).
- Expand **Score decomposition** → `quality/fit/timing/access × weight = priority`.
- Click the `+14.0 employment departure` contribution → feature value → normalization
  rule → **Fact** → **Evidence** → **RawObservation** (the original source record).
- `fundraising_status` is displayed as **unknown** — never "likely fundraising".

## Testing & validation

```bash
make test              # unit + integration + api + acceptance
make test-acceptance   # spec scenarios §62-65 only
make lint              # ruff + mypy
make backtest          # point-in-time backtest of founder_v0.1
cd apps/web && npm run build && npm run test:e2e   # prod build + Playwright smoke
```

## Repository map

| Path | Contents |
|---|---|
| `intelligence/` | Backend package: models, ingestion, extraction, entity resolution, events, features, scoring, ranking, discovery, digest, jobs, API |
| `apps/web/` | Next.js analytical UI |
| `configs/` | Versioned model / thesis / discovery / action-rule configuration (YAML) |
| `db/migrations/` | Alembic migrations · `db/seeds/` synthetic fixtures |
| `evals/` | Golden datasets + extraction / entity-resolution / ranking evaluations |
| `tests/` | `unit/` `integration/` `api/` `acceptance/` |
| `docs/` | PRODUCT, ARCHITECTURE, DATA_MODEL, EVENT_TAXONOMY, SCORING, SOURCES, EVALUATION, SECURITY, OPERATIONS |
| `.claude/` | Engineering standards (`CLAUDE.md`), subagents, validation hooks |

## Non-negotiable engineering rules

Enforced by review, tests, and [`.claude/settings.json`](.claude/settings.json) hooks.
Full list in [`CLAUDE.md`](CLAUDE.md).

1. LLMs never produce a numerical quality/priority score. Scoring is deterministic config.
2. Facts and inferences are different objects. Inferences carry type, confidence, evidence, model version.
3. `unknown` is never collapsed into `null`, `0`, or `false`.
4. Every derived fact links to Evidence which links to an immutable RawObservation.
5. Model weights live in versioned YAML, never in Python source. No silent model changes.
6. Ambiguous identities are never auto-merged. Every merge is reversible.
7. No unauthorized scraping. Source adapters document their acquisition assumptions.
8. Sensitive/protected personal attributes are never inferred or used as features.
