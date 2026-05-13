#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/akfa-vpn}"
DOCS_INSTALL_DIR="${DOCS_INSTALL_DIR:-/opt/akfa-docs-platform}"
GIT_REPO="${GIT_REPO:-}"
GIT_BRANCH="${GIT_BRANCH:-main}"
PANEL_DOMAIN="${PANEL_DOMAIN:-}"
PUBLIC_CONNECT_DOMAIN="${PUBLIC_CONNECT_DOMAIN:-}"
DOCS_DOMAIN="${DOCS_DOMAIN:-}"
ADMIN_EMAIL="${ADMIN_EMAIL:-}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
DOCS_ADMIN_EMAIL="${DOCS_ADMIN_EMAIL:-}"
DOCS_ADMIN_PASSWORD="${DOCS_ADMIN_PASSWORD:-}"
SSL_EMAIL="${SSL_EMAIL:-}"
ENABLE_SSL="${ENABLE_SSL:-ask}"
INSTALL_DOCS="${INSTALL_DOCS:-ask}"
CERT_NAME="${CERT_NAME:-}"
ACME_WEBROOT="${ACME_WEBROOT:-/var/www/letsencrypt}"
DOWNLOADS_DIR="${DOWNLOADS_DIR:-/opt/akfa-downloads}"
MAX_DOWNLOAD_MB="${MAX_DOWNLOAD_MB:-200}"
ALLOWED_DOWNLOAD_EXTENSIONS="${ALLOWED_DOWNLOAD_EXTENSIONS:-apk,exe,dmg,zip,msi,pkg}"
DOCS_INSTALLED="no"
SSL_ENABLED="no"

