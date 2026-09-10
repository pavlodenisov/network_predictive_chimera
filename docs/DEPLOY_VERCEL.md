# DEPLOY_VERCEL.md

> For the simplest hosted setup use **`docs/DEPLOY_RENDER.md`** — one Blueprint, no
> Vercel, no CORS. This file is the Vercel-specific path.

Vercel hosts the **frontend only** (`apps/web`, Next.js). The `intelligence/` FastAPI
backend + its database are a separate Python service. The Next.js server proxies
`/api/be/*` to the backend using the runtime env var **`API_BASE_URL`** (no CORS, no
build-time URL). So a working deployment is two pieces:

```
Vercel  ──►  apps/web  (Next.js)  ──HTTP──►  FastAPI + Postgres  (Railway / Render / Fly / a VM)
```

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

## 2. Deploy the frontend to Vercel

**Dashboard (no CLI needed):**
1. Vercel → **Add New → Project → Import** `pavlodenisov/network_predictive_chimera`.
2. **Root Directory:** `apps/web`  ← important, the repo is a monorepo.
3. Framework preset: **Next.js** (auto-detected; `apps/web/vercel.json` is committed).
4. **Environment Variables:**
   - `API_BASE_URL = https://<your-api-host>`   (the URL from step 1; a runtime var,
     read by the `/api/be/*` proxy route — not a `NEXT_PUBLIC_` build var)
5. Deploy. Every push to `main` redeploys. Changing `API_BASE_URL` needs only a
   redeploy, not a rebuild.

**CLI (if you have `vercel` + are logged in):**
```bash
cd apps/web
vercel link                     # once
vercel env add API_BASE_URL production   # paste the API URL
vercel --prod
```

## 3. Verify

- Open the Vercel URL. If the red banner "Backend not reachable" shows, the env var is
  missing/wrong or the API host is down.
- Add the exact Vercel domain to the API's `CHIMERA_CORS_ORIGINS` and redeploy the API,
  or browser requests are blocked by CORS.

## Single-platform alternative (advanced)

Vercel can also run the API as Python serverless functions: add `apps/web/api/index.py`
that imports `intelligence.api.app:app` (Mangum/ASGI adapter), set `DATABASE_URL` to a
Vercel Postgres / Neon instance, and run `alembic upgrade head` + `seed` as a one-off.
Cold starts and the lack of a long-running scheduler make the split above simpler for V0.
