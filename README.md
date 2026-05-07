# AKFA VPN

AKFA VPN - административная панель для управления корпоративным VPN-доступом через VPS-серверы с Xray-core, VLESS Reality и XTLS Vision.

Проект предназначен для сценария, где администратор управляет пользователями, лимитами устройств, VPN-нодами, профилями доступа, подписками и Xray config из единой панели. Пользователь получает одну публичную страницу подключения, сам выбирает платформу и добавляет подписку в VPN-клиент. Устройство регистрируется автоматически при первом реальном запросе подписки с `x-hwid`.

Руководство администратора: [docs/ADMIN_GUIDE.md](docs/ADMIN_GUIDE.md).

## Коротко

Текущая production-логика AKFA:

- Backend: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, AsyncSSH.
- Frontend: React, Vite, TypeScript, Tailwind CSS, Nginx production image.
- Авторизация админки: cookie session, CSRF, TOTP.
- VPN-протокол: Xray-core, VLESS Reality, XTLS Vision.
- Device limit: HWID hard mode.
- Один VPN user = несколько HWID devices.
- Одно устройство = один UUID/client в Xray.
- Подписки: raw VLESS, base64, Clash YAML, sing-box JSON.
- Nodes: `akfa_owned` и `imported_safe`.
- Xray install: background job с polling, без долгого HTTP request.
- Apply-config: safe, с backup, timeout и сохранением unknown clients в `imported_safe`.
- Dashboard traffic по серверам: node-level deltas, не сумма текущих пользователей.
- Админка: users, devices, departments, profiles, servers, bulk node access, traffic, audit, backup, settings.

## Архитектура

```text
AKFA admin UI
  |
  | cookie session + CSRF
  v
FastAPI backend
  |
  | SQLAlchemy / Alembic
  v
PostgreSQL
  |
  | AsyncSSH
  v
Linux VPS nodes
  |
  v
Xray-core / VLESS Reality / StatsService
```

Публичная часть:

```text
VPN user
  |
  v
/connect/{user_token}
  |
  v
/sub/{user_token}?platform=...&client=...&format=...
  |
  | x-hwid required
  v
HWID device registration
  |
  v
safe apply-config to allowed nodes
  |
  v
subscription response for that device UUID
```

## Структура проекта

```text
.
|-- backend/
|   |-- app/
|   |   |-- api/
|   |   |   |-- auth.py          # login, TOTP, session endpoints
|   |   |   `-- entities.py      # admin/public API
|   |   |-- core/
|   |   |   |-- config.py        # env settings
|   |   |   `-- security.py      # password, sessions, CSRF, encryption helpers
|   |   |-- db/
|   |   |   `-- session.py
|   |   |-- models/
|   |   |   `-- __init__.py      # SQLAlchemy models
|   |   |-- schemas/
|   |   |   |-- auth.py
|   |   |   |-- common.py
|   |   |   `-- entities.py
|   |   |-- services/
|   |   |   |-- backup.py
|   |   |   |-- config_apply.py
|   |   |   |-- hwid.py
|   |   |   |-- node_action_jobs.py
|   |   |   |-- server_metrics.py
|   |   |   |-- ssh_installer.py
|   |   |   |-- subscriptions.py
|   |   |   |-- traffic.py
|   |   |   |-- xray_config.py
|   |   |   `-- xray_probe.py
|   |   |-- cli.py
|   |   `-- main.py
|   |-- alembic/
|   |   `-- versions/
|   |-- tests/
|   |-- Dockerfile
|   |-- alembic.ini
|   `-- pyproject.toml
|-- frontend/
|   |-- src/
|   |   |-- components/
|   |   |-- lib/
|   |   `-- App.tsx
|   |-- Dockerfile
|   |-- nginx.conf
|   |-- package.json
|   `-- package-lock.json
|-- docker-compose.yml
|-- .env.example
|-- .dockerignore
|-- .gitignore
`-- README.md
```

## Быстрый запуск

Создайте `.env`:

```powershell
Copy-Item .env.example .env
```

Или на Linux/macOS:

```bash
cp .env.example .env
```

Соберите и запустите:

```bash
docker compose build --progress=plain
docker compose up -d
```

Создайте администратора:

```bash
read -r -s -p "Admin password: " AKFA_ADMIN_PASSWORD; echo
docker compose exec -T -e AKFA_ADMIN_PASSWORD backend python -m app.cli seed-admin --email ADMIN_EMAIL --password-env AKFA_ADMIN_PASSWORD --reset-password
```

Проверка:

```bash
curl http://localhost:8000/health
curl -I http://localhost:8080
```

Адреса:

- Frontend: `http://localhost:8080`
- Backend API: `http://localhost:8000`
- Healthcheck: `http://localhost:8000/health`
- PostgreSQL внутри compose network: `postgres:5432`

## Docker Compose

`docker-compose.yml` поднимает:

- `postgres` - PostgreSQL 16 Alpine с volume `postgres_data`;
- `backend` - FastAPI, перед стартом выполняет `alembic upgrade head`;
- `frontend` - production build React через Nginx.

Основные команды:

```bash
docker compose build --progress=plain
docker compose up -d
docker compose ps
docker compose logs --tail=200 backend
docker compose exec -T backend pytest
docker compose exec -T frontend npm run build
```

## Переменные окружения

Файл `.env` не коммитится.

Пример:

```env
ENVIRONMENT=production
POSTGRES_DB=akfa
POSTGRES_USER=akfa
POSTGRES_PASSWORD=replace-with-generated-db-password
DATABASE_URL=postgresql+psycopg://akfa:replace-with-generated-db-password@postgres:5432/akfa
SESSION_SECRET=replace-with-at-least-32-random-characters
ENCRYPTION_KEY=replace-with-a-fernet-key-from-python-cryptography
ADMIN_EMAIL=ADMIN_EMAIL
CORS_ORIGINS=["https://PANEL_DOMAIN","https://PUBLIC_CONNECT_DOMAIN"]
SECURE_COOKIES=true
SUBSCRIPTION_BASE_URL=https://PUBLIC_CONNECT_DOMAIN
```

Назначение:

