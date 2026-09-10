# TEAM_ROLLOUT.md

Two stages: **tonight** (a shareable first version on synthetic data) and **before real
data** (what has to be true before the firm's actual intelligence flows through it).

---

## Tonight — first version for the team

**Deploy:** follow `docs/DEPLOY_RENDER.md`. One Blueprint apply → three services → a
`https://chimera-web-xxxx.onrender.com` URL. ~3 min of clicks + ~10 min build.

**What the team gets:** the full analytical UI — Intelligence ranked feed, Person
drilldown with the score→feature→fact→evidence→observation chain, Events, Discovery, LP,
Talent, Models, Data Quality, Weekly Runs — running on **~113 synthetic people** with the
week-over-week delta story (Sarah Chen 27 → 52, §62–65 scenarios) already computed.

**Access tonight:** the `onrender.com` URL is unguessable but **unauthenticated**. That is
acceptable for this first version *only because the data is synthetic* — no real people,
no firm information. Send the link directly to the team; do not post it anywhere public.
Do **not** connect a real data source until SSO is in front (next section).

**Send to the team:**

> Chimera Network Intelligence — v0.1 preview: `<paste the chimera-web URL>`
> Ranked, decomposable intelligence on founders / LPs / talent / connectors. Running on
> synthetic seed data so you can see the shape of it. Try: open the Intelligence tab →
> sort by Priority → click a name → expand "Score decomposition" and follow it down to the
> source record. Feedback welcome; real data sources come next.
> Cold start: first load after a quiet period takes ~30–60s, then it's fast.

---

## Before real firm data flows through it

Ordered. Nothing real connects until 1–2 are done.

1. **SSO gate in front.** Don't build auth into the app for v1 — front the whole thing
   with Cloudflare Access / Google IAP / oauth2-proxy against the firm's IdP. It injects
   `X-User-Email`, which `intelligence/api/deps.py` already reads. Lock the services to
   accept traffic only from the gate. (Cloudflare Access: free ≤ 50 users.)
2. **Managed Postgres with backups + PITR**, and CI running the suite **against Postgres**
   (add a `postgres` service to `.github/workflows/ci.yml`; acceptance §62–65 green on PG
   is the gate). Reproducibility means `raw_observation` and the audit tables can never be
   lost.
3. **Real scheduler** for the weekly job on its own worker (Render Cron Job / cloud
   scheduler / the GitHub Actions workflow with prod secrets) + **failure alerting** on
   non-zero exit or `WeeklyRun.status in (failed, partial)`.
4. **Secrets** in the platform vault, not `.env`. Keep `CHIMERA_EXTRACTOR=rules` as default.
5. **Backups configured *and* one test restore.**
6. **Sentry** (API + web) + uptime check on `/health` + log drain for the JSON logs.
7. **Staging environment** — a second small instance + DB. Migrations and
   `configs/models/*.yaml` changes get exercised there first; the Models compare screen
   shows impact. Honors "no silent production model changes" (spec §5, §8).
8. **Data-handling note** reviewed by whoever owns compliance: what's stored, why,
   retention, deletion-on-request. The sensitive-attribute guardrail is already in
   `intelligence/features/base.py`.
9. **Connect ≥ 1 authorized source** (CRM export, licensed Crunchbase/PitchBook, an
   authorized LinkedIn snapshot feed, news RSS). Each adapter is a stub today; enabling
   one is the real product work. Until then the UI must clearly read "synthetic data".
10. **Users:** first cohort as `analyst`; a couple of GPs as `partner`.

**Rough infra cost, team ≈ 20, internal:** ~$75–160/month (2 always-on services + managed
Postgres w/ backups + Sentry/logs; SSO gate free). LLM extraction $0 unless enabled.
Data-source licensing (Crunchbase/PitchBook) is a separate firm decision.

**Long-term home:** once proven and someone owns infra, move into the firm's own cloud
(Cloud Run/ECS + Cloud SQL/RDS + their secrets manager) for data residency and their
existing security posture. Render/Railway-paid or a VM behind Cloudflare Access is the
right *starting* point, not the end state.
