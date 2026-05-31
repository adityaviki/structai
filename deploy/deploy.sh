#!/usr/bin/env bash
# Pull latest, sync deps, migrate DB, build frontend, restart services.
# Run on every deploy. Re-runnable.

set -euo pipefail

REPO_DIR="${REPO_DIR:-/home/ubuntu/structai-v2}"
ENV_FILE="${ENV_FILE:-/etc/structai.env}"

cd "$REPO_DIR"

export PATH="$HOME/.local/bin:$PATH"

echo "==> git pull"
git fetch --quiet
git reset --hard origin/main

echo "==> uv sync (backend deps)"
( cd backend && uv sync --no-dev )

echo "==> pnpm install (frontend deps)"
( cd frontend && pnpm install --frozen-lockfile )

echo "==> migrate"
( cd backend && env $(grep -v '^#' "$ENV_FILE" | xargs) uv run structai migrate )

echo "==> build frontend"
( cd frontend && pnpm build )

echo "==> restart api + worker"
sudo systemctl restart structai-api.service
sudo systemctl restart structai-worker.service

echo "==> caddy reload (no-op if Caddyfile unchanged)"
sudo systemctl reload caddy.service || true

echo "==> done. API status:"
sudo systemctl --no-pager --lines=10 status structai-api.service || true
echo
echo "Worker status:"
sudo systemctl --no-pager --lines=10 status structai-worker.service || true
