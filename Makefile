.PHONY: install install-backend install-frontend migrate dev dev-backend dev-worker dev-frontend test test-backend fmt lint clean

PYTHON ?= python3
UV ?= uv
PNPM ?= pnpm

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

install: install-backend install-frontend

install-backend:
	cd backend && $(UV) sync --all-extras

install-frontend:
	cd frontend && $(PNPM) install

# ---------------------------------------------------------------------------
# Migrate
# ---------------------------------------------------------------------------

migrate:
	cd backend && $(UV) run structai migrate

# ---------------------------------------------------------------------------
# Dev (three processes; run `make dev` and ctrl-c kills all of them)
# ---------------------------------------------------------------------------

dev:
	@trap 'kill 0' INT TERM EXIT; \
	$(MAKE) dev-backend & \
	$(MAKE) dev-worker & \
	$(MAKE) dev-frontend & \
	wait

dev-backend:
	cd backend && $(UV) run uvicorn structai.main:app --reload --host 127.0.0.1 --port 8000

dev-worker:
	cd backend && $(UV) run arq --watch src/structai structai.worker.main.WorkerSettings

dev-frontend:
	cd frontend && $(PNPM) dev

# ---------------------------------------------------------------------------
# Quality
# ---------------------------------------------------------------------------

test: test-backend

test-backend:
	cd backend && $(UV) run pytest

fmt:
	cd backend && $(UV) run ruff format src tests

lint:
	cd backend && $(UV) run ruff check src tests
	cd backend && $(UV) run mypy src

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

clean:
	rm -rf backend/.venv backend/.pytest_cache backend/.ruff_cache backend/.mypy_cache
	rm -rf frontend/node_modules frontend/dist