| Переменная | Назначение |
| --- | --- |
| `ENVIRONMENT` | Режим окружения. Для production используйте `production`. |
| `POSTGRES_DB` | Имя PostgreSQL database внутри compose. |
| `POSTGRES_USER` | PostgreSQL user внутри compose. |
| `POSTGRES_PASSWORD` | Сгенерированный пароль PostgreSQL. |
| `DATABASE_URL` | DSN PostgreSQL для SQLAlchemy/psycopg. |
| `SESSION_SECRET` | Секрет подписи cookie-session и временных auth tokens. |
| `ENCRYPTION_KEY` | Fernet key для SSH-паролей и private keys. |
| `ADMIN_EMAIL` | Email администратора, созданного install/bootstrap. Password не хранится в main `.env`. |
| `CORS_ORIGINS` | Разрешенные origins frontend. |
| `SECURE_COOKIES` | `true` для HTTPS production, `false` для local HTTP. |
| `SUBSCRIPTION_BASE_URL` | Публичная база для connect/subscription URLs. |

Сгенерировать Fernet key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Сгенерировать session secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Администраторы и TOTP

Создать администратора:

```bash
read -r -s -p "Admin password: " AKFA_ADMIN_PASSWORD; echo
docker compose exec -T -e AKFA_ADMIN_PASSWORD backend python -m app.cli seed-admin --email ADMIN_EMAIL --password-env AKFA_ADMIN_PASSWORD --reset-password
```

Создать администратора с TOTP:

```bash
read -r -s -p "Admin password: " AKFA_ADMIN_PASSWORD; echo
docker compose exec -T -e AKFA_ADMIN_PASSWORD backend python -m app.cli seed-admin --email ADMIN_EMAIL --password-env AKFA_ADMIN_PASSWORD --reset-password --enable-totp
```

Flow входа:

1. Admin вводит email/password.
2. Если TOTP не включен - сразу создается полноценная session.
3. Если TOTP включен - backend возвращает temporary login token и требует 6-значный код.
4. `POST /auth/2fa/verify` проверяет код.
5. Только после валидного TOTP создается полноценная session.

Flow включения TOTP:

1. `POST /auth/2fa/setup/start` генерирует pending secret.
2. Pending secret не включает 2FA.
3. Login после незавершенного setup не требует TOTP.
4. `POST /auth/2fa/setup/confirm` проверяет код.
5. Только после confirm pending secret становится active secret, а `totp_enabled=true`.
6. `POST /auth/2fa/disable` очищает active и pending secrets.

В UI это находится в `Настройки администратора`.

## Основные сущности

### Admin

Администратор панели:

- email;
- password hash;
- role;
- `totp_secret_encrypted`;
- `pending_totp_secret_encrypted`;
- `totp_enabled`;
- `totp_confirmed_at`;
- `totp_required`;
- recovery-related fields, если включены в схеме.

### Department

Отдел пользователя:

- name;
- description;
- default access profile.

Используется для организации пользователей и bulk operations.

### AccessProfile

Профиль доступа:

- name;
- routing mode: `full_tunnel`, `ru_direct`, `custom`;
- direct domains;
- blocked domains;
- traffic limit default;
- срок действия по умолчанию;
- `allowed_nodes` - nodes профиля по умолчанию;
- client template.

Профиль может задавать server access. Если у пользователя нет explicit allowed nodes, он наследует nodes из профиля.

### VPN user

VPN-пользователь - это один корпоративный доступ.

Поля:

- `username`;
- first/last name;
- department;
- access profile;
- status;
- `device_limit`;
- traffic limit;
- `expires_at`;
- `subscription_token`;
- explicit `allowed_node_ids`;
- `primary_node_id`;
- traffic counters;
- online state.

Пользователь получает одну connect-ссылку:

```text
/connect/{subscription_token}
```

### VPN user device

Устройство пользователя:

- `uuid` - UUID Xray client;
- `subscription_token` - legacy/device-specific subscription token;
- status: `active`, `revoked`;
- `hwid_hash`;
- `hwid_masked`;
- platform;
- client name;
- device model;
- OS version;
- app version;
- user-agent;
- created IP;
- last IP;
- traffic counters;
- `last_seen_at`;
- `last_subscribed_at`.

Raw `x-hwid` не хранится.

### VPS node

VPN-сервер:

- SSH credentials encrypted;
- public host;
- location;
- VLESS port;
- SNI;
- Reality private/public keys;
- short ID;
- Xray config path;
- Xray service name;
- managed mode;
- status;
- install/apply logs;
- traffic counters;
- config apply status.

## Node statuses

Поддерживаемые статусы node:

| Status | Значение |
| --- | --- |
| `draft` | Сервер добавлен, но еще не проверен/не установлен. |
| `checking` | Выполняется проверка. |
| `online` | Сервер рабочий и попадает в подписки. |
| `offline` | Сервер недоступен и не должен попадать в подписки. |
| `installing` | Идет установка Xray background job. |
| `failed` | Последняя проверка/операция завершилась ошибкой. |
| `disabled` | Сервер отключен админом и не попадает в подписки. |
| `maintenance` | Сервер на обслуживании и не попадает в подписки. |
| `deleted` | Сервер скрыт из UI и исключен из подписок. |

Подписки включают только nodes со статусом `online`.

## Node access logic

Для пользователя применяется такая логика:

1. Если у пользователя есть explicit `allowed_node_ids`, используются они.
2. Если explicit список пустой, используются `allowed_nodes` из access profile.
3. Если нет ни explicit nodes, ни profile nodes, при создании пользователя может быть использована совместимая автопривязка к online node.
4. В subscription runtime backend все равно отфильтрует nodes по status `online`.
5. `primary_node_id`, если доступен и online, идет первым в subscription.
6. Если primary node недоступен, выбирается первый active allowed node.
7. Если нет доступных online nodes, подписка не выдается.

## Управление серверами

На странице серверов и в карточке node доступны:

- проверка SSH;
- verify Xray;
- dry-run install;
- real install Xray;
- apply config;
- config preview;
- edit Reality/Xray params;
- enable;
- disable;
- maintenance;
- add/remove node to/from access profile;
- bulk add/remove node for users;
- replace node A with node B;
- safe delete;
- force delete.

### Safe delete

`DELETE /admin/nodes/{id}`:

- если node нигде не используется - soft-delete;
- если node используется пользователями, primary-node ссылками или профилями - возвращает `409` с понятной причиной;
- физически VPS и Xray на VPS не удаляются.

