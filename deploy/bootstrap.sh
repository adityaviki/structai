#!/usr/bin/env bash
# One-shot bootstrap for a fresh Ubuntu 24.04 Lightsail instance, or for
# an existing one that already runs another app (e.g. the movies app).
# Idempotent — safe to re-run.
#
# Installs Python 3.12+, uv, Node 22, pnpm, Postgres 16, Redis, Caddy.

set -euo pipefail

if [[ $EUID -eq 0 ]]; then
  echo "Run as the 'ubuntu' user with sudo available, not as root."
  exit 1
fi

echo "==> apt update + base packages"
sudo apt-get update -y
sudo apt-get install -y curl ca-certificates gnupg lsb-release git ufw build-essential

echo "==> Python 3.12 (Ubuntu 24.04 ships 3.12 by default)"
sudo apt-get install -y python3 python3-venv python3-dev
python3 --version

echo "==> uv (Python package + project manager)"
if ! command -v uv >/dev/null 2>&1 && ! [ -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv --version

echo "==> Node.js 22 (Nodesource)"
if ! command -v node >/dev/null || ! node --version | grep -q '^v22\.'; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
node --version

echo "==> pnpm via corepack"
sudo corepack enable
corepack prepare pnpm@latest --activate

echo "==> Postgres 16"
if ! command -v psql >/dev/null; then
  sudo apt-get install -y postgresql postgresql-contrib
fi
sudo systemctl enable --now postgresql

echo "==> Redis"
if ! command -v redis-cli >/dev/null; then
  sudo apt-get install -y redis-server
fi
sudo systemctl enable --now redis-server

echo "==> Caddy (official repo)"
if ! command -v caddy >/dev/null; then
  sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y caddy
fi
sudo systemctl enable --now caddy

echo "==> UFW firewall (22 / 80 / 443)"
sudo ufw allow OpenSSH || true
sudo ufw allow 80/tcp  || true
sudo ufw allow 443/tcp || true
sudo ufw --force enable

echo "==> /var/lib/structai workspace for documents and run logs"
sudo mkdir -p /var/lib/structai
sudo chown -R ubuntu:ubuntu /var/lib/structai

echo
echo "Bootstrap complete."
echo "Next: bash deploy/provision-db.sh, then populate /etc/structai.env, then bash deploy/deploy.sh."
