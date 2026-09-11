# DEPLOY_VERCEL.md

> For the simplest hosted setup use **`docs/DEPLOY_RENDER.md`** — one Blueprint, no
> Vercel. This file is the Vercel-specific path.

There are **two frontends** in this repo, both deployable to Vercel the same way:

| App | Audience | Screens |
|---|---|---|
| `apps/web` | Analysts | The dense terminal — full evidence trees, model config, data quality, weekly runs |
| `apps/team` | Everyone else | Plain-language "who to talk to and why" — same data, simpler surface, one click through to the full evidence |

Vercel hosts the **frontend only**. The `intelligence/` FastAPI backend + its database are
a separate Python service. Each Next.js app proxies `/api/be/*` to that backend using the
runtime env var **`API_BASE_URL`** (no CORS, no build-time URL — see
`app/api/be/[...path]/route.ts` in either app). So a working deployment is two pieces:

```
Vercel  ──►  apps/web  or  apps/team  (Next.js)  ──HTTP──►  FastAPI + Postgres  (Render / Railway / Fly)
```

Deploy both from the same repo as two separate Vercel projects with different **Root
Directory** settings, pointed at the same API.

## 1. Deploy the API first (pick one)

You need a public HTTPS URL for the API and a Postgres database.

**Railway / Render (dashboard, from this same repo):**
1. New service → deploy from GitHub → `pavlodenisov/network_predictive_chimera`.
2. Add a Postgres plugin/instance; it provides a connection string.
3. Environment:
   - `DATABASE_URL=postgres://…`  (config.py rewrites it to `postgresql+psycopg://`)
   - optional: `ANTHROPIC_API_KEY` + `CHIMERA_EXTRACTOR=claude`
   - CORS is not needed — the browser only talks to the Vercel proxy, not the API directly.
4. Install + start:
   ```
   pip install -r requirements.txt && pip install -e '.[postgres]'
   python -m alembic upgrade head
   python -m intelligence.jobs.seed        # one-off: synthetic universe + baseline scores
   python -m uvicorn intelligence.api.app:app --host 0.0.0.0 --port $PORT
   ```
5. Run the pipeline once so there's data to show: `python -m intelligence.jobs.weekly --as-of 2026-09-06`
   (schedule it with the platform's cron for real cadence — it calls the same entrypoint).

**Docker:** `docker compose up` builds `docker/api.Dockerfile` + Postgres + web; point a
reverse proxy / platform at the `api` service on `:8000`.

## 2. Deploy a frontend to Vercel

**Dashboard (no CLI needed) — repeat once per app:**
1. Vercel → **Add New → Project → Import** `pavlodenisov/network_predictive_chimera`.
2. **Root Directory:** `apps/team` for the friendly team view, or `apps/web` for the
   analyst terminal ← important, the repo is a monorepo.
3. Framework preset: **Next.js** (auto-detected; `vercel.json` is committed in both apps).
4. **Environment Variables:**
   - `API_BASE_URL = https://<your-api-host>`   (the URL from step 1; a runtime var,
     read by the `/api/be/*` proxy route — not a `NEXT_PUBLIC_` build var)
5. Deploy. Every push to `main` redeploys. Changing `API_BASE_URL` needs only a
   redeploy, not a rebuild. Give the second app its own Vercel project (don't reuse the
   first project for both Root Directories).

**CLI (if you have `vercel` + are logged in):**
```bash
cd apps/team   # or apps/web
vercel link                     # once
vercel env add API_BASE_URL production   # paste the API URL
vercel --prod
```

## 3. Verify

Open the Vercel URL. If the banner "Can't reach the data source" / "Backend not
reachable" shows, `API_BASE_URL` is missing/wrong or the API host is asleep/down — no
CORS setup is needed since the browser only ever talks to the Vercel proxy, never the
API directly.

## Single-platform alternative (advanced)

Vercel can also run the API as Python serverless functions: add `apps/web/api/index.py`
that imports `intelligence.api.app:app` (Mangum/ASGI adapter), set `DATABASE_URL` to a
Vercel Postgres / Neon instance, and run `alembic upgrade head` + `seed` as a one-off.
Cold starts and the lack of a long-running scheduler make the split above simpler for V0.
