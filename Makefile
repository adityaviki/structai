# StructAI — top-level task runner.
# All paths are repo-relative. Phase numbers refer to plans/plan.md §10.

.DEFAULT_GOAL := help
.PHONY: help install db-up db-down db-logs migrate revision \
        dev dev-api dev-worker dev-web \
        lint lint-py lint-ts format format-py format-ts \
        test test-py test-ts \
        openapi-gen clean

help: ## Show this help.
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Bootstrap ----------------------------------------------------------------

install: ## Install Python (uv) and JS (pnpm) deps.
	uv sync --group dev
	pnpm install

# --- Database -----------------------------------------------------------------

db-up: ## Start Postgres (docker-compose).
	docker compose up -d postgres

db-down: ## Stop Postgres.
	docker compose down

db-logs: ## Tail Postgres logs.
	docker compose logs -f postgres

migrate: ## Apply Alembic migrations.
	uv run alembic upgrade head

revision: ## Create a new Alembic migration. Usage: make revision NAME="add foo"
	@test -n "$(NAME)" || (echo "usage: make revision NAME=\"…\"" && exit 1)
	uv run alembic revision -m "$(NAME)"

# --- Dev servers --------------------------------------------------------------

dev-api: ## Run the API in watch mode.
	uv run uvicorn structai_api.main:app --reload --host 0.0.0.0 --port 8000

dev-worker: ## Run the worker in watch mode.
	uv run python -m structai_worker.main

dev-web: ## Run the web app in watch mode.
	pnpm --filter @structai/web dev

dev: db-up ## Run API + worker + web concurrently.
	pnpm exec concurrently \
		--names api,worker,web \
		--prefix-colors blue,green,magenta \
		"$(MAKE) dev-api" \
		"$(MAKE) dev-worker" \
		"$(MAKE) dev-web"

# --- Quality ------------------------------------------------------------------

lint: lint-py lint-ts ## Lint Python and TypeScript.

lint-py:
	uv run ruff check .

lint-ts:
	pnpm exec biome check apps/web packages

format: format-py format-ts ## Format Python and TypeScript.

format-py:
	uv run ruff format .

format-ts:
	pnpm exec biome format --write apps/web packages

test: test-py test-ts ## Run Python and TypeScript test suites.

test-py:
	uv run pytest -m "not eval"

test-ts:
	pnpm --recursive test

# --- OpenAPI ------------------------------------------------------------------

openapi-gen: ## Regenerate apps/web/src/api/schema.ts from the running API.
	pnpm exec openapi-typescript http://localhost:8000/openapi.json -o apps/web/src/api/schema.ts

# --- Misc ---------------------------------------------------------------------

clean: ## Remove caches and build artifacts.
	rm -rf .ruff_cache .pytest_cache .mypy_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name dist -prune -exec rm -rf {} +
