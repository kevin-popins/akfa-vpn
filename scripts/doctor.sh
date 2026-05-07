#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/akfa-vpn}"
COMPOSE_FILE="${COMPOSE_FILE:-$INSTALL_DIR/docker-compose.yml}"
PROJECT_DIR="${PROJECT_DIR:-$INSTALL_DIR}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:8080}"

usage() {
  cat <<'USAGE'
Usage: doctor.sh [--help]

Shows AKFA runtime diagnostics:
  - docker compose ps
  - backend health
  - frontend status
  - nginx -t
  - disk space
  - backend watchdog status
  - recent backend/watchdog logs
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

section() {
  printf '\n== %s ==\n' "$1"
}

section "docker compose ps"
compose_cmd ps || true

section "backend health"
curl -fsS --connect-timeout 2 --max-time 5 "$HEALTH_URL" || true
printf '\n'

section "frontend status"
curl -fsSI --connect-timeout 2 --max-time 5 "$FRONTEND_URL" | sed -n '1,8p' || true

section "nginx config"
nginx -t || true

section "disk space"
df -h /

section "backend watchdog"
systemctl status akfa-backend-watchdog.timer --no-pager || true
/usr/local/bin/akfa-backend-watchdog status || true

section "backend logs"
compose_cmd logs --tail=120 backend || true
