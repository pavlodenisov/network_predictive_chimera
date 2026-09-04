# EVENT_TAXONOMY.md — version `events_v0.1`

Events are the normalized representation of "something changed". They are **not** free
natural language. `intelligence/events/taxonomy.py` is the machine copy of this file;
`tests/unit/test_event_taxonomy.py` asserts the two agree.

Each type documents: **Definition · Required evidence · Optional evidence · Confidence ·
Expiration · Scoring models**. Confidence is a deterministic function of evidence, never
an LLM output. `severity` ∈ {low, medium, high}.

Common confidence inputs:
- `R` = max source `reliability_tier` weight among evidence (tier1→1.0, t2→0.85, t3→0.7, t4→0.55, t5→0.35)
- `D` = directness (observed change on the subject's own record = 1.0; third-party report = 0.7)
- `I` = independent-source factor = `min(1, 0.6 + 0.2·distinct_domain_count)`
- `X` = extraction confidence (deterministic parse = 1.0; snapshot diff = 0.95; llm = model-reported)

Default `confidence = round(R · D · X · I_or_1, 2)` unless a row overrides it.

Expiration: `active` events may become `expired` after `ttl_days` for *timing* purposes
(the event row is kept forever; only its timing contribution decays — see `docs/SCORING.md`).

---

## Employment

| type | severity | definition | required evidence | confidence | ttl_days | models |
|---|---|---|---|---|---|---|
| `EMPLOYMENT_STARTED` | low | a new current employment appears | employment record OR profile snapshot with new current company | default | 365 | founder, talent, lp |
| `EMPLOYMENT_ENDED` | medium | a previously-current employment gains an end date or disappears from the current slot | prior snapshot with company X current + new snapshot without it, OR explicit "left" statement | default; snapshot-diff `X=0.95` | 240 | founder, talent |
| `TITLE_CHANGED` | low | normalized_title changes at same org | two snapshots / employment records | default | 180 | founder, talent, lp |
| `PROMOTION` | medium | title change that increases `seniority` rank at same org | as TITLE_CHANGED + seniority ladder step up | default | 240 | founder, lp, talent |
| `SENIORITY_INCREASED` | low | seniority rank up across a job change | employment history | default | 240 | talent, lp |
| `BOARD_ROLE_STARTED` | low | new board seat | board listing / announcement | default | 400 | founder, connector, lp |
| `ADVISOR_ROLE_STARTED` | low | new advisory role | profile / announcement | default·0.9 | 300 | connector |

## Founder

| type | severity | definition | required evidence | confidence | ttl_days | models |
|---|---|---|---|---|---|---|
| `FOUNDER_TITLE_ADDED` | high | person adds a founder/co-founder/"building" title | profile snapshot diff OR announcement | default; snapshot-diff `X=0.95` | 200 | founder |
| `COMPANY_FORMATION_CONFIRMED` | high | a company associated with the person is confirmed formed | registry / press / company site with founder name | default | 400 | founder |
| `POSSIBLE_COMPANY_FORMATION` | medium | **inference**, not fact — signals suggest formation | ≥1 of: EMPLOYMENT_ENDED recent + "building" headline + stealth language | `probability` = `0.35 + 0.2·(signals) ` capped 0.85 | 150 | founder |
| `STEALTH_COMPANY_SIGNAL` | medium | headline/text indicates stealth work | profile text / post | default·0.85 | 150 | founder |
| `COFOUNDER_SEARCH` | medium | person publicly seeking a cofounder | post / profile | default | 120 | founder |
| `PRODUCT_LAUNCH` | medium | a product tied to the person is launched | launch post / press / product site | default | 200 | founder |
| `COMPANY_WEBSITE_LAUNCHED` | low | company domain goes live | crawl / whois-style record | default·0.9 | 200 | founder |
| `FUNDRAISE_ANNOUNCED` | high | a round is publicly announced | press / filing / announcement | default | 300 | founder |
| `FUNDING_ROUND_CONFIRMED` | high | round confirmed by a tier1/2 source | database record / filing | `R·1.0` | 400 | founder |
| `ACCELERATOR_JOINED` | medium | cohort membership | program list / announcement | default | 300 | founder |
| `COMPANY_EXIT` | high | company the person founded/led exits | press / database | default | 3650 | founder |
| `COMPANY_ACQUIRED` | high | company acquired | press / database | default | 3650 | founder, talent |
| `HIRING_STARTED` | low | the person / their new company begins hiring | job posts / "we're hiring" language | default·0.8 | 120 | founder |
| `DOMAIN_ACTIVITY_SPIKE` | low | a marked increase in domain / project activity | repo or post cadence change | default·0.6 | 90 | founder |
| `HEADLINE_CHANGED` | low | profile headline text materially changed (see §50 materiality) | two profile snapshots | snapshot-diff `X=0.95` | 90 | founder, talent, lp |

## Research / technical

| type | severity | definition | required evidence | confidence | ttl_days | models |
|---|---|---|---|---|---|---|
| `PAPER_PUBLISHED` | low | new publication authored | index record (arXiv/DOI-style) | `R·1.0` | 730 | founder, talent |
| `PATENT_FILED` | low | patent application with person as inventor | patent record | `R·1.0` | 1460 | founder, talent |
| `OPEN_SOURCE_PROJECT_LAUNCHED` | low | notable new OSS repo | repo record with stars/commits threshold | default·0.9 | 365 | founder, talent |
| `TECHNICAL_PROJECT_LAUNCHED` | low | non-OSS technical project shipped | post / site | default·0.8 | 200 | founder |
| `RESEARCH_COMMERCIALIZATION_SIGNAL` | medium | researcher moving tech toward a company | lab→startup transition / spinout language | default·0.8 | 180 | founder |

## LP

| type | severity | definition | required evidence | confidence | ttl_days | models |
|---|---|---|---|---|---|---|
| `LP_ROLE_STARTED` | medium | person starts an allocator/LP-side role | employment at family_office/endowment/foundation/FoF | default | 400 | lp |
| `FAMILY_OFFICE_ROLE_STARTED` | medium | role at a family office | employment record + org type | default | 400 | lp |
| `CIO_ROLE_STARTED` | high | person becomes CIO / head of investments | title + org type | default | 500 | lp |
| `PARTNER_ROLE_STARTED` | high | promotion/hire into Partner at an allocator or fund | title change | default | 400 | lp |
| `INVESTMENT_MANDATE_CHANGED` | high | bio/mandate text adds venture / alternatives allocation responsibility | official bio diff / announcement | default; snapshot-diff `X=0.95` | 300 | lp |
| `VENTURE_ALLOCATION_SIGNAL` | medium | evidence org is allocating to VC / emerging managers | disclosed commitment / program page | default·0.9 | 365 | lp |
| `FUND_INVESTMENT_ACTIVITY` | medium | org made a fund commitment | database / disclosure | `R·1.0` | 365 | lp |
| `EMERGING_MANAGER_SIGNAL` | medium | org runs / joins an emerging-manager program | program page / announcement | default·0.9 | 365 | lp |
| `INVESTMENT_COMMITTEE_ROLE` | medium | person joins an IC | announcement / bio | default | 400 | lp |

## Talent

| type | severity | definition | required evidence | confidence | ttl_days | models |
|---|---|---|---|---|---|---|
| `PROFESSIONAL_DEPARTURE` | medium | person left a role (talent lens on EMPLOYMENT_ENDED) | as EMPLOYMENT_ENDED | default | 180 | talent |
| `OPEN_TO_WORK_SIGNAL` | medium | person **declares** availability | explicit profile flag / post | `R·D·1.0` (fact only if declared; never inferred from a departure) | 120 | talent |
| `NEW_EXECUTIVE_ROLE` | medium | person starts a C-level/VP role | employment record | default | 365 | talent |
| `FUNCTIONAL_LEADERSHIP_ROLE` | low | person starts a function-head role | employment record | default | 365 | talent |
| `PORTFOLIO_ROLE_MATCH_CREATED` | low | system created a candidate↔role match above threshold | `candidate_role_match` row | `= match confidence` | 90 | talent |

## Network

| type | severity | definition | required evidence | confidence | ttl_days | models |
|---|---|---|---|---|---|---|
| `NEW_CHIMERA_CONNECTION` | medium | a new relationship_edge between a Chimera person and the subject | edge record | `= edge.confidence` | 730 | access (all) |
| `RELATIONSHIP_STRENGTH_UPDATED` | low | edge strength label changed | two edge states | `= edge.confidence` | 365 | access (all) |
| `WARM_PATH_CREATED` | medium | a path Chimera→person appeared where none existed | path computation diff | `= min(edge confidences on path)` | 180 | access (all) |
| `WARM_PATH_LOST` | medium | previously-known path no longer exists | path computation diff | 0.9 | 180 | access (all) |

## General

| type | severity | definition | required evidence | confidence | ttl_days | models |
|---|---|---|---|---|---|---|
| `NEWS_MENTION` | low | person named in a news article | article observation + entity resolution ≥ POSSIBLE_MATCH | `R·D·I` | 120 | all (weak) |
| `AWARD` | low | named award/recognition | announcement | default | 400 | founder, talent |
| `CONFERENCE_APPEARANCE` | low | speaker/panelist listing | agenda / announcement | default·0.9 | 120 | connector |
| `PUBLIC_TALK` | low | recorded talk / keynote | listing | default·0.9 | 180 | connector |
| `MAJOR_COMPANY_MILESTONE` | low | milestone at the person's company (scale, users, revenue) — only if verified | tier1/2 figure | `R·1.0` | 240 | founder |

---

## Rules

- Events are created only by `events/detector.py` comparing new facts to historical state.
- `dedupe_key` (see `docs/DATA_MODEL.md`) makes creation idempotent; a materially changed
  re-detection sets `supersedes_event_id` and marks the old row `superseded`.
- `POSSIBLE_COMPANY_FORMATION` and any `*_SIGNAL` that represents interpretation are
  written to **`inference`**, not `event`, when they are not directly observed. Where the
  taxonomy lists them above it is to document their confidence math and TTL; the detector
  routes them to the correct table.
- Adding an event type requires: a row here, an entry in `taxonomy.py`, a detector branch,
  and a test. (CLAUDE.md rule 9.)