Типовая ошибка:

```text
Сервер используется в профилях/пользователях. Сначала отключите сервер или используйте принудительное удаление.
```

### Force delete

`DELETE /admin/nodes/{id}?force=true`:

- отвязывает node от пользователей;
- убирает node из профилей;
- очищает `primary_node_id`;
- применяет cleanup config на node, если возможно;
- помечает node как `deleted`;
- скрывает node из списков.

### Replace node

`POST /admin/nodes/{old_id}/replace`:

```json
{
  "new_node_id": 123
}
```

Операция:

1. Находит пользователей и профили с old node.
2. Убирает old node.
3. Добавляет new node.
4. Если old node был primary, ставит new node primary.
5. Применяет config на affected old/new nodes.
6. Возвращает summary: сколько users/profiles изменено и apply status.

## Xray managed modes

### `akfa_owned`

AKFA владеет Xray config полностью. Этот режим используется для новых VPS, где Xray установлен через панель.

### `imported_safe`

Режим безопасного импорта существующего Xray:

- probe только read-only;
- import не переустанавливает Xray;
- AKFA сохраняет baseline config/inbound;
- unknown clients сохраняются;
- AKFA добавляет/обновляет/удаляет только своих clients;
- перед записью config создается backup.

## Xray probe/import

Probe выполняет только read-only команды:

```bash
command -v xray
xray version
systemctl is-active xray
systemctl is-enabled xray
test -f /usr/local/etc/xray/config.json
cat /usr/local/etc/xray/config.json
```

Probe определяет:

- установлен ли Xray;
- версия Xray;
- service active/enabled;
- config exists;
- JSON valid;
- VLESS inbound;
- Reality settings;
- port;
- SNI/serverNames;
- dest;
- privateKey;
- publicKey, если можно получить;
- shortIds;
- stream network/security;
- clients count.

Если publicKey нельзя получить из privateKey через `xray x25519 -i`, UI показывает поле `Reality publicKey`. Import disabled, пока обязательный publicKey пустой.

## Xray install

Real install работает как background job:

```text
POST /admin/nodes/{id}/install
```

Быстро возвращает:

```json
{
  "job_id": "...",
  "status": "running",
  "current_step": "..."
}
```

Frontend poll:

```text
GET /admin/node-actions/{job_id}
```

Job логирует этапы:

- подключение к VPS;
- apt/dpkg check;
- package update;
- dependencies install;
- Xray install;
- Reality config generation;
- config test;
- service start/restart;
- status check.

Две установки на одной node одновременно не запускаются: backend возвращает existing job или controlled conflict.

## SSH command timeouts

Команды разделены по типам:

- read-only/probe - короткие timeout;
- install/apply mutating commands - длиннее;
- apt-get update/install - достаточно длинные, чтобы не убивать нормальную установку;
- systemctl/xray config test - отдельные timeout.

Если SSH-команда получает timeout, backend закрывает remote channel и не оставляет долгий процесс бесконтрольно висеть. При apt/dpkg lock backend показывает понятную ошибку, а lock-файлы не удаляются вслепую.

## Apply-config

Apply-config:

- берет active HWID devices;
- включает только active users;
- исключает expired/traffic-limited/disabled/deleted users;
- исключает revoked devices;
- исключает devices без `hwid_hash`;
- применяет только на affected nodes;
- перед записью делает backup config;
- проверяет Xray config;
- restart/reload service;
- сохраняет apply status/error.

Client в Xray:

```json
{
  "id": "<device.uuid>",
  "email": "akfa_user_<user_id>_device_<device_id>",
  "flow": "xtls-rprx-vision"
}
```

В `imported_safe` unknown/non-AKFA clients сохраняются.

## HWID hard mode

HWID hard mode - production-режим ограничения устройств.

Правила:

- `x-hwid` обязателен для subscription;
- без `x-hwid` config не выдается;
- IP не входит в идентификацию;
- User-Agent не входит в идентификацию;
- install-token flow не используется;
- raw HWID не хранится;
- новый HWID сверх лимита не получает config;
- тот же HWID получает тот же active device config;
- revoked device не получает config.

Headers:

| Header | Обязателен | Назначение |
| --- | --- | --- |
| `x-hwid` | Да | Уникальный ID устройства/установки клиента. |
| `x-device-os` | Нет | ОС или платформа. |
| `x-ver-os` | Нет | Версия ОС. |
| `x-device-model` | Нет | Модель устройства. |
| `x-app-version` | Нет | Версия приложения. |
| `user-agent` | Нет | Metadata клиента. |

Формула:

```text
normalized_x_hwid = trim(x-hwid), remove whitespace, lowercase
hwid_hash = sha256(normalized_x_hwid)
```

Без `x-hwid`:

```text
HTTP 403
x-hwid-limit: true
x-hwid-not-supported: true

Ваш клиент не поддерживает ограничение устройств
```

Сверх лимита:

```text
HTTP 403
x-hwid-limit: true
x-hwid-max-devices-reached: true

Превышен лимит устройств
```

## Device lifecycle

Обычное отключение устройства не является пожизненным баном.

Удаление/отключение device:

- устройство перестает быть active;
- слот освобождается;
- UUID удаляется из Xray config через auto apply;
- old `/sub/device/{device_token}` больше не работает;
- тот же HWID может заново зарегистрироваться через `/sub/{user_token}`, если лимит позволяет.

Admin и public self-service removal используют одинаковую бизнес-семантику обычного disconnect/remove, а не hard-ban.

## Public connect page

URL:

```text
/connect/{user_token}
```

Страница публичная, без admin layout и без логина.

Показывает:

- имя пользователя;
- статус подписки;
- устройства `active/device_limit`;
- выбор устройства;
- инструкцию;
- subscription URL;
- QR-код;
- кнопку copy;
- простой список устройств;
- кнопку отключения устройства.

На странице не показываются технические слова `HWID`, `x-hwid`, `headers`.

Платформы:

Android / Happ:

```text
/sub/{user_token}?platform=android&client=happ&format=raw
```

iPhone / iPad / Happ:

```text
/sub/{user_token}?platform=iphone&client=happ&format=raw
```

Windows / FClashX:

```text
/sub/{user_token}?platform=windows&client=fclashx&format=clash
```

macOS / FClashX/Clash:

