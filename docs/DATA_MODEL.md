# DATA_MODEL.md

PostgreSQL-first, SQLite-compatible (see `docs/ARCHITECTURE.md` §4). All PKs are `GUID`
(uuid4 unless noted). All timestamps are `UTCDateTime` (tz-aware UTC). All JSON columns
are `JSONB`. Alembic owns the schema; no `create_all` in production.

Legend: **PK** primary key · **FK** foreign key · *idx* indexed · `enum` = string-backed
Python `enum.StrEnum` validated at the app layer (portable across dialects).

---

## Identity & profile

### person
| column | type | notes |
|---|---|---|
| id | GUID PK | |
| canonical_name | text *idx* | display name; never AI-generated |
| first_name / last_name | text null | |
| primary_location | text null | free text (e.g. "San Francisco, CA") |
| primary_email | text null *idx* | only if legitimately available |
| primary_linkedin_url | text null *idx* | canonicalized (lowercase, no query) |
| current_title | text null | provisional canonical state |
| current_organization_id | GUID FK→organization null | |
| classes | — | via `person_classification` (M2M) |
| monitoring_status | enum | DISCOVERED, REVIEW, ACTIVE_MONITORING, PASSIVE_MONITORING, ARCHIVED, DISMISSED |
| entity_resolution_status | enum | UNRESOLVED, RESOLVED, NEEDS_REVIEW, MERGED |
| merged_into_id | GUID FK→person null | set when this row was merged away (reversible) |
| notes | text null | analyst free text only |
| pinned | bool default false | analyst pin (§31) |
| first_seen_at / last_observed_at | UTCDateTime null | |
| created_at / updated_at | UTCDateTime | |

### person_classification  (M2M, §4)
`id PK · person_id FK *idx* · person_class enum · source enum · confidence float null ·
assigned_by text null · assigned_at · rationale_code text null` — unique(person_id, person_class).

### person_alias
`id PK · person_id FK *idx* · alias_type enum {NAME, LINKEDIN_URL, GITHUB_USERNAME,
PROVIDER_ID, EMAIL, OTHER} · alias_value text *idx* · source_id FK→source null ·
confidence float null · created_at`.

### organization
`id PK · canonical_name text *idx* · organization_type enum {startup, public_company,
private_company, fund, family_office, university, research_lab, portfolio_company, other}
· domain text null *idx* · location text null · founding_date date null · aum_usd numeric
null (LP model; only from disclosed figures) · attributes JSONB · created_at · updated_at`.

### employment
`id PK · person_id FK *idx* · organization_id FK *idx* · title text · normalized_title
text null · function enum null {engineering, research, product, design, sales, marketing,
operations, finance, legal, executive, investing, other} · seniority enum null {ic,
senior_ic, manager, director, vp, svp, c_level, founder, partner, board, advisor} ·
started_at date null · ended_at date null · current bool · evidence_ids JSONB (list) ·
confidence float null · created_at · updated_at`. *idx*(person_id, current).

### education
`id PK · person_id FK *idx* · institution_id FK→organization null · institution_name_raw
text null · degree text null · field text null · start_date date null · end_date date
null · evidence_ids JSONB`. No implicit prestige score (§11).

---

## Provenance layer

### source
`id PK · source_type enum {professional_profile, professional_activity, news, rss, crm,
manual_csv, json_snapshot, company_web, github, patents, academic, enrichment,
crunchbase, pitchbook, synthetic} · provider text · name text · enabled bool ·
reliability_tier smallint (1=best … 5=weak, §55) · configuration JSONB ·
last_successful_run UTCDateTime null · created_at`.

### raw_observation   *(immutable — never UPDATE/DELETE)*
`id PK · source_id FK *idx* · provider_record_id text null *idx* · subject_hint text null
· occurred_at UTCDateTime null · observed_at UTCDateTime · ingested_at UTCDateTime ·
processed_at UTCDateTime null · source_url text null · content_type enum
{profile_snapshot, activity_post, news_article, csv_row, json_record, patent, paper,
repo, manual_note} · raw_text text null · raw_json JSONB null · content_hash text *idx
unique-ish* · story_cluster_id GUID FK→story_cluster null · metadata JSONB`.
Dedup key: `(source_id, provider_record_id)` or `content_hash`.

### story_cluster   (§26 — syndicated-news de-duplication)
`id PK · cluster_key text *idx* · canonical_url text null · first_seen_at · article_count
int · distinct_domain_count int` — independent-source confidence uses
`distinct_domain_count`, not `article_count`.

### evidence
`id PK · fact_id FK→fact null *idx* · observation_id FK→raw_observation *idx* · source_url
text null · source_label text · quoted_fragment text null (only where permissibly stored)
· observed_at UTCDateTime null · evidence_strength float (0–1; derived from source
reliability_tier + directness) · created_at`.

