# Chimera Network Intelligence — API image (FastAPI + weekly pipeline).
# Build context is the repo root.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    CHIMERA_LOG_FORMAT=json \
    CHIMERA_API_HOST=0.0.0.0

WORKDIR /app

# Dependencies first for layer caching. psycopg[binary] bundles libpq — no apt needed.
COPY requirements.txt pyproject.toml README.md ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt "psycopg[binary]>=3.2"

# Application code (see .dockerignore for exclusions).
COPY intelligence ./intelligence
COPY configs ./configs
COPY db ./db
COPY scripts ./scripts
COPY alembic.ini ./
RUN pip install -e . --no-deps

EXPOSE 8000

# Idempotent: migrate -> seed (no-ops if already seeded) -> one week-2 pipeline pass
# (only if fewer than 2 runs exist) -> uvicorn. See scripts/bootstrap_demo.py.
CMD ["python", "scripts/bootstrap_demo.py"]
