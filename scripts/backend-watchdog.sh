#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/akfa-vpn}"
COMPOSE_FILE="${COMPOSE_FILE:-$INSTALL_DIR/docker-compose.yml}"
PROJECT_DIR="${PROJECT_DIR:-$INSTALL_DIR}"
BACKEND_SERVICE="${BACKEND_SERVICE:-backend}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
STATE_DIR="${STATE_DIR:-/var/lib/akfa-backend-watchdog}"
LOG_FILE="${LOG_FILE:-/var/log/akfa-backend-watchdog.log}"
FAIL_THRESHOLD="${FAIL_THRESHOLD:-3}"
CONNECT_TIMEOUT="${CONNECT_TIMEOUT:-2}"
MAX_TIME="${MAX_TIME:-5}"
COOLDOWN_SECONDS="${COOLDOWN_SECONDS:-180}"

usage() {
  cat <<'USAGE'
Usage:
  backend-watchdog.sh check    Run one bounded backend health check and restart after repeated failures.
  backend-watchdog.sh status   Show watchdog state and recent logs.

Environment overrides:
  INSTALL_DIR=/opt/akfa-vpn
  HEALTH_URL=http://127.0.0.1:8000/health
  FAIL_THRESHOLD=3
  COOLDOWN_SECONDS=180
USAGE
}

command="${1:-check}"
case "$command" in
  check|status|-h|--help) ;;
  *) usage; exit 2 ;;
esac
if [[ "$command" == "-h" || "$command" == "--help" ]]; then
  usage
  exit 0
fi

mkdir -p "$STATE_DIR"
touch "$LOG_FILE"

FAIL_COUNT_FILE="$STATE_DIR/fail-count"
LAST_RESTART_FILE="$STATE_DIR/last-restart"
LAST_REASON_FILE="$STATE_DIR/last-reason"

log() {
  local message="$1"
  local line
  line="$(date -Is) $message"
  printf '%s\n' "$line" >> "$LOG_FILE"
  logger -t akfa-backend-watchdog "$message" 2>/dev/null || true
}

fail_count() {
  if [[ -f "$FAIL_COUNT_FILE" ]]; then
    cat "$FAIL_COUNT_FILE"
  else
    printf '0'
  fi
}

set_fail_count() {
  printf '%s' "$1" > "$FAIL_COUNT_FILE"
}

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose --project-directory "$PROJECT_DIR" -f "$COMPOSE_FILE" "$@"
  else
    docker-compose --project-directory "$PROJECT_DIR" -f "$COMPOSE_FILE" "$@"
  fi
}

if [[ "$command" == "status" ]]; then
  printf 'AKFA backend watchdog\n'
  printf '  health url: %s\n' "$HEALTH_URL"
  printf '  fail count: %s/%s\n' "$(fail_count)" "$FAIL_THRESHOLD"
  printf '  last restart: %s\n' "$(cat "$LAST_RESTART_FILE" 2>/dev/null || printf 'never')"
  printf '  last reason: %s\n' "$(cat "$LAST_REASON_FILE" 2>/dev/null || printf '-')"
  printf '\nRecent log:\n'
  tail -n 40 "$LOG_FILE" 2>/dev/null || true
  exit 0
fi

http_code="000"
if http_code="$(curl -fsS -o /dev/null -w '%{http_code}' --connect-timeout "$CONNECT_TIMEOUT" --max-time "$MAX_TIME" "$HEALTH_URL" 2>/tmp/akfa-watchdog-curl.err)"; then
  if [[ "$http_code" == "200" ]]; then
    previous="$(fail_count)"
    if [[ "$previous" != "0" ]]; then
      log "backend recovered after $previous failed check(s)"
    fi
    set_fail_count 0
    exit 0
  fi
fi

reason="health check failed: http=$http_code $(tr '\n' ' ' </tmp/akfa-watchdog-curl.err 2>/dev/null || true)"
current=$(( $(fail_count) + 1 ))
set_fail_count "$current"
printf '%s' "$reason" > "$LAST_REASON_FILE"
log "$reason; consecutive_failures=$current threshold=$FAIL_THRESHOLD"

if (( current < FAIL_THRESHOLD )); then
  exit 0
fi

now="$(date +%s)"
last_restart="$(cat "$LAST_RESTART_FILE" 2>/dev/null || printf '0')"
if (( now - last_restart < COOLDOWN_SECONDS )); then
  log "restart skipped: cooldown is active (${COOLDOWN_SECONDS}s)"
  exit 0
fi

log "restarting docker compose service '$BACKEND_SERVICE' after $current consecutive failed checks"
compose_cmd restart "$BACKEND_SERVICE"
printf '%s' "$now" > "$LAST_RESTART_FILE"
set_fail_count 0
log "restart command finished for '$BACKEND_SERVICE'"
