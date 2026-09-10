# DEPLOY_RENDER.md — one-click hosted demo

`render.yaml` is a **Blueprint** that stands up all three pieces from this repo in a single
deploy: the FastAPI **API**, a managed **Postgres** database, and the Next.js **web** UI.
No Supabase, no Vercel, no local Docker needed.

```
chimera-web (Next.js)  ──HTTP──►  chimera-api (FastAPI)  ──►  chimera-db (Postgres 16)
```

## Deploy

1. Push this repo to GitHub (already done).
2. Render dashboard → **New → Blueprint** → connect `pavlodenisov/network_predictive_chimera` → **Apply**.
   Render reads `render.yaml` and creates `chimera-db`, `chimera-api`, `chimera-web`.
3. First build of **chimera-api** runs `scripts/bootstrap_demo.py`:
   `alembic upgrade head` → `intelligence.jobs.seed` (111 synthetic people + week‑1 baseline)
   → one `intelligence.jobs.weekly --as-of 2026-09-06` pass → `uvicorn`. All idempotent, so
   restarts and redeploys don't duplicate data.
4. When **chimera-api** is live, copy its URL (`https://chimera-api-XXXX.onrender.com`),
   open **chimera-web → Environment**, set:
   `NEXT_PUBLIC_API_BASE_URL = https://chimera-api-XXXX.onrender.com`
   and trigger a redeploy of chimera-web (the value is inlined at build time).
5. Open the **chimera-web** URL. The red "backend not reachable" banner means the env var
   is missing/wrong or the API is still spinning up.

## What's wired for you

| Service | Env var | Source |
|---|---|---|
| chimera-api | `DATABASE_URL` | `fromDatabase` → normalized to `postgresql+psycopg://` in `intelligence/config.py` |
| chimera-api | `CHIMERA_CORS_ORIGINS` | `*` (demo). Tighten to the web URL for anything real. |
| chimera-api | `CHIMERA_EXTRACTOR` | `rules` (deterministic). Set `claude` + add `ANTHROPIC_API_KEY` to enable the LLM extractor. |
| chimera-web | `NEXT_PUBLIC_API_BASE_URL` | you paste it after step 3 (`sync: false`) |

## Free-tier caveats

- Web services **sleep after ~15 min idle**; first request after that is a 30–60s cold start.
- Free Postgres is **1 GB** and **expires 90 days** after creation. Back up or upgrade for anything lasting.
- To keep costs at zero, both web services use the `free` plan; bump to `starter` to remove the sleep.

## Refresh the demo data

Redeploys are safe (idempotent). To force a clean rebuild: in Render, open a **Shell** on
chimera-api and run `python -m intelligence.jobs.weekly --as-of <later-date>` for another
weekly cycle, or drop/recreate `chimera-db` and redeploy chimera-api.

## Alternatives

- **Railway** — same shape; use the Dockerfiles, add a Postgres plugin, set the same env vars.
- **Fly.io** — `fly launch` per service (`docker/api.Dockerfile`, `apps/web/Dockerfile`) + `fly postgres`.
- **Single VM** — `docker compose up --build` (see `docker-compose.yml`) behind a reverse proxy.
- **Vercel frontend + separate API** — see `docs/DEPLOY_VERCEL.md`.
