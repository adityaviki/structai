#!/usr/bin/env bash
# Create the postgres role for structai with CREATEDB privilege, plus the
# structai_meta database. Prints the STRUCTAI_PG_URL to use in /etc/structai.env.
#
# CREATEDB is required because the app creates one database per project
# at runtime (see D3 in PLAN.md). The role does NOT need superuser.
#
# Re-runnable: skips if role/db already exist.

set -euo pipefail

DB_USER="${DB_USER:-structai}"
DB_PASS="${DB_PASS:-$(openssl rand -hex 24)}"
META_DB="${META_DB:-structai_meta}"

echo "==> Creating role '$DB_USER' (if missing) with CREATEDB"
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
  echo "    role '$DB_USER' already exists; leaving password unchanged"
  ROLE_EXISTED=1
else
  sudo -u postgres psql -c "CREATE ROLE $DB_USER LOGIN CREATEDB PASSWORD '$DB_PASS';"
  ROLE_EXISTED=0
fi

echo "==> Creating database '$META_DB' (if missing)"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$META_DB'" | grep -q 1 \
  || sudo -u postgres createdb -O "$DB_USER" "$META_DB"

echo "==> Granting schema permissions on $META_DB"
sudo -u postgres psql -d "$META_DB" -c "GRANT ALL ON SCHEMA public TO $DB_USER;"
sudo -u postgres psql -d "$META_DB" -c "ALTER SCHEMA public OWNER TO $DB_USER;"

echo
echo "Done."
if [ "$ROLE_EXISTED" = "0" ]; then
  echo "Use this in /etc/structai.env:"
  echo
  echo "  STRUCTAI_PG_URL=postgresql://$DB_USER:$DB_PASS@127.0.0.1:5432/postgres"
  echo
  echo "Save the password somewhere — re-running this script will NOT overwrite it."
else
  echo "Role already existed. If you don't remember the password, reset it with:"
  echo "  sudo -u postgres psql -c \"ALTER ROLE $DB_USER WITH PASSWORD 'NEW-PASS';\""
fi