usage() {
  cat <<'USAGE'
Usage: install.sh [--help]

Production-friendly installer for a clean Ubuntu VPS.
Run as root or with sudo.

Required input can be provided as environment variables or interactively:
  GIT_REPO=https://github.com/ORG/REPO.git
  PANEL_DOMAIN=panel.example.com
  PUBLIC_CONNECT_DOMAIN=panel.example.com
  DOCS_DOMAIN=help.example.com
  ADMIN_EMAIL=ADMIN_EMAIL
  ADMIN_PASSWORD=<prompted unless provided>
  DOCS_ADMIN_EMAIL=<defaults to ADMIN_EMAIL>
  DOCS_ADMIN_PASSWORD=<prompted unless provided>
  SSL_EMAIL=ADMIN_EMAIL

Defaults:
  INSTALL_DIR=/opt/akfa-vpn
  DOCS_INSTALL_DIR=/opt/akfa-docs-platform
  GIT_BRANCH=main
  CERT_NAME defaults to PANEL_DOMAIN

The script does not overwrite an existing .env without confirmation.
It does not remove Docker volumes or PostgreSQL data.
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  printf 'ERROR: run as root or via sudo.\n' >&2
  exit 1
fi

log() {
  printf '\n== %s ==\n' "$1"
}

warn() {
  printf 'WARNING: %s\n' "$1" >&2
}

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

ask() {
  local var_name="$1"
  local prompt="$2"
  local default="${3:-}"
  local current="${!var_name:-}"
  if [[ -n "$current" ]]; then
    return
  fi
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " current
    current="${current:-$default}"
  else
    read -r -p "$prompt: " current
  fi
  printf -v "$var_name" '%s' "$current"
}

require_interactive() {
  local label="$1"
  if [[ ! -t 0 ]]; then
    fail "$label is required in non-interactive mode. Provide it as an environment variable."
  fi
}

ask_password() {
  local var_name="$1"
  local label="$2"
  local current="${!var_name:-}"
  local first=""
  local second=""
  if [[ -n "$current" ]]; then
    if (( ${#current} < 12 )); then
      fail "$var_name must be at least 12 characters."
    fi
    if [[ "$current" == *$'\n'* || "$current" == *"'"* ]]; then
      fail "$var_name cannot contain newlines or single quotes."
    fi
    return
  fi
  require_interactive "$var_name"
  while true; do
    read -r -s -p "$label: " first
    printf '\n'
    read -r -s -p "Repeat $label: " second
    printf '\n'
    if [[ -z "$first" ]]; then
      printf 'Password cannot be empty.\n' >&2
      continue
    fi
    if (( ${#first} < 12 )); then
      printf 'Password must be at least 12 characters.\n' >&2
      continue
    fi
    if [[ "$first" != "$second" ]]; then
      printf 'Passwords do not match.\n' >&2
      continue
    fi
    if [[ "$first" == *$'\n'* || "$first" == *"'"* ]]; then
      printf 'Password cannot contain newlines or single quotes.\n' >&2
      continue
    fi
    printf -v "$var_name" '%s' "$first"
    break
  done
}

secret_urlsafe() {
  python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
}

fernet_key() {
  python3 - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
}

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose --project-directory "$INSTALL_DIR" -f "$INSTALL_DIR/docker-compose.yml" "$@"
  else
    docker-compose --project-directory "$INSTALL_DIR" -f "$INSTALL_DIR/docker-compose.yml" "$@"
  fi
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local method="${3:-GET}"
  local attempts="${4:-60}"
  local delay="${5:-2}"
  local i

  for ((i = 1; i <= attempts; i++)); do
    if [[ "$method" == "HEAD" ]]; then
      if curl -fsSI --connect-timeout 2 --max-time 10 "$url" >/dev/null; then
        printf '%s is responding: %s\n' "$name" "$url"
        return 0
      fi
    else
      if curl -fsS --connect-timeout 2 --max-time 10 "$url" >/dev/null; then
        printf '%s is responding: %s\n' "$name" "$url"
        return 0
      fi
    fi
    sleep "$delay"
  done

  fail "$name did not become healthy at $url"
}

nginx_test() {
  local output
  if ! output="$(nginx -t 2>&1)"; then
    printf '%s\n' "$output" >&2
    return 1
  fi
  printf '%s\n' "$output"
  if printf '%s\n' "$output" | grep -qi 'conflicting server name'; then
    return 1
  fi
}

require_service_running() {
  local service="$1"
  if ! compose_cmd ps --status running --services | grep -qx "$service"; then
    compose_cmd ps
    fail "docker compose service '$service' is not running"
  fi
}

wait_for_postgres() {
  local i
  for ((i = 1; i <= 60; i++)); do
    if compose_cmd exec -T postgres sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' >/dev/null 2>&1; then
      printf 'PostgreSQL is ready.\n'
      return 0
    fi
    sleep 2
  done
  compose_cmd logs --tail=120 postgres || true
  fail "PostgreSQL did not become ready"
}

install_packages() {
  apt-get update
  apt-get install -y ca-certificates curl gnupg git nginx certbot python3 python3-cryptography
  systemctl enable --now nginx
  if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  fi
}

install_node20_if_needed() {
  if command -v node >/dev/null 2>&1 && node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 20 ? 0 : 1)' >/dev/null 2>&1; then
    return
  fi
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
}

render_template() {
  local source="$1"
  local target="$2"
  local panel_server_names="$PANEL_DOMAIN"
  if [[ "$PUBLIC_CONNECT_DOMAIN" != "$PANEL_DOMAIN" ]]; then
    panel_server_names="$panel_server_names $PUBLIC_CONNECT_DOMAIN"
  fi
  sed \
    -e "s/PANEL_SERVER_NAMES/$panel_server_names/g" \
    -e "s/PANEL_DOMAIN/$PANEL_DOMAIN/g" \
    -e "s/PUBLIC_CONNECT_DOMAIN/$PUBLIC_CONNECT_DOMAIN/g" \
    -e "s/DOCS_DOMAIN/$DOCS_DOMAIN/g" \
    -e "s/CERT_NAME/$CERT_NAME/g" \
    "$source" > "$target"
}

install_panel_http_nginx() {
  log "Install HTTP-only nginx config"
  install -d "$ACME_WEBROOT"
  render_template deploy/nginx/panel.conf /etc/nginx/sites-available/akfa-panel.conf
  ln -sf /etc/nginx/sites-available/akfa-panel.conf /etc/nginx/sites-enabled/akfa-panel.conf
  rm -f /etc/nginx/sites-enabled/akfa-panel-ssl.conf
  nginx_test
  systemctl reload nginx
}

install_docs_http_nginx() {
  render_template deploy/nginx/docs.conf /etc/nginx/sites-available/akfa-docs.conf
  ln -sf /etc/nginx/sites-available/akfa-docs.conf /etc/nginx/sites-enabled/akfa-docs.conf
  rm -f /etc/nginx/sites-enabled/akfa-docs-ssl.conf
}

configure_ssl_if_requested() {
  local ssl_confirm="n"
  if [[ "$ENABLE_SSL" == "ask" ]]; then
    read -r -p "Issue Let's Encrypt certificate? [y/N]: " ssl_confirm
  fi
  if [[ "$ENABLE_SSL" != "yes" && ! "$ssl_confirm" =~ ^[Yy]$ ]]; then
    warn "SSL was not requested. Nginx remains in valid HTTP-only mode."
    return 0
  fi

  log "Issue Let's Encrypt certificate"
  local cert_domains=(-d "$PANEL_DOMAIN")
  if [[ "$PUBLIC_CONNECT_DOMAIN" != "$PANEL_DOMAIN" ]]; then
    cert_domains+=(-d "$PUBLIC_CONNECT_DOMAIN")
  fi
  if [[ -f /etc/nginx/sites-enabled/akfa-docs.conf && "$DOCS_DOMAIN" != "$PANEL_DOMAIN" && "$DOCS_DOMAIN" != "$PUBLIC_CONNECT_DOMAIN" ]]; then
    cert_domains+=(-d "$DOCS_DOMAIN")
  fi

  local certbot_ok="no"
  local attempt
  for attempt in 1 2 3; do
    if certbot certonly --webroot -w "$ACME_WEBROOT" --cert-name "$CERT_NAME" "${cert_domains[@]}" --email "$SSL_EMAIL" --agree-tos --no-eff-email; then
      certbot_ok="yes"
      break
    fi
    warn "Certbot attempt $attempt failed."
    if (( attempt < 3 )); then
      sleep $((attempt * 20))
    fi
  done

  if [[ "$certbot_ok" != "yes" ]]; then
    warn "Certbot failed. Leaving nginx in HTTP-only mode."
    warn "Retry later: sudo certbot certonly --webroot -w $ACME_WEBROOT --cert-name $CERT_NAME ${cert_domains[*]} --email $SSL_EMAIL --agree-tos --no-eff-email"
    nginx_test
    systemctl reload nginx
    return 0
  fi

  if [[ ! -f "/etc/letsencrypt/live/$CERT_NAME/fullchain.pem" || ! -f "/etc/letsencrypt/live/$CERT_NAME/privkey.pem" ]]; then
    warn "Certificate files were not found after certbot. Leaving nginx in HTTP-only mode."
    nginx_test
    systemctl reload nginx
    return 0
  fi

  log "Enable HTTPS nginx config"
  render_template deploy/nginx/panel-ssl.conf /etc/nginx/sites-available/akfa-panel-ssl.conf
  ln -sf /etc/nginx/sites-available/akfa-panel-ssl.conf /etc/nginx/sites-enabled/akfa-panel-ssl.conf
  if [[ -f /etc/nginx/sites-enabled/akfa-docs.conf ]]; then
    render_template deploy/nginx/docs-ssl.conf /etc/nginx/sites-available/akfa-docs-ssl.conf
    ln -sf /etc/nginx/sites-available/akfa-docs-ssl.conf /etc/nginx/sites-enabled/akfa-docs-ssl.conf
  fi
  nginx_test
  systemctl reload nginx
  SSL_ENABLED="yes"
}

validate_env_file() {
  local env_file="$1"
  if grep -nEv '^[A-Za-z_][A-Za-z0-9_]*=.*$|^#|^$' "$env_file"; then
    fail "Invalid environment assignment in $env_file"
  fi
}

env_quote() {
  local value="$1"
  if [[ "$value" == *$'\n'* || "$value" == *"'"* ]]; then
    fail "Environment values cannot contain newlines or single quotes."
  fi
  printf "'%s'" "$value"
}

docs_service_user() {
  awk -F= '/^User=/{print $2; exit}' "$DOCS_INSTALL_DIR/deploy/akfa-docs-platform.service" 2>/dev/null || true
}

write_docs_env() {
  local env_file="$DOCS_INSTALL_DIR/.env"
  if [[ -f "$env_file" ]]; then
    validate_env_file "$env_file"
    return
  fi
  cat > "$env_file" <<EOF
NODE_ENV=production
HOSTNAME=127.0.0.1
PORT=6876
SITE_URL=https://$DOCS_DOMAIN
DATA_DIR=$DOCS_INSTALL_DIR/data
DOWNLOADS_DIR=$DOWNLOADS_DIR
SESSION_SECRET=$(secret_urlsafe)
ADMIN_EMAIL=$DOCS_ADMIN_EMAIL
ADMIN_PASSWORD=$(env_quote "$DOCS_ADMIN_PASSWORD")
MAX_UPLOAD_MB=5
MAX_DOWNLOAD_MB=$MAX_DOWNLOAD_MB
ALLOWED_DOWNLOAD_EXTENSIONS=$ALLOWED_DOWNLOAD_EXTENSIONS
EOF
  chmod 600 "$env_file"
  validate_env_file "$env_file"
}

prepare_docs_data_dir() {
  local service_user
  service_user="$(docs_service_user)"
  service_user="${service_user:-www-data}"
  install -d "$DOCS_INSTALL_DIR/data" "$DOCS_INSTALL_DIR/data/uploads"
  install -d "$DOWNLOADS_DIR"
  chown -R "$service_user:$service_user" "$DOCS_INSTALL_DIR/data"
  chown -R "$service_user:$service_user" "$DOWNLOADS_DIR"
  chmod 750 "$DOCS_INSTALL_DIR/data"
  chmod 750 "$DOCS_INSTALL_DIR/data/uploads"
  chmod 750 "$DOWNLOADS_DIR"
}

sync_seed_downloads() {
  local manifest="$DOCS_INSTALL_DIR/seed-downloads/downloads.manifest.json"
  local service_user
  service_user="$(docs_service_user)"
  service_user="${service_user:-www-data}"
  if [[ ! -f "$manifest" ]]; then
    warn "Seed downloads manifest not found: $manifest"
    return 0
  fi
  if ! command -v node >/dev/null 2>&1; then
    warn "Node is not available; seed downloads were not copied."
    return 0
  fi
  DOWNLOADS_DIR="$DOWNLOADS_DIR" OVERWRITE_SEED_DOWNLOADS="${OVERWRITE_SEED_DOWNLOADS:-no}" MANIFEST_PATH="$manifest" node <<'NODE'
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
  chown -R "$service_user:$service_user" "$DOWNLOADS_DIR"
}

install_watchdog() {
  log "Install backend watchdog"
  install -m 0755 scripts/backend-watchdog.sh /usr/local/bin/akfa-backend-watchdog
  install -d /etc/akfa
  cp deploy/systemd/backend-watchdog.env.example /etc/akfa/backend-watchdog.env
  sed -i "s|INSTALL_DIR=/opt/akfa-vpn|INSTALL_DIR=$INSTALL_DIR|g; s|COMPOSE_FILE=/opt/akfa-vpn/docker-compose.yml|COMPOSE_FILE=$INSTALL_DIR/docker-compose.yml|g; s|PROJECT_DIR=/opt/akfa-vpn|PROJECT_DIR=$INSTALL_DIR|g" /etc/akfa/backend-watchdog.env
  cp deploy/systemd/akfa-backend-watchdog.service /etc/systemd/system/akfa-backend-watchdog.service
  cp deploy/systemd/akfa-backend-watchdog.timer /etc/systemd/system/akfa-backend-watchdog.timer
  systemctl daemon-reload
  systemctl disable --now akfa-backend-watchdog.timer 2>/dev/null || true
  systemctl enable --now akfa-backend-watchdog.timer
  systemctl is-enabled akfa-backend-watchdog.timer >/dev/null
  systemctl is-active --quiet akfa-backend-watchdog.timer
  /usr/local/bin/akfa-backend-watchdog status >/dev/null
}

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  ask GIT_REPO "Git repository URL"
fi
ask PANEL_DOMAIN "Panel domain" "panel.example.com"
ask PUBLIC_CONNECT_DOMAIN "Public connect domain (can be the same as panel domain)" "$PANEL_DOMAIN"
ask DOCS_DOMAIN "Docs domain" "help.example.com"
ask ADMIN_EMAIL "Main panel admin email" "ADMIN_EMAIL"
ask_password ADMIN_PASSWORD "Main panel admin password"
if [[ -z "$DOCS_ADMIN_EMAIL" ]]; then
  DOCS_ADMIN_EMAIL="$ADMIN_EMAIL"
fi
ask SSL_EMAIL "Email for Let's Encrypt" "$ADMIN_EMAIL"
CERT_NAME="${CERT_NAME:-$PANEL_DOMAIN}"
cors_origins="[\"https://$PANEL_DOMAIN\"]"
if [[ "$PUBLIC_CONNECT_DOMAIN" != "$PANEL_DOMAIN" ]]; then
  cors_origins="[\"https://$PANEL_DOMAIN\",\"https://$PUBLIC_CONNECT_DOMAIN\"]"
fi

log "Install packages"
install_packages

if [[ ! -d "$INSTALL_DIR/.git" ]]; then
  mkdir -p "$(dirname "$INSTALL_DIR")"
  git clone --branch "$GIT_BRANCH" "$GIT_REPO" "$INSTALL_DIR"
else
  printf 'Using existing checkout: %s\n' "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

if [[ -f .env ]]; then
  read -r -p ".env already exists. Keep it? [Y/n]: " keep_env
  if [[ "${keep_env:-Y}" =~ ^[Nn]$ ]]; then
    cp ".env" ".env.$(date +%Y%m%d-%H%M%S).bak"
    rm -f .env
  fi
fi

if [[ ! -f .env ]]; then
  db_password="$(secret_urlsafe)"
  session_secret="$(secret_urlsafe)"
  encryption_key="$(fernet_key)"
  cat > .env <<EOF
ENVIRONMENT=production
POSTGRES_DB=akfa
POSTGRES_USER=akfa
POSTGRES_PASSWORD=$db_password
DATABASE_URL=postgresql+psycopg://akfa:$db_password@postgres:5432/akfa
SESSION_SECRET=$session_secret
ENCRYPTION_KEY=$encryption_key
ADMIN_EMAIL=$ADMIN_EMAIL
CORS_ORIGINS=$cors_origins
SECURE_COOKIES=true
SUBSCRIPTION_BASE_URL=https://$PUBLIC_CONNECT_DOMAIN
SUBSCRIPTION_TITLE=AKFA VPN
SUBSCRIPTION_FILENAME=akfa-vpn
SUBSCRIPTION_ANNOUNCEMENT=
SUBSCRIPTION_UPDATE_INTERVAL_HOURS=12
SUBSCRIPTION_SERVER_PREFIX=AKFA
EOF
  chmod 600 .env
  printf 'Generated .env for main panel.\n'
else
  chmod 600 .env
fi

install_panel_http_nginx

log "Build images"
compose_cmd build --progress=plain backend frontend

log "Start PostgreSQL"
compose_cmd up -d postgres
require_service_running postgres
wait_for_postgres

log "Run database migrations once"
compose_cmd run --rm --no-deps backend alembic upgrade head

log "Start backend and frontend"
compose_cmd up -d backend frontend
require_service_running postgres
require_service_running backend
require_service_running frontend
wait_for_url "Backend health" "http://127.0.0.1:8000/health" GET 60 2
wait_for_url "Frontend" "http://127.0.0.1:8080" HEAD 60 2

log "Create or verify super admin"
compose_cmd exec -T -e AKFA_ADMIN_PASSWORD="$ADMIN_PASSWORD" backend python -m app.cli seed-admin --email "$ADMIN_EMAIL" --password-env AKFA_ADMIN_PASSWORD --reset-password

install_watchdog

if [[ "$INSTALL_DOCS" == "yes" || "$INSTALL_DOCS" == "ask" ]]; then
  docs_confirm="n"
  if [[ "$INSTALL_DOCS" == "ask" ]]; then
    read -r -p "Build and install akfa-docs-platform on this VPS? [y/N]: " docs_confirm
  fi
  if [[ "$INSTALL_DOCS" == "yes" || "$docs_confirm" =~ ^[Yy]$ ]]; then
    log "Install docs platform"
    ask DOCS_ADMIN_EMAIL "Docs admin email" "$ADMIN_EMAIL"
    ask_password DOCS_ADMIN_PASSWORD "Docs admin password"
    install_node20_if_needed
    (cd akfa-docs-platform && npm ci --no-audit --no-fund && npm run build && node scripts/package-deploy.mjs)
    tar -xzf akfa-docs-platform/dist/akfa-docs-platform-deploy.tar.gz -C "$(dirname "$DOCS_INSTALL_DIR")"
    write_docs_env
    prepare_docs_data_dir
    sync_seed_downloads
    cp "$DOCS_INSTALL_DIR/deploy/akfa-docs-platform.service" /etc/systemd/system/akfa-docs-platform.service
    install_docs_http_nginx
    systemctl daemon-reload
    systemctl enable --now akfa-docs-platform
    wait_for_url "Docs homepage" "http://127.0.0.1:6876" HEAD 60 2
    wait_for_url "Docs admin login" "http://127.0.0.1:6876/admin/login" HEAD 60 2
    DOCS_INSTALLED="yes"
  fi
fi

nginx_test
systemctl reload nginx
configure_ssl_if_requested

log "Final checks"
require_service_running postgres
require_service_running backend
require_service_running frontend
wait_for_url "Backend health" "http://127.0.0.1:8000/health" GET 3 2
wait_for_url "Frontend" "http://127.0.0.1:8080" HEAD 3 2
if [[ "$DOCS_INSTALLED" == "yes" ]]; then
  wait_for_url "Docs homepage" "http://127.0.0.1:6876" HEAD 3 2
  wait_for_url "Docs admin login" "http://127.0.0.1:6876/admin/login" HEAD 3 2
fi
nginx_test
/usr/local/bin/akfa-backend-watchdog status >/dev/null
if [[ "$SSL_ENABLED" == "yes" ]]; then
  wait_for_url "Panel HTTPS" "https://$PANEL_DOMAIN" HEAD 3 2
  if [[ "$DOCS_INSTALLED" == "yes" ]]; then
    wait_for_url "Docs HTTPS" "https://$DOCS_DOMAIN" HEAD 3 2
  fi
fi

printf '\nInstall finished successfully.\n'
printf 'Panel: http://%s\n' "$PANEL_DOMAIN"
printf 'Public connect base: http://%s\n' "$PUBLIC_CONNECT_DOMAIN"
if [[ "$SSL_ENABLED" == "yes" ]]; then
  printf 'HTTPS enabled for certificate name: %s\n' "$CERT_NAME"
else
  printf 'HTTPS is not enabled. Nginx is running in valid HTTP-only mode.\n'
fi
printf 'Diagnostics: %s/scripts/doctor.sh\n' "$INSTALL_DIR"
