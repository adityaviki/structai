# Deploying StructAI to Lightsail

Target: an Ubuntu 24.04 Lightsail instance — typically the **same box**
that already runs `movies.adityaviki.com` — serving
`https://structai.adityaviki.com`.

Architecture:
- **Caddy** on :80/:443 → terminates TLS, serves the built frontend, reverse-proxies `/api/*`
- **uvicorn** API on `127.0.0.1:8000` (systemd: `structai-api.service`)
- **arq** worker (systemd: `structai-worker.service`)
- **Postgres 16** on `127.0.0.1:5432` — role `structai` has CREATEDB; one DB per project plus `structai_meta`
- **Redis** on `127.0.0.1:6379` — arq queue + SSE pubsub
- Uploaded documents and per-run logs under `/var/lib/structai`

The bootstrap script is idempotent so it's safe to run on the box that
already hosts the movies app — Postgres/Caddy/Node already there will
be left alone; Python, uv, and Redis get added.

---

## 0. DNS (Namecheap)

In the Namecheap dashboard for `adityaviki.com`, add an `A` record:

```
Host:  structai
Type:  A
Value: <your Lightsail public IP>          # same IP that movies uses
TTL:   Automatic
```

Wait for it to resolve before continuing — Caddy will fail to issue a cert
otherwise:

```bash
dig +short structai.adityaviki.com
```

## 1. Ports

Already open from the movies setup (80, 443). Nothing to do.

## 2. SSH onto the box

```bash
ssh ubuntu@<your-lightsail-ip>
```

## 3. Clone the repo

```bash
git clone https://github.com/adityaviki/structai-v2.git
cd structai-v2
```

## 4. Bootstrap (installs Python/uv/Node/pnpm/Postgres/Redis/Caddy)

```bash
bash deploy/bootstrap.sh
```

Re-runnable. Skips anything that's already installed.

## 5. Provision the database role

```bash
bash deploy/provision-db.sh
```

It will print:

```
STRUCTAI_PG_URL=postgresql://structai:<hex-password>@127.0.0.1:5432/postgres
```

**Save the password.** Re-running this script will NOT regenerate it.

## 6. Populate the env file

```bash
sudo install -m 0640 -o root -g ubuntu \
  deploy/structai.env.example /etc/structai.env

sudo $EDITOR /etc/structai.env
```

Fill in:
- `STRUCTAI_PG_URL` — from step 5
- `STRUCTAI_ANTHROPIC_API_KEY` — from console.anthropic.com

## 7. Install systemd units

```bash
sudo cp deploy/systemd/structai-api.service    /etc/systemd/system/
sudo cp deploy/systemd/structai-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
```

## 8. Add the Caddy site

Open `/etc/caddy/Caddyfile` and append the contents of
`deploy/Caddyfile.snippet`:

```bash
sudo bash -c 'cat /home/ubuntu/structai-v2/deploy/Caddyfile.snippet >> /etc/caddy/Caddyfile'
sudo systemctl reload caddy
```

(The movies block stays untouched above it.)

## 9. First-time install + build + migrate

```bash
cd /home/ubuntu/structai-v2
bash deploy/deploy.sh
```

`deploy.sh` is what you'll re-run for every future deploy (it also handles
the first one). It installs both backends, runs the migrations, builds
the Vite frontend, and restarts the two services.

## 10. Start the services

```bash
sudo systemctl enable --now structai-api.service
sudo systemctl enable --now structai-worker.service
```

Visit `https://structai.adityaviki.com` — Caddy will request a cert from
Let's Encrypt on first request, and you're live.

---

## Updating after a code push

```bash
cd /home/ubuntu/structai-v2
bash deploy/deploy.sh
```

Pulls latest, runs `uv sync` + `pnpm install`, migrates, rebuilds the
frontend, restarts api + worker.

## Inspecting

```bash
sudo journalctl -u structai-api.service -f
sudo journalctl -u structai-worker.service -f
sudo journalctl -u caddy -n 200 --no-pager
```

Postgres / Redis health:

```bash
sudo -u postgres psql -c '\l' | grep structai
redis-cli ping
```

## Backups

- Postgres: standard `pg_dumpall` (or per-DB `pg_dump`) is enough.
- Workspace: `/var/lib/structai` holds uploaded documents and run logs;
  worth snapshotting if you care about historical uploads.

## Files at a glance

```
deploy/
├── README.md                        (this file)
├── bootstrap.sh                     step 4
├── provision-db.sh                  step 5
├── deploy.sh                        first install + every update (step 9)
├── Caddyfile.snippet                step 8
├── structai.env.example             step 6 (→ /etc/structai.env)
└── systemd/
    ├── structai-api.service         FastAPI / uvicorn
    └── structai-worker.service      arq worker
```
