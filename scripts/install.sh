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
SSL_EMAIL="${SSL_EMAIL:-}"
ENABLE_SSL="${ENABLE_SSL:-ask}"
INSTALL_DOCS="${INSTALL_DOCS:-ask}"

usage() {
  cat <<'USAGE'
Usage: install.sh [--help]

Production-friendly installer for a clean Ubuntu VPS.
Run as root or with sudo.

Required input can be provided as environment variables or interactively:
  GIT_REPO=https://github.com/ORG/REPO.git
  PANEL_DOMAIN=panel.example.com
  PUBLIC_CONNECT_DOMAIN=connect.example.com
  DOCS_DOMAIN=help.example.com
  ADMIN_EMAIL=ADMIN_EMAIL
  SSL_EMAIL=ADMIN_EMAIL

Defaults:
  INSTALL_DIR=/opt/akfa-vpn
  DOCS_INSTALL_DIR=/opt/akfa-docs-platform
  GIT_BRANCH=main

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

install_packages() {
  apt-get update
  apt-get install -y ca-certificates curl gnupg git nginx certbot python3 python3-cryptography
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
  sed \
    -e "s/PANEL_DOMAIN/$PANEL_DOMAIN/g" \
    -e "s/PUBLIC_CONNECT_DOMAIN/$PUBLIC_CONNECT_DOMAIN/g" \
    -e "s/DOCS_DOMAIN/$DOCS_DOMAIN/g" \
    "$source" > "$target"
}

ask GIT_REPO "Git repository URL"
ask PANEL_DOMAIN "Panel domain" "panel.example.com"
ask PUBLIC_CONNECT_DOMAIN "Public connect domain" "$PANEL_DOMAIN"
ask DOCS_DOMAIN "Docs domain" "help.example.com"
ask ADMIN_EMAIL "Initial admin email" "ADMIN_EMAIL"
ask SSL_EMAIL "Email for Let's Encrypt" "$ADMIN_EMAIL"
admin_password="${ADMIN_PASSWORD:-$(secret_urlsafe)}"

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
CORS_ORIGINS=["https://$PANEL_DOMAIN","https://$PUBLIC_CONNECT_DOMAIN"]
SECURE_COOKIES=true
SUBSCRIPTION_BASE_URL=https://$PUBLIC_CONNECT_DOMAIN
EOF
  printf 'Generated .env. Initial admin password: %s\n' "$admin_password"
fi

docker compose build --progress=plain
docker compose up -d
docker compose exec -T backend python -m app.cli seed-admin --email "$ADMIN_EMAIL" --password "$admin_password"

install -m 0755 scripts/backend-watchdog.sh /usr/local/bin/akfa-backend-watchdog
install -d /etc/akfa
cp deploy/systemd/backend-watchdog.env.example /etc/akfa/backend-watchdog.env
sed -i "s|INSTALL_DIR=/opt/akfa-vpn|INSTALL_DIR=$INSTALL_DIR|g; s|COMPOSE_FILE=/opt/akfa-vpn/docker-compose.yml|COMPOSE_FILE=$INSTALL_DIR/docker-compose.yml|g; s|PROJECT_DIR=/opt/akfa-vpn|PROJECT_DIR=$INSTALL_DIR|g" /etc/akfa/backend-watchdog.env
cp deploy/systemd/akfa-backend-watchdog.service /etc/systemd/system/akfa-backend-watchdog.service
cp deploy/systemd/akfa-backend-watchdog.timer /etc/systemd/system/akfa-backend-watchdog.timer
systemctl daemon-reload
systemctl enable --now akfa-backend-watchdog.timer

render_template deploy/nginx/panel.conf /etc/nginx/sites-available/akfa-panel.conf
ln -sf /etc/nginx/sites-available/akfa-panel.conf /etc/nginx/sites-enabled/akfa-panel.conf

if [[ "$INSTALL_DOCS" == "yes" || "$INSTALL_DOCS" == "ask" ]]; then
  docs_confirm="n"
  if [[ "$INSTALL_DOCS" == "ask" ]]; then
    read -r -p "Build and install akfa-docs-platform on this VPS? [y/N]: " docs_confirm
  fi
  if [[ "$INSTALL_DOCS" == "yes" || "$docs_confirm" =~ ^[Yy]$ ]]; then
    install_node20_if_needed
    (cd akfa-docs-platform && npm ci --no-audit --no-fund && npm run build && node scripts/package-deploy.mjs)
    tar -xzf akfa-docs-platform/dist/akfa-docs-platform-deploy.tar.gz -C "$(dirname "$DOCS_INSTALL_DIR")"
    if [[ ! -f "$DOCS_INSTALL_DIR/.env" ]]; then
      cp "$DOCS_INSTALL_DIR/.env.example" "$DOCS_INSTALL_DIR/.env"
      sed -i \
        -e "s|https://DOCS_DOMAIN|https://$DOCS_DOMAIN|g" \
        -e "s|ADMIN_EMAIL|$ADMIN_EMAIL|g" \
        -e "s|replace-with-at-least-32-random-characters|$(secret_urlsafe)|g" \
        -e "s|replace-with-temporary-admin-password|$admin_password|g" \
        "$DOCS_INSTALL_DIR/.env"
    fi
    cp "$DOCS_INSTALL_DIR/deploy/akfa-docs-platform.service" /etc/systemd/system/akfa-docs-platform.service
    render_template deploy/nginx/docs.conf /etc/nginx/sites-available/akfa-docs.conf
    ln -sf /etc/nginx/sites-available/akfa-docs.conf /etc/nginx/sites-enabled/akfa-docs.conf
    systemctl daemon-reload
    systemctl enable --now akfa-docs-platform
  fi
fi

nginx -t
systemctl reload nginx

if [[ "$ENABLE_SSL" == "yes" || "$ENABLE_SSL" == "ask" ]]; then
  ssl_confirm="n"
  if [[ "$ENABLE_SSL" == "ask" ]]; then
    read -r -p "Issue Let's Encrypt certificate for panel domains? [y/N]: " ssl_confirm
  fi
  if [[ "$ENABLE_SSL" == "yes" || "$ssl_confirm" =~ ^[Yy]$ ]]; then
    cert_domains=(-d "$PANEL_DOMAIN")
    if [[ "$PUBLIC_CONNECT_DOMAIN" != "$PANEL_DOMAIN" ]]; then
      cert_domains+=(-d "$PUBLIC_CONNECT_DOMAIN")
    fi
    if [[ -f /etc/nginx/sites-enabled/akfa-docs.conf ]]; then
      cert_domains+=(-d "$DOCS_DOMAIN")
    fi
    certbot --nginx "${cert_domains[@]}" --email "$SSL_EMAIL" --agree-tos --no-eff-email
  fi
fi

printf '\nInstall finished.\n'
printf 'Panel: https://%s\n' "$PANEL_DOMAIN"
printf 'Public connect base: https://%s\n' "$PUBLIC_CONNECT_DOMAIN"
printf 'Diagnostics: %s/scripts/doctor.sh\n' "$INSTALL_DIR"
