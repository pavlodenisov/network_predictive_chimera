# SOURCES.md

The intelligence engine is source-independent. Every source implements one Protocol and
produces one normalized `RawObservation` schema; the pipeline downstream of ingestion is
identical regardless of provider (§5).

## 1. Adapter interface  (`intelligence/ingestion/adapters/base.py`)

```python
class SourceAdapter(Protocol):
    source_name: str
    def discover(self, *, rules: list[DiscoveryRule], as_of: date) -> list[RawObservationDraft]: ...
    def update_known_entities(self, *, people: list[PersonRef], as_of: date) -> list[RawObservationDraft]: ...
    def health_check(self) -> SourceHealth: ...
```

- `RawObservationDraft` = pre-persistence dataclass (provider_record_id, subject_hint,
  occurred_at, observed_at, source_url, content_type, raw_text, raw_json, metadata).
- `SourceHealth` = `{status: successful|partial|failed|disabled, records: int,
  latency_ms: int, last_successful_run, errors: list[str]}`.
- An adapter missing credentials returns `status=disabled` from `health_check` and empty
  lists from `discover`/`update_known_entities` — it never raises, never scrapes.

## 2. V0 adapters

| adapter | status | acquisition assumption | data |
|---|---|---|---|
| `SyntheticSource` | **working** | deterministic fixtures under `db/seeds/` | profiles, weekly snapshots, relationships, events — powers the demo |
| `ManualCSVSource` | **working** | analyst-provided CSV exports (`db/seeds/csv/*.csv` or `POST /imports`) | people, employments, relationships, events |
| `JSONSnapshotSource` | **working** | authorized professional-profile snapshots as JSON (one object per person per capture) | profile snapshots for diffing |
| `RSSNewsSource` | **working (offline default)** | public RSS/news feeds. Default reads `db/seeds/news/*.xml`; `CHIMERA_RSS_LIVE=1` + feed URLs enables live `httpx` fetch respecting each feed's terms | news articles → NEWS_MENTION, founder/LP/talent events |
| `LinkedInSnapshotSource` | **stub (disabled)** | **authorized** snapshots/provider records only — NEVER automated scraping (§5, §39). Expects the same JSON shape as `JSONSnapshotSource` plus provider IDs | — |
| `CRMSource` | stub (disabled) | firm CRM export/API with credentials | relationships, interaction history, feedback |
| `CrunchbaseSource` | stub (disabled) | licensed API key | company/funding/role records |
| `PitchBookSource` | stub (disabled) | licensed API + permitted access | company/fund/LP records |
| `GitHubSource` | stub (disabled) | public API token | repos, contribution activity → OSS features |

Stubs contain the full class, config schema, and `health_check` returning `disabled` with
the reason. Enabling one = supply config in `source.configuration` + credentials in env.

## 3. Normalization & dedup  (§4–5, §26)

1. `normalize.py` maps each draft to a `RawObservation` (immutable).
2. `dedupe.py` drops a draft whose `(source_id, provider_record_id)` or `content_hash`
   already exists.
3. News: near-duplicate syndicated articles are grouped into a `story_cluster`
   (`cluster_key` from normalized title + entities). Independent-source confidence uses
   `distinct_domain_count`, not article count — "15 copies of one press release" counts
   once.

## 4. Reliability tiers  (§55)

| tier | weight | examples |
|---|---|---|
| 1 | 1.00 | company/official site, government/registry filing, primary announcement |
| 2 | 0.85 | established database / reputable publication (Crunchbase, PitchBook, major press) |
| 3 | 0.70 | professional profile / self-reported |
| 4 | 0.55 | secondary reporting, aggregators |
| 5 | 0.35 | weak / unverified / anonymous |

Mapping is `source.reliability_tier` (configurable). Reliability affects
`evidence_strength` and `confidence_score`; it **never rewrites the observed fact**.

## 5. Conflicting data  (§56)

If source A says current employer = X and source B says = Y, the system does **not**
silently pick one. It:
1. stores both facts,
2. computes a provisional canonical `person.current_organization_id` using
   `recency > reliability_tier > directness`,
3. writes a `data_quality` conflict record surfaced on the Data Quality screen,
4. marks the losing fact `superseded_by_id` only when a later observation resolves it.

## 6. Freshness thresholds  (§27, `intelligence/features/freshness.py`)

| feature type | stale after | configurable key |
|---|---|---|
| current employment | 60 days | `freshness.current_employment` |
| network relationship | 365 days | `freshness.network_relationship` |
| company funding stage | 120 days | `freshness.company_stage` |
| profile headline | 45 days | `freshness.headline` |
| education | never | `freshness.education` |

Stale evidence is shown, not dropped; it lowers `recency` in `confidence_score` and can
trigger `DATA_STALE` reason codes / `VERIFY_DATA` actions.