### fact
`id PK · subject_type enum {person, organization, employment, relationship} · subject_id
GUID *idx* · fact_type text *idx* (see catalogue below) · structured_value JSONB
({"value":…, "unit":…} or {"status":"unknown"}) · valid_from UTCDateTime null · valid_to
UTCDateTime null · extraction_method enum {deterministic_parse, snapshot_diff, llm,
manual, import} · extraction_confidence float null · extractor_version text ·
superseded_by_id GUID FK→fact null · created_at`. Always ≥1 `evidence` row.

**Fact type catalogue (V0):** `EMPLOYMENT_STARTED_AT`, `EMPLOYMENT_ENDED_AT`,
`CURRENT_TITLE`, `HEADLINE_TEXT`, `HEADLINE_CHANGED`, `PRIOR_EXIT`, `PRIOR_FOUNDER`,
`COMPANIES_FOUNDED_COUNT`, `INSTITUTIONAL_FUNDRAISE`, `PRODUCT_SHIPPED`,
`YEARS_DOMAIN_EXPERIENCE`, `YEARS_ENGINEERING_EXPERIENCE`, `PATENT_COUNT`,
`PUBLICATION_COUNT`, `OSS_PROJECT_MAJOR`, `EARLY_EMPLOYEE_RANK`, `PROMOTION_COUNT`,
`TEAM_SIZE_MANAGED`, `BUDGET_OWNERSHIP`, `BOARD_ROLE`, `ADVISOR_ROLE`, `LOCATION`,
`DECISION_AUTHORITY_ROLE`, `ORG_TYPE_ALLOCATOR`, `VENTURE_ALLOCATION_EVIDENCE`,
`EMERGING_MANAGER_EVIDENCE`, `INVESTMENT_MANDATE`, `FUNDRAISING_STATUS` (value may be
`{"status":"unknown"}`), `OPEN_TO_WORK_DECLARED`, `GITHUB_IDENTITY`, `EDUCATION_INSTITUTION`.

### inference   *(never presented as fact)*
`id PK · person_id FK *idx* · inference_type text *idx* (from event taxonomy "possible/
signal" set) · probability float · model_version text · evidence_ids JSONB · explanation_code
text · created_at · expires_at UTCDateTime null`.

---

## Events

### event
`id PK · person_id FK *idx* · organization_id FK null · event_type text *idx* (see
`docs/EVENT_TAXONOMY.md`) · occurred_at UTCDateTime null · detected_at UTCDateTime ·
confidence float · severity enum {low, medium, high} · evidence_ids JSONB ·
structured_payload JSONB · supersedes_event_id GUID FK→event null · dedupe_key text *idx*
· status enum {active, superseded, retracted, expired} · created_at`.
`dedupe_key = sha1(person_id | event_type | occurred_at | sorted(evidence_ids))` → idempotency.

---

## Network

### relationship_edge
`id PK · source_person_id GUID *idx* · target_person_id GUID *idx* · relationship_type
enum {chimera_team, colleague, coworker_past, coinvestor, school, founder_investor,
introduced_by, personal, unknown} · relationship_strength enum {UNKNOWN, WEAK, MODERATE,
STRONG, DIRECT} · strength_numeric float null (only if data supports it — else null, not 0)
· confidence float null · source enum · first_seen_at null · last_verified_at null ·
evidence_ids JSONB · created_at · updated_at`. *idx*(source_person_id, target_person_id).
A person is "Chimera" if they have a `chimera_team` self/edge flag → `person.is_chimera_seed`
(bool, set from seed).

---

## Discovery

### discovery_rule
`id PK · name text · active bool · target_class enum · industries JSONB · technical_topics
JSONB · titles JSONB · prior_employers JSONB · geographies JSONB · keywords JSONB ·
excluded_keywords JSONB · source_ids JSONB · lookback_days int · minimum_evidence
JSONB ({"min_signals":1, "require_event_types":[…]}) · created_by text · created_at · updated_at`.

### discovery_candidate
`id PK · discovery_rule_id FK *idx* · person_id GUID FK→person null (staging person) ·
first_discovered_at · source_id FK · triggering_evidence_ids JSONB · identity_confidence
float · candidate_classification enum · promoted_to_person_id GUID null · promoted_at null
· dismissed bool · dismissed_reason text null · false_positive bool default false ·
score float null · score_breakdown JSONB null`.

---

## Features & scoring

### person_feature_snapshot
`id PK · person_id FK *idx* · model_target enum {founder, lp, talent, connector} ·
feature_set_version text · calculated_at UTCDateTime *idx* · as_of_date date · features
JSONB ({name:{value,status,raw_unit,source_fact_ids}}) · missing_features JSONB (list) ·
data_freshness JSONB ({feature:{verified_at, age_days, stale:bool}}) · created_at`.

### scoring_model
`id PK · name text *idx* · version text · target_class enum · configuration JSONB (the
parsed YAML) · config_hash text · status enum {draft, active, retired} · created_at ·
activated_at null · retired_at null` — unique(name, version).

