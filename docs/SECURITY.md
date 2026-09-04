# SECURITY.md

This system handles professional and network data about real people. Compliance is a
design constraint, not a feature (§39).

## 1. Secrets

- All secrets from the environment / `.env` (git-ignored). `.env.example` documents every
  variable. No API keys, tokens, or credentials in the repository or in `source.configuration`
  committed to `db/seeds/`.
- `intelligence/config.py` (`pydantic-settings`) is the single read point. Nothing else
  reads `os.environ` directly.
- CI/scheduled runs receive secrets as masked environment variables (§47).

## 2. Data access & integrity

- All DB access via SQLAlchemy ORM / parameterized statements — no string-built SQL.
- Pydantic validates every API input and every LLM output. Unknown fields rejected.
- `raw_observation` is append-only (no UPDATE/DELETE path in code; enforced by repository
  layer + reviewed in migrations).
- Every mutation that changes a canonical belief writes an `analyst_override` or a
  superseding `fact`/`event` — originals are never destroyed (§31). Merges are reversible
  via `entity_merge_log` (§9).
- Audit trail: `weekly_run`, `extraction_run`, `analyst_override`, `entity_merge_log`,
  `analyst_feedback`, `entity_resolution_result` together reconstruct who/what/when.

## 3. Authentication abstraction

`intelligence/api/deps.py` exposes `get_current_user()` returning a `User(id, email,
roles)`. V0 implementation: a static dev principal from `CHIMERA_DEV_USER` (default
`analyst@chimera.local`). The rest of the code depends only on the abstraction, so a real
IdP (OIDC/SAML) drops in without touching routers. All write endpoints require an
authenticated principal; role checks (`analyst`, `partner`) are enforced in `deps.py`.

## 4. Acquisition / source terms

- **No unauthorized scraping.** `LinkedInSnapshotSource` and all provider stubs assume
  authorized snapshots / licensed APIs and are disabled until configured (`docs/SOURCES.md`).
- `RSSNewsSource` is offline by default; live fetch (`CHIMERA_RSS_LIVE=1`) honours each
  feed's terms and a polite delay.
- Each adapter's module docstring states its permitted-acquisition assumption.

## 5. Prohibited inferences  (§39)

The system MUST NOT infer, store, or use as a feature any of:

`race · ethnicity · religion · sexual orientation · health / disability · political
ideology · union membership · genetic / biometric data · gender identity · any other
protected or sensitive attribute`.

- Extraction schemas (`intelligence/schemas/extraction/`) have **no fields** for these and
  the rule extractor has no rules for them.
- `intelligence/features/registry.py` has a `FORBIDDEN_FEATURE_SUBSTRINGS` guard; feature
  builders raise if a feature name matches. `tests/unit/test_no_sensitive_features.py`
  enforces it across all model configs.
- Free-text `notes` fields are analyst-authored and out of scope for extraction.

## 6. PII handling

- `quoted_fragment` on `evidence` is stored only where permissibly retained; adapters set
  `metadata.quote_retention_ok`. When false, only a source URL + label is stored.
- No personal/sensitive data in URL query strings or logs. `observability.py` has a
  redaction filter for `email`, `linkedin_url`, and any key in `SENSITIVE_LOG_KEYS`.
- Personal data is not compiled across sources beyond what the stated product purpose
  (network intelligence for the firm) requires.

## 7. Threat notes for V0

- Prompt-injection via ingested text: LLM extraction is schema-bound, output-validated,
  and cannot trigger side effects (it only returns structured facts/events). The rule
  extractor is the default.
- The API is internal-only (bind `127.0.0.1`, CORS restricted to the dev web origin).
  Production deployment behind the firm's SSO/reverse proxy is a launch requirement
  (see `docs/OPERATIONS.md` risks).
