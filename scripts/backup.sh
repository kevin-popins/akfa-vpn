#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/akfa-vpn}"
BACKUP_DIR="${BACKUP_DIR:-/opt/akfa-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
COMPOSE_FILE="${COMPOSE_FILE:-$INSTALL_DIR/docker-compose.yml}"
PROJECT_DIR="${PROJECT_DIR:-$INSTALL_DIR}"

usage() {
  cat <<'USAGE'
Usage: backup.sh [--help]

Creates a timestamped AKFA backup under BACKUP_DIR.
Backs up:
  - PostgreSQL dump from docker compose service postgres
  - .env
  - docker-compose.yml
  - deploy templates, if present

Environment overrides:
  INSTALL_DIR=/opt/akfa-vpn
  BACKUP_DIR=/opt/akfa-backups
  RETENTION_DAYS=14
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose --project-directory "$PROJECT_DIR" -f "$COMPOSE_FILE" "$@"
  else
    docker-compose --project-directory "$PROJECT_DIR" -f "$COMPOSE_FILE" "$@"
  fi
}

timestamp="$(date +%Y%m%d-%H%M%S)"
target="$BACKUP_DIR/akfa-vpn-$timestamp"
archive="$target.tar.gz"
mkdir -p "$target"

if [[ -f "$INSTALL_DIR/.env" ]]; then
  cp "$INSTALL_DIR/.env" "$target/env"
fi
if [[ -f "$COMPOSE_FILE" ]]; then
  cp "$COMPOSE_FILE" "$target/docker-compose.yml"
fi
if [[ -d "$INSTALL_DIR/deploy" ]]; then
  cp -a "$INSTALL_DIR/deploy" "$target/deploy"
fi

if compose_cmd ps postgres >/dev/null 2>&1; then
  compose_cmd exec -T postgres sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$target/postgres.sql"
else
  printf 'postgres service is not available; database dump skipped\n' > "$target/postgres.sql.skipped"
fi

tar -czf "$archive" -C "$BACKUP_DIR" "$(basename "$target")"
rm -rf "$target"

find "$BACKUP_DIR" -maxdepth 1 -name 'akfa-vpn-*.tar.gz' -type f -mtime +"$RETENTION_DAYS" -print -delete

printf 'Backup created: %s\n' "$archive"