```text
/sub/{user_token}?platform=macos&client=fclashx&format=clash
```

`install=` links не используются.

Страница обновляет состояние без reload:

- после удаления устройства;
- периодическим polling;
- если админ изменил лимит;
- если устройство появилось через VPN-клиент;
- если устройство удалено из админки.

## Public device removal

Endpoint:

```text
DELETE /public/connect/{user_token}/devices/{device_id}
```

Работает без admin login, но только внутри валидного `user_token`.

Поведение:

- можно удалить только устройство данного пользователя;
- повторное удаление идемпотентно;
- после удаления выполняется auto apply-config;
- если apply-config не удался, backend возвращает controlled error, а состояние не должно превращаться в рассинхрон.

## Subscription endpoints

### `GET /sub/{user_token}`

Основной endpoint.

Query:

| Query | Пример | Значение |
| --- | --- | --- |
| `platform` | `android`, `windows`, `iphone`, `macos` | Metadata/display name. |
| `client` | `happ`, `fclashx`, `streisand`, `v2rayn` | Metadata/display name. |
| `format` | `raw`, `base64`, `clash`, `singbox` | Формат ответа. |

Первый запрос нового HWID:

1. Проверяет user active/not expired/traffic.
2. Проверяет device limit.
3. Создает device.
4. Применяет config на affected nodes.
5. Возвращает subscription только после успешного apply.

Existing HWID:

- не делает apply-config на каждый refresh;
- возвращает существующий config.

### `GET /sub/device/{device_token}`

Legacy/device-specific endpoint.

В hard mode:

- требует `x-hwid`;
- проверяет, что hash совпадает с device;
- не создает новые devices;
- revoked/disconnected device получает 403/404.

### Deprecated install-link

```text
POST /public/connect/{user_token}/install-link
```

Возвращает `410 Gone`. Install-token activation не участвует в production flow.

## Subscription formats

### Raw

```text
GET /sub/{user_token}?format=raw
```

Default format тоже raw.

```text
Content-Type: text/plain; charset=utf-8
```

VLESS URI содержит:

- `encryption=none`;
- `type=tcp`;
- `security=reality`;
- `pbk=<node.reality_public_key>`;
- `fp=chrome` или node fingerprint;
- `sni=<node.sni>`;
- `sid=<node.short_id>`;
- `flow=xtls-rprx-vision`;
- `device.uuid`;
- clean server remark.

### Base64

```text
GET /sub/{user_token}?format=base64
```

Возвращает base64 от raw VLESS lines.

### Clash

```text
GET /sub/{user_token}?platform=windows&client=fclashx&format=clash
```

Headers:

```text
Content-Type: application/yaml; charset=utf-8
profile-title: akfa vpn
Content-Disposition: attachment; filename="akfa-vpn.yaml"
```

YAML:

```yaml
proxies:
  - name: "AKFA 🇳🇱 Нидерланды"
    type: vless
    server: "SERVER_IP"
    port: 443
    uuid: "<device.uuid>"
    network: tcp
    tls: true
    udp: true
    flow: xtls-rprx-vision
    servername: "www.googletagmanager.com"
    client-fingerprint: chrome
    reality-opts:
      public-key: "<node.reality_public_key>"
      short-id: "<node.short_id>"
proxy-groups:
  - name: "akfa vpn"
    type: select
    proxies:
      - "AKFA 🇳🇱 Нидерланды"
rules:
  - MATCH,akfa vpn
```

### sing-box

```text
GET /sub/{user_token}?format=singbox
```

Возвращает sing-box JSON с UUID конкретного device.

## Server names and emoji flags

Profile/subscription name:

```text
akfa vpn
```

Server names:

```text
AKFA 🇳🇱 Нидерланды
AKFA 🇩🇪 Германия
AKFA 🇫🇮 Финляндия
```

Если несколько серверов одной страны:

```text
AKFA 🇳🇱 Нидерланды 1
AKFA 🇳🇱 Нидерланды 2
```

Поддерживаемые aliases находятся в `backend/app/services/xray_config.py` в `COUNTRY_NAMES`.

Примеры:

- `nl`, `netherlands`, `holland`, `нидерланды`, `голландия`;
- `de`, `germany`, `deutschland`, `германия`;
- `fi`, `finland`, `финляндия`;
- `ie`, `ireland`, `ирландия`;
- `fr`, `france`, `франция`;
- `pl`, `poland`, `польша`;
- `se`, `sweden`, `швеция`;
- `no`, `norway`, `норвегия`;
- `ch`, `switzerland`, `швейцария`;
- `at`, `austria`, `австрия`;
- `cz`, `czech`, `czechia`, `чехия`;
- `es`, `spain`, `испания`;
- `it`, `italy`, `италия`;
- `us`, `usa`, `united states`, `america`, `сша`, `америка`;
- `ca`, `canada`, `канада`;
- `uk`, `gb`, `united kingdom`, `great britain`, `britain`, `англия`, `великобритания`;
- `tr`, `turkey`, `турция`;
- `ae`, `uae`, `united arab emirates`, `оаэ`, `эмираты`;
- `jp`, `japan`, `япония`;
- `sg`, `singapore`, `сингапур`;
- `kr`, `korea`, `south korea`, `корея`, `южная корея`.

Если location не распознана, используется fallback на `node.location` или `node.name`.

## Dashboard traffic по серверам

В блоке Dashboard `Данные по серверам` трафик считается как server-level accounting.

Важно:

- трафик node не считается из текущего списка пользователей;
- удаление user/device не уменьшает исторический traffic node;
- перенос пользователя между nodes не пересчитывает историю задним числом;
- один user на нескольких nodes не размазывает общий user traffic на все nodes.

Как работает:

1. При сборе с node backend получает Xray counters.
2. Считает delta относительно предыдущих counters этой node.
3. Сохраняет delta в `traffic_snapshots` с `node_id`.
4. Для чистого node-level delta `vpn_user_id` может быть `NULL`.
5. Dashboard показывает `SUM(delta)` по `node_id` и выбранному периоду.

Периоды UI:

- Сегодня;
- 7 дней;
- Этот месяц;
- Всё время.

Источник на Dashboard:

- `Xray node stats`, если использованы inbound/node counters;
- `Node traffic`, если отображаются сохраненные deltas.

`Users sum` больше не используется для server cards.

## Traffic analytics по пользователям

