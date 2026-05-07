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

env_value() {
  local file="$1"
  local key="$2"
  if [[ -f "$file" ]]; then
    awk -F= -v key="$key" '$1 == key { value = substr($0, index($0, "=") + 1); gsub(/^'\''|'\''$/, "", value); print value; exit }' "$file"
  fi
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

section "admin credentials"
main_admin_email="$(env_value "$INSTALL_DIR/.env" "ADMIN_EMAIL")"
if [[ -n "$main_admin_email" ]]; then
  printf 'Main panel admin email: %s\n' "$main_admin_email"
  printf 'Main panel password: configured during install; not stored in .env.\n'
else
  printf 'WARNING: Main panel ADMIN_EMAIL is not recorded in %s/.env.\n' "$INSTALL_DIR"
fi
docs_env="/opt/akfa-docs-platform/.env"
docs_admin_email="$(env_value "$docs_env" "ADMIN_EMAIL")"
if [[ -n "$docs_admin_email" ]]; then
  printf 'Docs admin email: %s\n' "$docs_admin_email"
  if [[ -n "$(env_value "$docs_env" "ADMIN_PASSWORD")" ]]; then
    printf 'Docs admin password: present in docs .env; hidden.\n'
  else
    printf 'WARNING: Docs ADMIN_PASSWORD is missing.\n'
  fi
fi

section "backend watchdog"
if [[ -x /usr/local/bin/akfa-backend-watchdog ]]; then
  if systemctl is-active --quiet akfa-backend-watchdog.timer; then
    printf 'akfa-backend-watchdog.timer: active\n'
  else
    printf 'WARNING: akfa-backend-watchdog.timer is inactive or not loaded.\n'
  fi
  if systemctl is-enabled --quiet akfa-backend-watchdog.timer; then
    printf 'akfa-backend-watchdog.timer: enabled\n'
  else
    printf 'WARNING: akfa-backend-watchdog.timer is disabled or not installed.\n'
  fi
  timer_state="$(systemctl show akfa-backend-watchdog.timer -p ActiveState -p SubState -p NextElapseUSecRealtime -p LastTriggerUSec 2>/dev/null || true)"
  printf 'Timer state:\n%s\n' "$timer_state"
  next_trigger="$(systemctl show akfa-backend-watchdog.timer -p NextElapseUSecRealtime --value 2>/dev/null || true)"
  sub_state="$(systemctl show akfa-backend-watchdog.timer -p SubState --value 2>/dev/null || true)"
  if [[ -z "$next_trigger" || "$next_trigger" == "n/a" || "$next_trigger" == "0" ]]; then
    printf 'WARNING: akfa-backend-watchdog.timer has no future trigger.\n'
  fi
  if [[ "$sub_state" != "waiting" ]]; then
    printf 'WARNING: akfa-backend-watchdog.timer substate is %s, expected waiting.\n' "${sub_state:-unknown}"
  fi
  last_run="$(systemctl show akfa-backend-watchdog.service -p ExecMainExitTimestamp --value 2>/dev/null || true)"
  printf 'Last watchdog service exit: %s\n' "${last_run:-unknown}"
  if journalctl -u akfa-backend-watchdog.service --since '3 minutes ago' -q 2>/dev/null | grep -q .; then
    printf 'Recent watchdog journal entries: yes\n'
  else
    printf 'WARNING: No watchdog journal entries in the last 3 minutes.\n'
  fi
  systemctl status akfa-backend-watchdog.timer --no-pager || true
  /usr/local/bin/akfa-backend-watchdog status || true
else
  printf 'WARNING: /usr/local/bin/akfa-backend-watchdog is missing or not executable.\n'
fi

section "backend logs"
compose_cmd logs --tail=120 backend || true
