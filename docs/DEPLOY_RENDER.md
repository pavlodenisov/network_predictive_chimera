# DEPLOY_RENDER.md — one-click hosted instance

`render.yaml` is a **Blueprint** that stands up all three pieces from this repo in a single
deploy: the FastAPI **API**, a managed **Postgres** database, and the Next.js **web** UI.
No Supabase, no Vercel, no local Docker.

```
chimera-web (Next.js)  ──HTTP──►  chimera-api (FastAPI)  ──►  chimera-db (Postgres 16)
```

## Deploy (≈3 minutes of clicks, then wait for the build)

1. Render dashboard → **New → Blueprint** → connect `pavlodenisov/network_predictive_chimera` → **Apply**.
   Render creates `chimera-db`, `chimera-api`, `chimera-web`. Leave `ANTHROPIC_API_KEY` blank.
2. **That's it — the API URL is auto-wired.** `chimera-web`'s `NEXT_PUBLIC_API_BASE_URL` is
   injected from `chimera-api`'s hostname via `fromService`; `apps/web/lib/api.ts` prepends
   `https://`. No manual env var, no second redeploy.
3. First build of **chimera-api** runs `scripts/bootstrap_demo.py`:
   `alembic upgrade head` → `intelligence.jobs.seed` (≈113 synthetic people + week-1 baseline)
   → one `intelligence.jobs.weekly --as-of 2026-09-06` pass → `uvicorn`. All idempotent.
4. When all three are green, open the **chimera-web** URL. Table populated, Sarah Chen near the top.

**If the first `chimera-web` build raced ahead of `chimera-api` and shows the "backend not
reachable" banner:** open `chimera-web` → **Manual Deploy → Deploy latest commit** once. The
`fromService` value resolves on the retry.

**If `chimera-api`'s first deploy fails its health check** (seed + weekly can be slow on the
free instance): **Manual Deploy → Deploy latest commit** again — seed is a no-op the second
time, so it comes up fast.

## Free-tier reality

| | |
|---|---|
| Web services | Sleep after ~15 min idle; first hit after that is a 30–60s cold start. 750 hrs/mo each — idle sleep keeps you well under. |
| Render Postgres | **Deleted ~30 days after creation** unless upgraded (~$7/mo). Use Neon (below) for indefinitely-free. |
| Weekly refresh | Does not run itself on free tier. The on-boot pass gives immediate data; for a recurring cycle use the GitHub Actions workflow (below) or a Render Cron Job. |

## Indefinitely-free database: swap Render Postgres → Neon

1. neon.tech → new project (free) → copy the connection string
   (`postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`).
2. In `render.yaml`, delete the `databases:` block and change `chimera-api`'s `DATABASE_URL`
   from `fromDatabase` to `sync: false`; commit.
3. Re-apply the Blueprint (or edit the env var in the dashboard) and paste the Neon string.
   `intelligence/config.py` rewrites `postgres://`/`postgresql://` → `postgresql+psycopg://`
   automatically.

## Recurring weekly pipeline (free)

`.github/workflows/weekly.yml` already runs the identical entrypoint on a schedule
(Mondays 13:17 UTC) and on demand. Enable it:

1. Repo → **Settings → Secrets and variables → Actions** → add `DATABASE_URL` = the same
   connection string the API uses (Neon or Render). Optionally `ANTHROPIC_API_KEY`.
2. It now runs weekly and uploads the digest as a workflow artifact. Trigger a manual run
   from the **Actions** tab (`weekly-intelligence` → Run workflow) any time.

## Alternatives

- **Railway / Fly.io** — same Dockerfiles; add Postgres, set the same env vars.
- **Single VM** — `docker compose up --build` behind a reverse proxy.
- **Team production** (SSO, always-on, backups, staging) — see `docs/TEAM_ROLLOUT.md`.