Пользовательская аналитика остается отдельной:

- StatsService читает `user>>>...>>>traffic`;
- email format: `akfa_user_<user_id>_device_<device_id>`;
- device traffic обновляет device counters;
- user traffic = сумма devices;
- online device = delta за online window;
- online user = хотя бы одно online device.

Это нужно для страницы аналитики, лимитов пользователя и online status.

## Backup and restore

Backup archive содержит:

- admins;
- profiles;
- departments;
- nodes;
- users;
- devices;
- user-node links;
- user-node traffic;
- traffic snapshots;
- audit logs;
- rendered Xray configs per node.

Backup содержит чувствительные данные:

- subscription tokens;
- node parameters;
- Reality keys;
- encrypted SSH credentials.

Храните archive безопасно.

## Audit log

Audit фиксирует критичные admin actions:

- create/update/delete users;
- device revoke/reset;
- node create/update/install/import/apply;
- node lifecycle/bulk actions;
- backup restore;
- traffic collection.

## Admin UI pages

Панель содержит:

- Dashboard;
- Servers;
- Add VPS;
- Install Xray;
- Departments;
- Access Profiles;
- VPN Users;
- Bulk Import;
- Traffic Analytics;
- Backup;
- Audit Log;
- Admin Settings.

### Users page

Функции:

- создание пользователя;
- таблица пользователей;
- фильтры;
- devices label `1/5`;
- online status;
- traffic summary;
- connect link;
- QR connect link;
- user detail;
- edit user settings;
- device list;
- revoke/remove device;
- reset all devices.

Create/update user показывает process popup:

- создание пользователя;
- применение конфигурации;
- success;
- partial apply warning;
- error.

### Server detail

Функции:

- summary;
- status;
- Xray info;
- install log;
- verify;
- dry-run;
- install;
- apply config;
- import/probe;
- edit;
- config preview;
- enable/disable/maintenance;
- bulk add/remove users;
- add/remove profile;
- replace node;
- safe delete;
- force delete.

## CLI

Seed admin:

```bash
python -m app.cli seed-admin --email ADMIN_EMAIL --password-env AKFA_ADMIN_PASSWORD --reset-password
```

Seed admin with TOTP:

```bash
python -m app.cli seed-admin --email ADMIN_EMAIL --password-env AKFA_ADMIN_PASSWORD --reset-password --enable-totp
```

Через Docker:

```bash
docker compose exec -T -e AKFA_ADMIN_PASSWORD backend python -m app.cli seed-admin --email ADMIN_EMAIL --password-env AKFA_ADMIN_PASSWORD --reset-password
```

## API map

### Auth

```text
POST /auth/login
POST /auth/2fa/verify
POST /auth/2fa
POST /auth/2fa/setup/start
POST /auth/2fa/setup/confirm
POST /auth/2fa/disable
GET  /auth/me
POST /auth/logout
```

### Admin dashboard

```text
GET /admin/dashboard
```

### Departments

```text
GET  /admin/departments
POST /admin/departments
GET  /admin/departments/{id}
PUT  /admin/departments/{id}
```

### Access profiles

```text
GET    /admin/access-profiles
POST   /admin/access-profiles
PUT    /admin/access-profiles/{id}
DELETE /admin/access-profiles/{id}
POST   /admin/seed/default-profile
```

### Nodes

```text
GET    /admin/nodes
GET    /admin/nodes/metrics?period=all
POST   /admin/nodes
GET    /admin/nodes/{id}
PUT    /admin/nodes/{id}
DELETE /admin/nodes/{id}
DELETE /admin/nodes/{id}?force=true

POST   /admin/nodes/{id}/check
POST   /admin/nodes/{id}/dry-run
POST   /admin/nodes/{id}/verify
POST   /admin/nodes/{id}/install
GET    /admin/node-actions/{job_id}

POST   /admin/nodes/probe
POST   /admin/nodes/{id}/probe
POST   /admin/nodes/{id}/import-xray
POST   /admin/nodes/{id}/apply-config
GET    /admin/nodes/{id}/config-preview

POST   /admin/nodes/{id}/disable
POST   /admin/nodes/{id}/enable
POST   /admin/nodes/{id}/maintenance
POST   /admin/nodes/{id}/profiles/add
POST   /admin/nodes/{id}/profiles/remove
POST   /admin/nodes/{id}/users/add
POST   /admin/nodes/{id}/users/remove
POST   /admin/nodes/{id}/replace
```

### Users and devices

```text
GET    /admin/users
POST   /admin/users
GET    /admin/users/{id}
PUT    /admin/users/{id}
DELETE /admin/users/{id}

POST /admin/users/{id}/enable
POST /admin/users/{id}/disable
POST /admin/users/{id}/regenerate-uuid
POST /admin/users/{id}/regenerate-subscription
POST /admin/users/{id}/reset-traffic

GET   /admin/users/{id}/devices
PATCH /admin/users/{id}/devices/{device_id}
POST  /admin/users/{id}/devices/{device_id}/revoke
POST  /admin/users/{id}/devices/reset

POST /admin/users/import
GET  /admin/users/{id}/subscription-preview
```

### Traffic

```text
POST /admin/traffic/collect/{node_id}
POST /admin/traffic/collect-now
POST /admin/traffic/collect-background
POST /admin/traffic/debug-collect
GET  /admin/traffic/overview
GET  /admin/traffic/snapshots
```

### Backup and audit

```text
GET  /admin/audit-log
GET  /admin/backup/export
POST /admin/backup/import
```

### Public

```text
GET    /public/connect/{user_token}
DELETE /public/connect/{user_token}/devices/{device_id}
POST   /public/connect/{user_token}/install-link  # deprecated, returns 410

GET /sub/{user_token}
GET /sub/device/{device_token}
```

## Manual checks

### Проверка HWID limit 2/2

Без HWID:

```bash
curl -i "http://localhost:8000/sub/{user_token}?platform=android&client=happ&format=raw"
```

Ожидаемо:

```text
403 Ваш клиент не поддерживает ограничение устройств
```

Первое устройство:

```bash
curl -i \
  -H "x-hwid: phone-1" \
  -H "x-device-os: Android" \
  -H "x-device-model: SM-A165F" \
  -H "x-ver-os: 15" \
  "http://localhost:8000/sub/{user_token}?platform=android&client=happ&format=raw"
```

