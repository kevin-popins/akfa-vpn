#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/akfa-vpn}"
BRANCH="${BRANCH:-main}"
RUN_BACKUP="${RUN_BACKUP:-yes}"
DOWNLOADS_DIR="${DOWNLOADS_DIR:-/opt/akfa-downloads}"
OVERWRITE_SEED_DOWNLOADS="${OVERWRITE_SEED_DOWNLOADS:-no}"

usage() {
  cat <<'USAGE'
Usage: update.sh [--help]

Safe update flow:
  1. run backup.sh
  2. git fetch/pull
  3. docker compose build backend frontend
  4. start postgres
  5. run alembic migrations once
  6. start backend/frontend
  7. run health checks

Environment overrides:
  INSTALL_DIR=/opt/akfa-vpn
  BRANCH=main
  RUN_BACKUP=yes|no
  OVERWRITE_SEED_DOWNLOADS=no|yes
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  printf 'ERROR: %s is not a git checkout.\n' "$INSTALL_DIR" >&2
  exit 1
fi

cd "$INSTALL_DIR"

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose --project-directory "$INSTALL_DIR" -f "$INSTALL_DIR/docker-compose.yml" "$@"
  else
    docker-compose --project-directory "$INSTALL_DIR" -f "$INSTALL_DIR/docker-compose.yml" "$@"
  fi
}

require_service_running() {
  local service="$1"
  if ! compose_cmd ps --status running --services | grep -qx "$service"; then
    compose_cmd ps
    printf 'ERROR: docker compose service %s is not running.\n' "$service" >&2
    exit 1
  fi
}

wait_for_postgres() {
  local i
  for ((i = 1; i <= 60; i++)); do
    if compose_cmd exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  compose_cmd logs --tail=120 postgres || true
  printf 'ERROR: PostgreSQL did not become ready.\n' >&2
  exit 1
}

sync_seed_downloads() {
  local manifest="$INSTALL_DIR/akfa-docs-platform/seed-downloads/downloads.manifest.json"
  if [[ ! -f "$manifest" ]]; then
    return 0
  fi
  if ! command -v node >/dev/null 2>&1; then
    printf 'WARNING: node is not available; seed downloads were not copied.\n' >&2
    return 0
  fi
  install -d "$DOWNLOADS_DIR"
  DOWNLOADS_DIR="$DOWNLOADS_DIR" OVERWRITE_SEED_DOWNLOADS="$OVERWRITE_SEED_DOWNLOADS" MANIFEST_PATH="$manifest" node <<'NODE'
const fs = require('node:fs');
const path = require('node:path');

const manifestPath = process.env.MANIFEST_PATH;
const downloadsDir = process.env.DOWNLOADS_DIR;
const overwrite = process.env.OVERWRITE_SEED_DOWNLOADS === 'yes';
const base = path.dirname(manifestPath);
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
fs.mkdirSync(downloadsDir, { recursive: true });

for (const item of manifest.downloads || []) {
  const sourceName = path.basename(item.source || '');
  const targetName = path.basename(item.filename || '');
  if (!sourceName || !targetName || sourceName !== item.source || targetName !== item.filename) {
    throw new Error(`Invalid manifest path for ${item.key || targetName}`);
  }
  const source = path.join(base, sourceName);
  const target = path.join(downloadsDir, targetName);
  if (!fs.existsSync(source)) {
    console.warn(`Seed download missing: ${sourceName}`);
    continue;
  }
  if (fs.existsSync(target) && !overwrite) {
    console.log(`Seed download exists, keeping: ${targetName}`);
    continue;
  }
  fs.copyFileSync(source, target);
  fs.chmodSync(target, 0o640);
  console.log(`Seed download copied: ${targetName}`);
}
NODE
  if id www-data >/dev/null 2>&1; then
    chown -R www-data:www-data "$DOWNLOADS_DIR"
    chmod 750 "$DOWNLOADS_DIR"
  fi
}

if [[ "$RUN_BACKUP" != "no" ]]; then
  "$INSTALL_DIR/scripts/backup.sh"
fi

git fetch --prune origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

sync_seed_downloads

compose_cmd build backend frontend
compose_cmd up -d postgres
require_service_running postgres
wait_for_postgres
compose_cmd run --rm --no-deps backend alembic upgrade head
compose_cmd up -d backend frontend
require_service_running backend
require_service_running frontend

curl -fsS --connect-timeout 2 --max-time 10 http://127.0.0.1:8000/health
curl -fsSI --connect-timeout 2 --max-time 10 http://127.0.0.1:8080 >/dev/null

printf 'Update finished. Run scripts/doctor.sh for diagnostics.\n'