### score_snapshot
`id PK · person_id FK *idx* · scoring_model_id FK *idx* · feature_snapshot_id FK ·
weekly_run_id FK→weekly_run null · scored_at UTCDateTime *idx* · as_of_date date ·
quality_score / fit_score / timing_score / access_score float null · priority_score float
· confidence_score float · rank int null · rank_universe_id GUID FK→ranking_universe null
· previous_score_snapshot_id GUID null · contribution_breakdown JSONB · delta_breakdown
JSONB null · action enum null · reason_codes JSONB · created_at`.
*idx*(person_id, scoring_model_id, scored_at).

### ranking_universe   (§54)
`id PK · label text · model_target enum · scoring_model_id FK · filter JSONB · as_of_date
date · member_count int · created_at`.

---

## Talent matching

### portfolio_company   (a specialised organization view; may just be organization rows)
### portfolio_role_need
`id PK · portfolio_company_id GUID FK→organization *idx* · role_title text · function enum
· seniority enum · domain_requirements JSONB · stage_requirements JSONB ·
location_requirements JSONB · status enum {open, filled, paused} · created_at · updated_at`.

### candidate_role_match
`id PK · person_id FK *idx* · portfolio_role_need_id FK *idx* · model_version text ·
calculated_at · score float · score_breakdown JSONB` — unique(person_id, role_need_id, model_version).

---

## Runs, feedback, overrides, observability

### weekly_run
`id PK · started_at · finished_at null · as_of_date date · status enum {running, success,
partial, failed} · source_coverage JSONB ([{source, status, records, latency_ms,
last_success}]) · observations_ingested int · people_updated int · people_discovered int
· facts_created int · events_created int · inferences_created int · scoring_models_run
JSONB · stage_stats JSONB · errors JSONB · warnings JSONB · code_version text ·
config_version text · digest JSONB null`.

### extraction_run   (§23)
`id PK · observation_id FK *idx* · extractor_name text · prompt_version text ·
model_version text · input_observation_ids JSONB · output JSONB null · parse_status enum
{ok, invalid_retried_ok, failed} · error text null · latency_ms int · token_usage JSONB
null · created_at`.

### analyst_feedback   (§7, §32)
`id PK · person_id FK *idx* · user_id text · score_snapshot_id FK null · feedback_type
enum {CONTACT_NOW, CONSIDER, PASS, FALSE_POSITIVE, INCORRECT_EVENT, INCORRECT_IDENTITY,
IMPORTANT_PERSON, NOT_RELEVANT, INTRO_REQUESTED, CONTACTED, MEETING_BOOKED, INVESTED,
HIRED, LP_CONVERSATION, LP_COMMITMENT, VIEWED, SAVED} · feedback_value JSONB null ·
reason_code text null · notes text null · created_at`.

### analyst_override   (§31 — never destroys originals)
`id PK · target_type enum {event, employment, classification, relationship, entity_merge,
entity_unmerge, source_state, person_pin, manual_evidence} · target_id GUID null ·
person_id GUID null *idx* · original_value JSONB null · override_value JSONB null ·
analyst_user_id text · reason text · created_at · reverted_at null`.

### entity_resolution_result   (§9)
`id PK · candidate_observation_id GUID null · candidate_person_id GUID null · matched_person_id
GUID null · decision enum {MATCH, POSSIBLE_MATCH, NO_MATCH, AMBIGUOUS} · score float ·
scorecard JSONB · competing_person_ids JSONB · auto_applied bool · reviewed bool ·
reviewer_user_id text null · created_at`.

### entity_merge_log   (reversible)
`id PK · winner_person_id GUID *idx* · loser_person_id GUID *idx* · decision_source enum
{auto, analyst} · resolution_result_id FK null · merged_fields JSONB (snapshot of loser
for restore) · analyst_user_id text null · reason text null · active bool · created_at ·
reverted_at null`.

### thesis_configuration   (§12, §60 — sample, clearly labelled)
`id PK · name text · version text · is_sample bool · sectors JSONB · technologies JSONB ·
business_models JSONB · stages JSONB · geographies JSONB · technical_topics JSONB ·
embedding_model text null · notes text · created_at` — unique(name, version).

### action_rule_set   (§57)
`id PK · name text · version text · rules JSONB (ordered list of {when:{…}, then:action,
reason_codes:[…]}) · status enum {draft, active, retired} · created_at`.

---

## Indexes (§52)

`person(canonical_name)`, `person(primary_linkedin_url)`, `person_alias(alias_value)`,
`raw_observation(content_hash)`, `raw_observation(source_id, provider_record_id)`,
`fact(subject_type, subject_id, fact_type)`, `event(person_id, occurred_at)`,
`event(dedupe_key)`, `score_snapshot(person_id, scoring_model_id, scored_at)`,
`relationship_edge(source_person_id)`, `relationship_edge(target_person_id)`,
`person_feature_snapshot(person_id, calculated_at)`, `weekly_run(started_at)`,
`organization(canonical_name)`, `organization(domain)`.