Второе устройство:

```bash
curl -i \
  -H "x-hwid: laptop-1" \
  -H "x-device-os: Windows" \
  -H "x-device-model: Windows 11 Pro" \
  "http://localhost:8000/sub/{user_token}?platform=windows&client=fclashx&format=clash"
```

Третье устройство при лимите 2:

```bash
curl -i \
  -H "x-hwid: phone-2" \
  "http://localhost:8000/sub/{user_token}?platform=android&client=happ&format=raw"
```

Ожидаемо:

```text
403 Превышен лимит устройств
```

### Проверка FClashX

```bash
curl -i \
  -H "x-hwid: windows-device-1" \
  -H "x-device-os: Windows" \
  -H "x-device-model: Windows 11 Pro" \
  "http://localhost:8000/sub/{user_token}?platform=windows&client=fclashx&format=clash"
```

Проверить:

- `Content-Type: application/yaml; charset=utf-8`;
- `profile-title: akfa vpn`;
- `Content-Disposition: attachment; filename="akfa-vpn.yaml"`;
- YAML содержит `proxies`, `proxy-groups`, `rules`;
- proxy-group называется `akfa vpn`;
- proxy names чистые, без username/token/UUID.

### Проверка node traffic Dashboard

1. Запустить сбор traffic.
2. Открыть Dashboard.
3. В `Данные по серверам` выбрать период.
4. Убедиться, что source не `Users sum`.
5. Удалить user/device.
6. Проверить, что historical node traffic не уменьшился.

## Development backend

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
alembic upgrade head
pytest
uvicorn app.main:app --reload
```

На Linux/macOS activation:

```bash
source .venv/bin/activate
```

Alembic:

```bash
cd backend
alembic revision --autogenerate -m "change description"
alembic upgrade head
alembic downgrade -1
```

## Development frontend

```bash
cd frontend
npm install
npm run build
npm run dev
```

Vite dev server:

```text
http://localhost:5173
```

Если используете Vite dev server, добавьте origin:

```env
CORS_ORIGINS=["http://localhost:5173","http://localhost:8080"]
```

## Tests

Backend:

```bash
docker compose exec -T backend pytest
```

Frontend:

```bash
docker compose exec -T frontend npm run build
```

Full acceptance:

```bash
docker compose build --progress=plain
docker compose up -d
docker compose ps
docker compose exec -T backend pytest
docker compose exec -T frontend npm run build
curl http://localhost:8000/health
curl -I http://localhost:8080
```

Local:

```bash
python -m pytest backend/tests -q
cd frontend
npm run build
```

## Production checklist

Перед production:

- заменить `SESSION_SECRET`;
- заменить `ENCRYPTION_KEY`;
- включить HTTPS;
- выставить `SECURE_COOKIES=true`;
- указать production `SUBSCRIPTION_BASE_URL`;
- ограничить admin panel firewall или VPN;
- включить TOTP для администраторов;
- настроить backup PostgreSQL volume;
- проверить CORS origins;
- не открывать Xray API наружу;
- убедиться, что Xray API на VPS слушает localhost;
- проверить SSH-доступы;
- проверить install на тестовой VPS;
- проверить imported_safe на существующем Xray;
- проверить `/connect/{user_token}`;
- проверить `x-hwid` на реальном клиенте;
- проверить `format=clash` в FClashX;
- проверить auto apply-config после создания device;
- проверить Dashboard node traffic после сбора stats.

## v0.1 VPS operations

Все production-шаблоны используют placeholders:

- `PANEL_DOMAIN`;
- `PUBLIC_CONNECT_DOMAIN`;
- `DOCS_DOMAIN`;
- `SERVER_IP`;
- `ADMIN_EMAIL`.

Не храните реальные домены, IP, пароли, токены, private keys, cookies и backup archives в git.

### One-command install flow

На чистом Ubuntu VPS после публикации репозитория на GitHub:

```bash
sudo GIT_REPO=REPO_URL \
  PANEL_DOMAIN=panel.example.com \
  PUBLIC_CONNECT_DOMAIN=panel.example.com \
  DOCS_DOMAIN=help.example.com \
  ADMIN_EMAIL=ADMIN_EMAIL \
  SSL_EMAIL=ADMIN_EMAIL \
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/ORG/REPO/main/scripts/install.sh)"
```

Если не хотите pipe-to-shell, используйте ручной flow ниже.

### Manual install flow

```bash
sudo apt-get update
sudo apt-get install -y git
sudo git clone REPO_URL /opt/akfa-vpn
cd /opt/akfa-vpn
sudo PANEL_DOMAIN=panel.example.com \
  PUBLIC_CONNECT_DOMAIN=panel.example.com \
  DOCS_DOMAIN=help.example.com \
  ADMIN_EMAIL=ADMIN_EMAIL \
  scripts/install.sh
```

Installer:

- устанавливает Docker, docker compose plugin, nginx, certbot;
- `PUBLIC_CONNECT_DOMAIN` может совпадать с `PANEL_DOMAIN`; nginx `server_name` будет deduplicated;
- спрашивает main panel admin email и password с подтверждением;
- если база знаний включена, спрашивает docs admin email и password с подтверждением;
- password prompts скрытые, пароли не печатаются в финальном output;
- генерирует `.env` с новыми `POSTGRES_PASSWORD`, `SESSION_SECRET`, `ENCRYPTION_KEY`;
- пишет main panel `ADMIN_EMAIL` в `/opt/akfa-vpn/.env`, но не хранит main panel admin password после bootstrap;
- не перезаписывает существующий `.env` без подтверждения;
- сначала ставит валидный HTTP-only nginx config;
- запускает `postgres`, ждёт `pg_isready`, затем выполняет Alembic migrations один раз через одноразовый backend container;
- запускает `backend` и `frontend`;
- создаёт initial admin через `ADMIN_EMAIL` только после успешного `/health`;
- ставит backend watchdog timer только после successful backend health;
- если включена база знаний, генерирует корректный docs `.env`, создаёт writable `data/uploads` для service user и проверяет `/` + `/admin/login`;
- копирует стартовые файлы скачивания из `akfa-docs-platform/seed-downloads` в `/opt/akfa-downloads`;
- опционально выпускает TLS через `certbot certonly --webroot` с retry/backoff и включает HTTPS config только если сертификаты реально созданы;
- завершает install с success только после проверки `postgres/backend/frontend`, backend health, frontend status, docs health если docs установлены, `nginx -t` и watchdog status.

Production URLs после успешного install:

- main panel: `https://PANEL_DOMAIN`;
- docs admin: `https://DOCS_DOMAIN/admin/login`.

