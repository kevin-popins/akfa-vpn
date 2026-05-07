#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/akfa-vpn}"
BRANCH="${BRANCH:-main}"
RUN_BACKUP="${RUN_BACKUP:-yes}"

usage() {
  cat <<'USAGE'
Usage: update.sh [--help]

Safe update flow:
  1. run backup.sh
  2. git fetch/pull
  3. docker compose build backend frontend
  4. docker compose up -d
  5. run health checks

Environment overrides:
  INSTALL_DIR=/opt/akfa-vpn
  BRANCH=main
  RUN_BACKUP=yes|no
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

if [[ "$RUN_BACKUP" != "no" ]]; then
  "$INSTALL_DIR/scripts/backup.sh"
fi

git fetch --prune origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

docker compose build backend frontend
docker compose up -d

curl -fsS --connect-timeout 2 --max-time 10 http://127.0.0.1:8000/health
curl -fsSI --connect-timeout 2 --max-time 10 http://127.0.0.1:8080 >/dev/null

printf 'Update finished. Run scripts/doctor.sh for diagnostics.\n'
