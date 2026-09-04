# CLAUDE.md — Chimera Network Intelligence engineering standards

This is a **high-integrity analytical system**, not an AI product. Read
`docs/PRODUCT.md` and `docs/SCORING.md` before changing analytical code.

## The 15 rules (non-negotiable)

1. **Never introduce subjective AI-generated scoring.** LLMs extract and classify; they
   never output a founder/LP/talent/priority/quality number. Scoring is deterministic
   config in `configs/models/*.yaml`.
2. **Every new feature requires a definition and a test** — raw unit, source, normalization,
   missing behaviour, expected direction, weight, rationale, and a unit test (see the
   quant-researcher checklist).
3. **Every factual derived record requires evidence.** A `fact` with no `evidence` row is
   a bug. Evidence points at an immutable `raw_observation`.
4. **Never collapse `unknown` into `false` or `0`.** `missing`, `zero`, `false`, `unknown`
   are four states. Features carry `{value, status}`.
5. **Never silently change model weights.** A changed model config = a new `version` and a
   new `scoring_model` row. `config_hash` mismatch without a version bump fails the run.
6. **Never merge ambiguous identities automatically.** Auto-merge only above the high
   threshold with no competing candidate. Every merge is reversible via `entity_merge_log`.
7. **All schema changes require an Alembic migration.** No `Base.metadata.create_all` in
   app or job code (tests may use it on a throwaway SQLite).
8. **All score changes require tests** — normalization, decay, contribution, delta math.
9. **All new event types require taxonomy documentation** — a row in
   `docs/EVENT_TAXONOMY.md`, an entry in `intelligence/events/taxonomy.py`, a detector
   branch, and a test.
10. **All LLM outputs require validated structured Pydantic schemas.** Reject malformed
    output, retry once with validation feedback, then record an `extraction_run` failure.
    Never accept free-form labels.
11. **Never make LinkedIn scraping a hidden dependency.** Authorized snapshots/provider
    records only; adapters document their acquisition assumption.
12. **Prefer simple deterministic logic over unnecessary ML.** When choosing between a
    sophisticated opaque method and a simpler auditable one, choose auditable for V0
    (§68).
13. **Do not add a chatbot** or generic RAG chat unless explicitly requested.
14. **Do not add decorative AI UI** — no gradients, no animated "AI" visualizations, no
    hero section, no chat-first interface. Information density before decoration (§28).
15. **Optimize for analytical density and auditability.** Every UI element must help
    answer one of the §69 questions (who / what changed / when / what evidence / how much
    did it matter / why did the score move / how confident / how to reach them / what's
    missing / what to verify).

## Layering (see `docs/ARCHITECTURE.md`)

```
sources → ingestion → RawObservation(immutable) → extraction(ExtractionRun) →
Evidence → Fact → {Event | Inference} → EntityResolution → Feature(PersonFeatureSnapshot)
→ scoring(ScoreSnapshot) → ranking(deltas, universe) → digest / API / UI
```

Do not let a lower layer import an upper layer. Scoring never touches raw text. The UI
never computes a score — it renders `contribution_breakdown`.

## Conventions

- Python 3.11+ (verified on 3.14). `ruff` + `mypy` + `pytest` must pass (hooked).
- SQLAlchemy 2.0 typed models. Column types come from `intelligence/types.py` only
  (`GUID`, `JSONB`, `UTCDateTime`) — never raw dialect types elsewhere.
- All timestamps tz-aware UTC via `intelligence.observability.now_utc()`.
- Enums are `enum.StrEnum` subclasses in `intelligence/models/enums.py`, stored as strings.
- Config (weights, thresholds, decay constants) lives in `configs/`, loaded and validated
  at startup — never as literals in scoring code.
- Tests: `tests/unit` (pure functions, fast), `tests/integration` (`-m integration`,
  cross-layer), `tests/api`, `tests/acceptance` (`-m acceptance`, spec §62-65).
- Frontend: `apps/web`, Next.js App Router, TypeScript strict, Tailwind, TanStack
  Table/Query. Numbers in a monospace column. `eslint` + `tsc --noEmit` must pass.

## When you add or change analytical behaviour

1. Update the relevant `docs/*.md` first (the docs are the spec of record).
2. Update `configs/` if a weight/threshold/constant changes; bump the model `version`.
3. Add/adjust tests (rule 2, 8, 9).
4. Run `make lint test`. For extraction changes also run `python -m evals.run extraction`
   and compare to baseline (rule: "looks good" is not approval — the numbers must hold).

## Subagents (`.claude/agents/`)

`quant-researcher` (scoring/features/normalization/decay/backtesting) ·
`data-engineer` (schema/ingestion/provenance/temporal/dedup/entity-resolution) ·
`backend-engineer` (APIs/services/db/jobs/perf) ·
`frontend-engineer` (analytical UI/tables/drilldown) ·
`eval-engineer` (goldens/extraction+ranking eval/regression) ·
`reviewer` (read-only: hallucination risk, provenance violations, unknown handling,
model/future-data leakage, scoring bugs, duplicate events, insecure sources, subjective logic).