Для non-interactive install задайте переменные окружения:

- `ADMIN_EMAIL`;
- `ADMIN_PASSWORD`;
- `DOCS_ADMIN_EMAIL`;
- `DOCS_ADMIN_PASSWORD`.

Если обязательные password variables не заданы и stdin не интерактивный, install завершится ошибкой. Пароли должны быть не короче 12 символов; они не выводятся в install output.

### Update

Перед первым обновлением старого VPS убедитесь, что `/opt/akfa-vpn/.env` содержит `POSTGRES_PASSWORD`, а пароль в `DATABASE_URL` совпадает с ним. Новый `docker-compose.yml` специально не использует fallback-пароль для production.

```bash
cd /opt/akfa-vpn
sudo scripts/update.sh
```

Update script сначала запускает backup, затем делает `git pull --ff-only`, пересобирает `backend` и `frontend`, запускает `postgres`, выполняет Alembic migrations один раз, запускает `backend/frontend`, не удаляет volumes и проверяет `/health`.

Update также читает `akfa-docs-platform/seed-downloads/downloads.manifest.json` и копирует новые seed downloads в `/opt/akfa-downloads`, но не затирает уже существующие файлы. Для принудительной замены seed-файлов используйте:

```bash
sudo OVERWRITE_SEED_DOWNLOADS=yes scripts/update.sh
```

### Backup

```bash
sudo /opt/akfa-vpn/scripts/backup.sh
```

Backup складывается в `/opt/akfa-backups`, содержит PostgreSQL dump, `.env`, `docker-compose.yml` и deploy templates. Ротация по умолчанию: 14 дней.

### Doctor

```bash
sudo /opt/akfa-vpn/scripts/doctor.sh
```

Doctor показывает `docker compose ps`, backend health, frontend status, `nginx -t`, disk space, статус backend watchdog и последние backend/watchdog logs.

### Reset failed test install

Используйте только для тестового VPS, где можно удалить текущую AKFA-установку. Команды ограничены путями AKFA и не трогают другие nginx/systemd/Docker данные.

```bash
cd /opt/akfa-vpn 2>/dev/null && sudo docker compose down --volumes --remove-orphans || true

sudo systemctl disable --now akfa-backend-watchdog.timer 2>/dev/null || true
sudo rm -f /etc/systemd/system/akfa-backend-watchdog.service
sudo rm -f /etc/systemd/system/akfa-backend-watchdog.timer
sudo rm -f /usr/local/bin/akfa-backend-watchdog
sudo rm -f /etc/akfa/backend-watchdog.env
sudo systemctl disable --now akfa-docs-platform 2>/dev/null || true
sudo rm -f /etc/systemd/system/akfa-docs-platform.service
sudo systemctl daemon-reload

sudo rm -f /etc/nginx/sites-enabled/akfa-panel.conf
sudo rm -f /etc/nginx/sites-enabled/akfa-panel-ssl.conf
sudo rm -f /etc/nginx/sites-enabled/akfa-docs.conf
sudo rm -f /etc/nginx/sites-enabled/akfa-docs-ssl.conf
sudo rm -f /etc/nginx/sites-available/akfa-panel.conf
sudo rm -f /etc/nginx/sites-available/akfa-panel-ssl.conf
sudo rm -f /etc/nginx/sites-available/akfa-docs.conf
sudo rm -f /etc/nginx/sites-available/akfa-docs-ssl.conf
sudo nginx -t && sudo systemctl reload nginx

sudo docker image rm akfa-vpn-backend akfa-vpn-frontend 2>/dev/null || true
cd /opt
sudo rm -rf /opt/akfa-vpn
sudo rm -rf /opt/akfa-docs-platform
```

После reset повторите clean install:

```bash
cd /opt
git clone REPO_URL akfa-vpn
cd /opt/akfa-vpn
chmod +x scripts/*.sh
sudo ./scripts/install.sh
```

## Backend self-healing

Production self-healing реализован через systemd timer:

- script: `scripts/backend-watchdog.sh`;
- service: `deploy/systemd/akfa-backend-watchdog.service`;
- timer: `deploy/systemd/akfa-backend-watchdog.timer`;
- env template: `deploy/systemd/backend-watchdog.env.example`.

Поведение:

- раз в минуту выполняется bounded check `HEALTH_URL`, по умолчанию `http://127.0.0.1:8000/health`;
- `curl` ограничен `CONNECT_TIMEOUT` и `MAX_TIME`;
- один сбой не рестартит backend;
- restart выполняется только после `FAIL_THRESHOLD` последовательных сбоев, по умолчанию 3;
- есть cooldown между рестартами;
- рестартует только docker compose service `backend`;
- не удаляет контейнеры, volumes, PostgreSQL data или backups;
- пишет лог в `/var/log/akfa-backend-watchdog.log` и syslog.

Команды:

```bash
sudo systemctl status akfa-backend-watchdog.timer
sudo /usr/local/bin/akfa-backend-watchdog status
sudo journalctl -u akfa-backend-watchdog.service -n 100 --no-pager
```

## Nginx maintenance fallback

Шаблоны:

- panel HTTP nginx: `deploy/nginx/panel.conf`;
- panel HTTPS nginx: `deploy/nginx/panel-ssl.conf`;
- docs HTTP nginx: `deploy/nginx/docs.conf`;
- docs HTTPS nginx: `deploy/nginx/docs-ssl.conf`;
- static fallback page: `deploy/static/maintenance.html`.

`panel.conf` проксирует в frontend upstream `127.0.0.1:8080` и показывает `/maintenance.html` для `502/503/504`. Maintenance page отдаётся с `Cache-Control: no-store`.

Install сначала активирует только HTTP templates. HTTPS templates включаются только после успешного `certbot certonly --webroot` и проверки наличия `/etc/letsencrypt/live/CERT_NAME/fullchain.pem`. По умолчанию `CERT_NAME` равен `PANEL_DOMAIN`. Если certbot временно занят или не смог выпустить сертификат, install оставляет nginx в валидном HTTP-only режиме и печатает команду повторного выпуска SSL.

