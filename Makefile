# Chimera Network Intelligence — task runner.
# One command to start the app: `make setup && make migrate && make seed && make dev`

PY := ./.venv/bin/python
PIP := ./.venv/bin/pip
VENV := .venv
WEB := apps/web

.DEFAULT_GOAL := help
.PHONY: help setup venv deps web-deps migrate revision seed weekly digest backtest \
        api dev web test test-unit test-integration test-acceptance test-api \
        lint fmt typecheck e2e clean reset check

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: venv deps web-deps  ## Create venv, install backend + frontend deps

venv:
	test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install --upgrade pip setuptools wheel

deps:  ## Install/upgrade Python dependencies (editable install of `intelligence`)
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

web-deps:  ## Install frontend dependencies
	cd $(WEB) && npm install

migrate:  ## Apply DB migrations (alembic upgrade head)
	$(PY) -m alembic upgrade head

revision:  ## Create a new migration:  make revision m="add x"
	$(PY) -m alembic revision --autogenerate -m "$(m)"

seed:  ## Load synthetic week-1 baseline (people, orgs, relationships, baseline scores)
	$(PY) -m intelligence.jobs.seed

# For the synthetic demo the week-2 fixtures are dated 2026-09-06; a real deployment runs
# with no --as-of (defaults to today). Override:  make weekly WEEKLY_AS_OF=2026-10-01
WEEKLY_AS_OF ?= 2026-09-06

weekly:  ## Run the full 14-stage weekly intelligence pipeline (demo: as of 2026-09-06)
	$(PY) -m intelligence.jobs.weekly --as-of $(WEEKLY_AS_OF)

digest:  ## Print the most recent weekly digest
	$(PY) -m intelligence.jobs.weekly --digest-only

backtest:  ## Backtest a model:  make backtest model=founder_v0.1 from=2026-01-01 to=2026-08-01
	$(PY) -m intelligence.backtest --model $(or $(model),founder_v0.1) --from $(or $(from),2026-01-01) --to $(or $(to),2026-08-01)

api:  ## Run the FastAPI backend (http://127.0.0.1:8000)
	$(PY) -m uvicorn intelligence.api.app:app --reload --host 127.0.0.1 --port 8000

web:  ## Run the Next.js frontend (http://localhost:3000)
	cd $(WEB) && npm run dev

dev:  ## Run API + web together
	@echo "Starting API on :8000 and web on :3000 — Ctrl-C stops both"
	@$(MAKE) -j2 api web

test: test-unit test-integration test-api test-acceptance  ## Run the full test suite

test-unit:
	$(PY) -m pytest tests/unit

test-integration:
	$(PY) -m pytest tests/integration -m integration

test-acceptance:  ## Run spec acceptance scenarios §62-65
	$(PY) -m pytest tests/acceptance -m acceptance -v

test-api:
	$(PY) -m pytest tests/api

lint:  ## ruff + mypy
	$(PY) -m ruff check intelligence tests evals
	$(PY) -m mypy

fmt:  ## Auto-format (ruff)
	$(PY) -m ruff format intelligence tests evals
	$(PY) -m ruff check --fix intelligence tests evals

typecheck:
	$(PY) -m mypy

e2e:  ## Playwright smoke flow (requires `make api` + `make web` running, or CI webServer)
	cd $(WEB) && npm run test:e2e

evals:  ## Run extraction + entity-resolution + ranking evaluations
	$(PY) -m evals.run

check: lint test  ## Everything CI runs

reset:  ## Delete local DB and re-migrate + re-seed
	rm -f chimera.db
	$(MAKE) migrate
	$(MAKE) seed

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