Если frontend загрузился, но backend API недоступен, React UI показывает собственный экран:

```text
Панель временно перезапускается
Выполняется автоматическое восстановление сервиса.
Обновите страницу через 1–2 минуты.
```

HTTP `401/403` остаются обычной auth-логикой и не считаются maintenance.

## Docs Downloads

Стартовые файлы скачивания для базы знаний описаны manifest-файлом:

```text
akfa-docs-platform/seed-downloads/
  README.md
  downloads.manifest.json
  <binary files>
```

Manifest задаёт стабильный публичный URL, например:

```json
{
  "key": "happ-android",
  "title": "Happ для Android",
  "platform": "android",
  "filename": "happ-android.apk",
  "source": "Happ.apk",
  "publicPath": "/downloads/happ-android.apk"
}
```

На VPS файлы лежат в `/opt/akfa-downloads`. Nginx отдаёт их напрямую через `https://DOCS_DOMAIN/downloads/<filename>`, не проксируя в Next.js.

Стабильные ссылки для статей:

- `/downloads/happ-android.apk`;
- `/downloads/fclashx-windows.exe`;
- `/downloads/fclashx-macos.dmg`.

Обновить файл без SSH можно в docs admin: `https://DOCS_DOMAIN/admin/login`, раздел **Файлы / Загрузки**. Кнопка “Заменить” пишет новый файл поверх стабильного имени, поэтому public URL не меняется.

Разрешённые расширения задаются через `ALLOWED_DOWNLOAD_EXTENSIONS`, размер через `MAX_DOWNLOAD_MB`. Production install выставляет:

```env
DOWNLOADS_DIR=/opt/akfa-downloads
MAX_DOWNLOAD_MB=200
ALLOWED_DOWNLOAD_EXTENSIONS=apk,exe,dmg,zip,msi,pkg
```

Проверка после deploy:

```bash
curl -I https://DOCS_DOMAIN/downloads/happ-android.apk
curl -I https://DOCS_DOMAIN/downloads/fclashx-windows.exe
curl -I https://DOCS_DOMAIN/downloads/fclashx-macos.dmg
```

Если бинарники крупные для обычного Git, используйте Git LFS или release assets. Manifest всё равно должен оставаться в git, чтобы install/update понимали стабильные имена и публичные пути.

## Troubleshooting

### `403 Ваш клиент не поддерживает ограничение устройств`

Клиент не отправил `x-hwid`.

Обычный браузер обычно не отправляет этот header. Для ручного теста используйте `curl -H "x-hwid: ..."`.

### `403 Превышен лимит устройств`

У пользователя заполнен `device_limit`.

Решение:

- удалить/отключить старое устройство;
- увеличить лимит;
- использовать уже зарегистрированное устройство.

### `403 Ссылка подписки привязана к другому устройству`

Это относится к `/sub/device/{device_token}`.

Причина: device-specific token используется с другим HWID.

### FClashX: `cannot unmarshal !!str vless://...`

Клиент получил raw VLESS вместо Clash YAML.

Используйте:

```text
/sub/{user_token}?platform=windows&client=fclashx&format=clash
```

### Install Xray завершился на VPS, но UI получил 504

Текущая архитектура установки использует background job. Если где-то видите старый 504 behavior, проверьте, что frontend и backend пересобраны:

```bash
docker compose build --progress=plain
docker compose up -d
```

### Node delete показывает ошибку использования

Это normal safe-delete behavior.

Используйте:

- remove node from users/profiles;
- replace node;
- disable node;
- force delete, если нужно убрать все связи автоматически.

### Dashboard показывает 0 traffic

Dashboard server traffic берет только сохраненные node deltas. Нужно выполнить сбор stats с online node. Deltas могут появляться из Xray inbound/node counters или из user-email counters, сохраненных как исторические `traffic_snapshots` по `node_id`.

### Backend не стартует после миграций

Проверить:

```bash
docker compose logs --tail=200 backend
```

Частые причины:

- неверный `DATABASE_URL`;
- некорректный `ENCRYPTION_KEY`;
- конфликт Alembic revisions;
- PostgreSQL volume со старой несовместимой схемой.

## Security notes

- Raw `x-hwid` не хранится.
- SSH passwords/private keys шифруются Fernet key.
- `.env` нельзя коммитить.
- Production cookies должны быть secure.
- `SESSION_SECRET`, `ENCRYPTION_KEY`, `POSTGRES_PASSWORD` должны генерироваться отдельно для каждого VPS.
- `CORS_ORIGINS` в production должен содержать только `https://PANEL_DOMAIN` и при необходимости `https://PUBLIC_CONNECT_DOMAIN`.
- Admin session cookie `httpOnly`; CSRF cookie не `httpOnly`, потому что frontend отправляет его в `X-CSRF-Token`.
- Admin write endpoints требуют auth и CSRF.
- Upload/import endpoints ограничивают тип и размер файлов.
- Markdown/HTML в базе знаний проходит sanitization перед `dangerouslySetInnerHTML`.
- Nginx templates запрещают отдачу `.env`, `.git`, dumps, backups, SQLite DB и logs.
- Admin panel лучше закрывать firewall.
- TOTP желательно включить всем администраторам.
- Backup archive содержит sensitive данные.
- Xray API не должен быть доступен извне.
- В `imported_safe` unknown clients сохраняются.

Практический hardening не является обещанием абсолютной безопасности. Перед production рекомендуется отдельный security review инфраструктуры, firewall, SSH-доступов, TLS и backup storage.

## Git hygiene

Не коммитить:

- `.env`;
- `node_modules/`;
- `frontend/dist/`;
- `backend/.venv/`;
- `__pycache__/`;
- `.pytest_cache/`;
- временные backup archives;
- PostgreSQL dumps;
- SQLite DB/data/uploads;
- TLS private keys/certificates;
- `.next/`, `dist/`, `build/`;
- локальные IDE/cache files.

Полезно перед коммитом:

```bash
git status --short
git diff --stat
```

## License

This project is proprietary software. All rights are reserved.

You may not use, copy, modify, distribute, deploy, host, sell, sublicense, or create derivative works from this project without prior explicit written permission from the copyright holder.

See [LICENSE](./LICENSE).
