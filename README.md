# AKFA VPN

AKFA VPN - административная панель для управления корпоративным VPN-доступом через VPS-узлы с Xray-core, VLESS Reality и XTLS Vision.

Проект состоит из:

- backend: FastAPI, SQLAlchemy, Alembic, PostgreSQL;
- frontend: React, Vite, TypeScript, Tailwind CSS;
- инфраструктура: Docker Compose, PostgreSQL, Nginx для production-сборки frontend;
- управляемые VPN-узлы: Linux VPS с Xray-core, VLESS Reality inbound и StatsService.

Панель рассчитана на модель:

1. Администратор заводит VPN-пользователя и задает лимит устройств.
2. Пользователь получает одну публичную connect-ссылку `/connect/{user_token}`.
3. Пользователь выбирает платформу и добавляет subscription URL в поддерживаемый VPN-клиент.
4. VPN-клиент при запросе подписки обязан передать `x-hwid`.
5. Backend создает отдельное устройство для каждого нового HWID в пределах лимита.
6. Xray config строится из активных HWID-устройств, а не из общего UUID пользователя.

## Текущий статус архитектуры

AKFA использует HWID hard mode для ограничения устройств.

Это значит:

- устройство идентифицируется только по `x-hwid`;
- IP-адрес не является частью идентификации;
- User-Agent не является идентификатором устройства;
- install-token flow больше не используется в production subscription flow;
- без `x-hwid` рабочая подписка не выдается;
- новый `x-hwid` сверх `device_limit` не получает config;
- `/sub/device/{device_token}` тоже требует `x-hwid` и проверяет совпадение с устройством;
- raw `x-hwid` не хранится и не отдается в API/UI.

## Возможности

- Авторизация администратора через защищенные cookie-сессии.
- CSRF-защита для административных запросов.
- Двухфакторная авторизация TOTP для входа в админку.
- Управление отделами.
- Управление access profiles.
- Управление VPN-пользователями.
- Управление лимитом устройств пользователя.
- Self-service public connect page для пользователя.
- HWID hard mode device limit.
- Отдельный Xray UUID/client на каждое устройство.
- Xray config generation из активных HWID-устройств.
- Multi-node access: пользователь может иметь доступ к нескольким узлам.
- Primary node ordering для подписок.
- VLESS Reality subscription formats: raw, base64, Clash/Mihomo YAML, sing-box JSON.
- Проверка SSH-доступа к VPS.
- Dry-run установки Xray.
- Установка Xray.
- Read-only probe существующего Xray.
- Безопасный импорт существующего Reality inbound.
- `imported_safe` режим для уже существующих Xray-конфигов.
- Safe apply-config с сохранением unknown clients в imported_safe.
- Backup config перед записью на VPS.
- Сбор трафика через Xray StatsService.
- Агрегация трафика по устройствам в пользователя.
- Online status пользователя через активность устройств.
- Метрики VPS-узлов.
- Audit log административных действий.
- Backup/export и restore/import данных панели.

## Стек

### Backend

- Python 3.12 в Docker image.
- FastAPI.
- SQLAlchemy 2.
- Alembic.
- PostgreSQL.
- psycopg 3.
- AsyncSSH.
- cryptography/Fernet для шифрования SSH-секретов.
- pyotp для TOTP.
- pytest, pytest-asyncio.

### Frontend

- React 18.
- TypeScript.
- Vite.
- Tailwind CSS.
- lucide-react icons.
- qrcode.react.
- Nginx в production Docker image.

### Infrastructure

- Docker Compose.
- PostgreSQL 16 Alpine.
- Backend port: `8000`.
- Frontend port: `8080`.

## Структура проекта

```text
.
|-- backend/
|   |-- app/
|   |   |-- api/              # FastAPI routers: auth, admin/public entities
|   |   |-- core/             # config, security helpers
|   |   |-- db/               # SQLAlchemy session
|   |   |-- models/           # SQLAlchemy models
|   |   |-- schemas/          # Pydantic schemas
|   |   |-- services/         # Xray, SSH, HWID, traffic, backup, import logic
|   |   `-- main.py           # FastAPI app
|   |-- alembic/
|   |   `-- versions/         # Database migrations
|   |-- tests/                # Backend tests
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

## Быстрый запуск через Docker

1. Создать `.env` из примера:

```bash
cp .env.example .env
```

На Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

2. Для local/dev можно оставить значения из примера. Для production обязательно заменить секреты.

3. Собрать образы:

```bash
docker compose build --progress=plain
```

4. Запустить сервисы:

```bash
docker compose up -d
```

5. Создать администратора:

```bash
docker compose exec -T backend python -m app.cli seed-admin --email admin@example.com --password 'ChangeMe123!'
```

6. Проверить healthcheck:

```bash
curl http://localhost:8000/health
```

После запуска:

- Web UI: `http://localhost:8080`
- Backend API: `http://localhost:8000`
- Healthcheck: `http://localhost:8000/health`
- PostgreSQL внутри compose network: `postgres:5432`

## Переменные окружения

Файл `.env` не должен попадать в Git.

| Переменная | Пример | Назначение |
| --- | --- | --- |
| `ENVIRONMENT` | `production` | Режим окружения. |
| `DATABASE_URL` | `postgresql+psycopg://akfa:akfa@postgres:5432/akfa` | DSN PostgreSQL. |
| `SESSION_SECRET` | long random string | Секрет подписи cookie-сессий. |
| `ENCRYPTION_KEY` | Fernet key | Ключ для шифрования SSH-паролей и private keys. |
| `CORS_ORIGINS` | `["http://localhost:8080"]` | Разрешенные origins frontend. |
| `SECURE_COOKIES` | `false` для local, `true` для HTTPS | Включает secure cookies. |
| `SUBSCRIPTION_BASE_URL` | `https://panel.example.com` | Базовый публичный URL панели/подписок. |

Сгенерировать `ENCRYPTION_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Сгенерировать `SESSION_SECRET`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Администратор и TOTP

Создать super admin без TOTP:

```bash
docker compose exec -T backend python -m app.cli seed-admin --email admin@example.com --password 'ChangeMe123!'
```

Создать super admin с уже включенным TOTP:

```bash
docker compose exec -T backend python -m app.cli seed-admin --email admin@example.com --password 'ChangeMe123!' --enable-totp
```

Если используется `--enable-totp`, CLI напечатает TOTP secret. Его нужно добавить в Google Authenticator, Aegis, 1Password, Authy или другое приложение для одноразовых кодов.

В UI также есть flow:

1. Пароль администратора.
2. Если 2FA включена - ввод 6-значного TOTP.
3. Если 2FA требуется, но еще не настроена - экран QR/secret.
4. Вход в панель только после успешного кода.

В разделе настроек администратора можно включить или сбросить 2FA.

## Основные сущности

### Department

Отдел или группа пользователей. Используется для организационной структуры и фильтрации.

### Access profile

Профиль доступа задает клиентскую маршрутизацию:

- full tunnel;
- ru-direct;
- custom direct/blocked domains;
- traffic limit defaults;
- срок действия по умолчанию;
- список разрешенных nodes по умолчанию.

### VPN user

VPN-пользователь - это аккаунт доступа, который получает одну connect-ссылку.

Важные поля:

- `username`;
- `status`;
- `device_limit`;
- `traffic_limit_bytes`;
- `expires_at`;
- `access_profile_id`;
- `allowed_node_ids`;
- `primary_node_id`;
- `subscription_token`.

### VPN user device

Устройство пользователя. В HWID hard mode это отдельный Xray client.

Важные поля:

- `uuid` - UUID для Xray/VLESS client;
- `hwid_hash` - SHA-256 от нормализованного `x-hwid`;
- `hwid_masked` - безопасная маска HWID для UI;
- `status` - `active` или `revoked`;
- `platform`;
- `client_name`;
- `device_model`;
- `os_version`;
- `app_version`;
- `user_agent`;
- `created_ip`;
- `last_ip_address`;
- `last_subscribed_at`;
- traffic counters.

Raw `x-hwid` не хранится.

### VPS node

VPS-сервер с Xray-core.

Важные поля:

- SSH credentials;
- public host/IP;
- location;
- VLESS port;
- SNI;
- Reality private/public key;
- short ID;
- Xray config path;
- service name;
- managed mode: `akfa_owned` или `imported_safe`.

## HWID hard mode

HWID hard mode - основная production-логика ограничения устройств.

### Что должен отправлять VPN-клиент

Backend читает headers:

| Header | Обязателен | Назначение |
| --- | --- | --- |
| `x-hwid` | Да | Уникальный идентификатор установки/устройства. |
| `x-device-os` | Нет | ОС: `android`, `windows`, `iphone`, `macos` и т.п. |
| `x-ver-os` | Нет | Версия ОС. |
| `x-device-model` | Нет | Модель устройства. |
| `x-app-version` | Нет | Версия VPN-клиента. |
| `user-agent` | Нет | Описание клиента, только metadata. |

### Формула HWID hash

Backend нормализует HWID:

```text
normalized_x_hwid = trim(x-hwid), remove whitespace, lowercase
hwid_hash = sha256(normalized_x_hwid)
```

В базе хранится:

- `hwid_hash`;
- `hwid_masked`;
- metadata устройства.

Raw `x-hwid` не хранится.

### Что происходит без x-hwid

Если клиент запрашивает:

```text
GET /sub/{user_token}
```

без header `x-hwid`, backend возвращает:

```text
HTTP 403
Ваш клиент не поддерживает ограничение устройств
```

Response headers:

```text
x-hwid-limit: true
x-hwid-not-supported: true
```

Device не создается. Config не отдается.

### Новый x-hwid ниже лимита

Если пользователь активен, не истек, трафик не превышен, и `active_devices_count < device_limit`:

1. Backend создает `vpn_user_device`.
2. Генерирует новый `device.uuid`.
3. Сохраняет `hwid_hash` и metadata.
4. Делает safe apply-config на доступных nodes пользователя.
5. Возвращает подписку с UUID именно этого device.

Response headers:

```text
x-hwid-limit: true
x-hwid-active: true
```

### Тот же x-hwid повторно

Если `hwid_hash` уже есть у активного устройства этого пользователя:

1. Backend обновляет `last_seen_at`, `last_subscribed_at`, `last_ip_address`.
2. Возвращает config того же device.
3. Количество устройств не увеличивается.

### Новый x-hwid сверх лимита

Если `active_devices_count >= device_limit`, backend возвращает:

```text
HTTP 403
Превышен лимит устройств
```

Response headers:

```text
x-hwid-limit: true
x-hwid-max-devices-reached: true
```

Device не создается. Config не отдается.

### Revoked device

Если `hwid_hash` найден, но устройство отключено:

```text
HTTP 403
Устройство отключено
```

### IP-адрес

IP не входит в идентификацию устройства.

Это сделано специально: пользователь может перейти с домашнего Wi-Fi на мобильный интернет, и подписка должна продолжить работать.

IP используется только как metadata:

- `created_ip`;
- `ip_address`;
- `last_ip_address`.

## Public connect page

Публичная страница:

```text
/connect/{user_token}
```

Она не требует логин/пароль.

На странице пользователь видит:

- AKFA VPN;
- имя пользователя;
- статус подписки;
- срок действия;
- трафик;
- количество устройств: например `1/5`;
- выбор платформы;
- subscription URL;
- QR-код;
- инструкции подключения;
- список уже созданных устройств без секретов.

### Платформы

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

macOS / Happ:

```text
/sub/{user_token}?platform=macos&client=happ&format=raw
```

macOS / FClashX:

```text
/sub/{user_token}?platform=macos&client=fclashx&format=clash
```

На странице есть предупреждение:

```text
Ограничение устройств работает только с клиентами, которые передают HWID.
Если приложение не поддерживает HWID, подписка не будет выдана.
```

### Важно

Если открыть subscription URL в обычном браузере, скорее всего будет:

```text
403 Ваш клиент не поддерживает ограничение устройств
```

Это ожидаемое поведение. Браузер не передает `x-hwid`.

## Subscription endpoints

### `GET /sub/{user_token}`

Основной endpoint.

Query:

| Query | Значения | Назначение |
| --- | --- | --- |
| `platform` | `android`, `windows`, `iphone`, `macos` | Платформа для metadata/display name. |
| `client` | `happ`, `fclashx`, `streisand`, `v2rayn`, etc. | Клиент для metadata/display name. |
| `format` | `raw`, `base64`, `clash`, `singbox` | Формат подписки. |

Headers:

```text
x-hwid: unique-device-id
x-device-os: Android
x-ver-os: 14
x-device-model: Samsung S23
x-app-version: 3.18.3
user-agent: Happ/3.18.3/Android/...
```

### `GET /sub/device/{device_token}`

Legacy/device-specific endpoint оставлен, но в hard mode тоже требует `x-hwid`.

Поведение:

- без `x-hwid` - `403 Ваш клиент не поддерживает ограничение устройств`;
- wrong HWID - `403 Ссылка подписки привязана к другому устройству`;
- revoked device - `403 Устройство отключено`;
- matching HWID - config конкретного device.

Новые устройства через `/sub/device/{device_token}` никогда не создаются.

### Deprecated: `/public/connect/{user_token}/install-link`

Install-link flow отключен.

Endpoint возвращает:

```text
HTTP 410 Gone
Install-link flow deprecated. Используйте /sub/{user_token} с x-hwid.
```

## Subscription formats

### Raw

```text
GET /sub/{user_token}?format=raw
```

Ответ:

```text
Content-Type: text/plain; charset=utf-8
vless://...
vless://...
```

Raw также является default format.

### Base64

```text
GET /sub/{user_token}?format=base64
```

Ответ:

```text
Content-Type: text/plain; charset=utf-8
base64(raw VLESS lines)
```

### Clash / Mihomo

```text
GET /sub/{user_token}?platform=windows&client=fclashx&format=clash
```

Ответ:

```text
Content-Type: application/yaml; charset=utf-8
profile-title: akfa vpn
Content-Disposition: attachment; filename="akfa-vpn.yaml"
```

Структура YAML:

```yaml
proxies:
  - name: "AKFA 🇳🇱 Нидерланды"
    type: vless
    server: "203.0.113.10"
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

Если доступные nodes есть, backend возвращает sing-box JSON с UUID конкретного device.

## Naming rules

Название subscription/profile:

```text
akfa vpn
```

Названия серверов:

```text
AKFA 🇳🇱 Нидерланды
AKFA 🇩🇪 Германия
AKFA 🇫🇮 Финляндия
```

Если несколько серверов в одной стране:

```text
AKFA 🇳🇱 Нидерланды 1
AKFA 🇳🇱 Нидерланды 2
```

В названия нельзя включать:

- username;
- subscription token;
- device token;
- HWID;
- UUID;
- URL;
- timestamp.

## Xray node management

AKFA поддерживает два режима управления Xray node.

### `akfa_owned`

AKFA полностью владеет Xray config.

Подходит для новых VPS, где Xray устанавливается через панель.

### `imported_safe`

AKFA импортирует существующий Xray Reality inbound и работает аккуратно:

- probe выполняет read-only команды;
- import не делает destructive reinstall;
- unknown clients сохраняются;
- AKFA добавляет/обновляет только своих clients;
- перед записью config создается backup;
- apply-config не должен удалять чужих clients без явного takeover/replace режима.

## Read-only Xray probe/import

При добавлении или редактировании VPS можно выполнить probe.

Read-only команды:

```bash
command -v xray
xray version
systemctl is-active xray
systemctl is-enabled xray
test -f /usr/local/etc/xray/config.json
cat /usr/local/etc/xray/config.json
```

Probe ищет:

- установлен ли Xray;
- активен ли service;
- есть ли config;
- валидный ли JSON;
- есть ли VLESS inbound;
- есть ли Reality settings;
- port;
- SNI/serverName;
- shortIds;
- privateKey;
- publicKey;
- existing clients.

Если privateKey есть, backend пытается получить publicKey через:

```bash
xray x25519 -i <privateKey>
```

Если publicKey получить нельзя, UI показывает поле ручного ввода Reality publicKey.

## Xray config generation

Серверные clients строятся из:

```text
active vpn_user_devices with hwid_hash
```

Для каждого client:

```json
{
  "id": "<device.uuid>",
  "email": "akfa_user_<user_id>_device_<device_id>",
  "flow": "xtls-rprx-vision"
}
```

Legacy/no-HWID devices не попадают в production Xray config.

## Traffic and online

StatsService parser сопоставляет Xray stats по email:

```text
user>>>akfa_user_<user_id>_device_<device_id>>>>traffic
```

Логика:

- traffic device = counters конкретного device email;
- traffic user = сумма устройств пользователя;
- online device = есть delta traffic для device;
- online user = хотя бы одно устройство online.

## Admin UI

Админская панель содержит:

- dashboard;
- users;
- departments;
- access profiles;
- VPS nodes;
- traffic analytics;
- audit log;
- backup/restore;
- admin settings/TOTP.

### Users

На странице пользователей:

- форма создания пользователя сверху;
- таблица пользователей ниже;
- колонка `Устройства`: `1/5`, `2/5`, `7/10`;
- connect link;
- QR connect link;
- карточка пользователя;
- редактирование лимита устройств, профиля, срока действия, трафика, статуса;
- список устройств;
- revoke device;
- reset all devices.

Нельзя уменьшить `device_limit` ниже текущего количества active HWID devices:

```text
Нельзя установить лимит меньше текущего количества активных устройств.
```

### Device card

Админ видит:

- display name;
- device model;
- platform;
- OS version;
- app version;
- client name;
- masked HWID;
- status;
- last IP;
- last subscribed at;
- traffic;
- User-Agent.

## Типовой сценарий: новый пользователь

1. Админ создает VPN user.
2. Указывает `device_limit`, например `2`.
3. Копирует connect link:

```text
/connect/{user_token}
```

4. Пользователь открывает connect link.
5. Выбирает Android, iPhone, Windows или macOS.
6. Копирует subscription URL или сканирует QR.
7. Добавляет ссылку в HWID-compatible VPN-клиент.
8. Клиент делает request с `x-hwid`.
9. AKFA создает device и применяет config на nodes.

## Как проверить лимит 2/2 вручную

Пусть у пользователя:

```text
device_limit = 2
```

Первое устройство:

```bash
curl -H "x-hwid: phone-1" \
  -H "x-device-os: Android" \
  -H "x-device-model: Samsung S23" \
  -H "x-ver-os: 14" \
  -H "x-app-version: 3.18.3" \
  "http://localhost:8000/sub/{user_token}?platform=android&client=happ&format=raw"
```

Второе устройство:

```bash
curl -H "x-hwid: laptop-1" \
  -H "x-device-os: Windows" \
  -H "x-device-model: ThinkPad X1" \
  "http://localhost:8000/sub/{user_token}?platform=windows&client=fclashx&format=clash"
```

Третье устройство:

```bash
curl -i -H "x-hwid: phone-2" \
  "http://localhost:8000/sub/{user_token}?platform=android&client=happ&format=raw"
```

Ожидаемый ответ:

```text
HTTP/1.1 403 Forbidden
x-hwid-limit: true
x-hwid-max-devices-reached: true

Превышен лимит устройств
```

## Как проверить отсутствие HWID

```bash
curl -i "http://localhost:8000/sub/{user_token}?platform=android&client=happ&format=raw"
```

Ожидаемый ответ:

```text
HTTP/1.1 403 Forbidden
x-hwid-limit: true
x-hwid-not-supported: true

Ваш клиент не поддерживает ограничение устройств
```

## Как проверить копирование ссылки на другой телефон

В HWID hard mode сама subscription URL может быть одинаковой:

```text
/sub/{user_token}?platform=android&client=happ&format=raw
```

Защита работает не через уникальность URL, а через `x-hwid`.

Сценарий:

1. Первый телефон запрашивает ссылку с `x-hwid: phone-1`.
2. Backend создает DEV-1.
3. Второй телефон использует ту же ссылку, но отправляет `x-hwid: phone-2`.
4. Если лимит свободен, backend создаст DEV-2.
5. Если лимит исчерпан, backend вернет `403 Превышен лимит устройств`.

Для `/sub/device/{device_token}` защита жестче:

1. Device token принадлежит DEV-1.
2. DEV-1 имеет `hwid_hash(phone-1)`.
3. Запрос с `x-hwid: phone-2` получит:

```text
403 Ссылка подписки привязана к другому устройству
```

## Как проверить FClashX/Mihomo YAML

```bash
curl -i \
  -H "x-hwid: windows-device-1" \
  -H "x-device-os: Windows" \
  -H "x-device-model: ThinkPad X1" \
  -H "user-agent: FlClash X/v0.3.2 Platform/windows" \
  "http://localhost:8000/sub/{user_token}?platform=windows&client=fclashx&format=clash"
```

Проверить:

- status `200`;
- `Content-Type: application/yaml; charset=utf-8`;
- `profile-title: akfa vpn`;
- `Content-Disposition: attachment; filename="akfa-vpn.yaml"`;
- YAML содержит `proxies`, `proxy-groups`, `rules`;
- `proxy-groups[0].name = akfa vpn`;
- proxy name выглядит как `AKFA 🇳🇱 Нидерланды`;
- UUID внутри proxy равен `device.uuid`.

## Development: backend

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate
pip install -e ".[test]"
alembic upgrade head
python -m app.cli seed-admin --email admin@example.com --password 'ChangeMe123!'
uvicorn app.main:app --reload
pytest
```

PowerShell activation:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[test]"
pytest
```

Alembic:

```bash
cd backend
alembic revision --autogenerate -m "описание изменения"
alembic upgrade head
alembic downgrade -1
```

## Development: frontend

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

Если frontend работает через Vite, добавьте origin в `.env`:

```text
CORS_ORIGINS=["http://localhost:5173","http://localhost:8080"]
```

## Tests and acceptance

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
docker compose exec -T backend pytest
docker compose exec -T frontend npm run build
```

Local backend tests:

```bash
cd backend
pytest
```

Local frontend build:

```bash
cd frontend
npm install
npm run build
```

## Backup and restore

Admin UI содержит backup/export и restore/import.

Backup включает основные таблицы панели, включая:

- admins;
- access profiles;
- departments;
- nodes;
- users;
- user-node access;
- devices;
- device installs legacy table, если она есть;
- traffic snapshots;
- audit log.

Перед production restore обязательно проверьте:

- совпадает ли версия схемы;
- актуальны ли `ENCRYPTION_KEY` и encrypted SSH credentials;
- доступен ли PostgreSQL volume backup.

## Git hygiene

В Git не нужно добавлять:

- `.env`;
- `node_modules/`;
- `frontend/dist/`;
- `backend/.venv/`;
- `__pycache__/`;
- `.pytest_cache/`;
- `pytest-cache-files-*`;
- временные архивы backup;
- логи;
- локальные IDE/cache файлы.

Полезно перед коммитом:

```bash
git status --short
git diff --stat
```

## Production checklist

Перед production:

- заменить `SESSION_SECRET`;
- заменить `ENCRYPTION_KEY`;
- включить HTTPS;
- установить `SECURE_COOKIES=true`;
- выставить корректный `SUBSCRIPTION_BASE_URL`, например `https://panel.example.com`;
- ограничить доступ к admin panel firewall или private network;
- не публиковать Xray API наружу;
- убедиться, что Xray API слушает только localhost на VPS;
- настроить backup PostgreSQL volume;
- проверить SSH доступы и ключи;
- проверить CORS origins;
- включить TOTP для администраторов;
- проверить `/connect/{user_token}`;
- проверить `x-hwid` flow на реальном клиенте;
- проверить `format=clash` в FClashX/Mihomo;
- проверить safe apply-config на одном тестовом node перед массовым rollout.

## Troubleshooting

### `403 Ваш клиент не поддерживает ограничение устройств`

Клиент не отправил `x-hwid`.

Решение:

- использовать HWID-compatible клиент;
- проверить, что custom client действительно добавляет header `x-hwid`;
- не тестировать подписку обычным браузером без header.

### `403 Превышен лимит устройств`

У пользователя достигнут `device_limit`.

Решение:

- админ может увеличить limit;
- админ может revoke старое устройство;
- пользователь должен использовать уже зарегистрированное устройство.

### `403 Ссылка подписки привязана к другому устройству`

Это относится к `/sub/device/{device_token}`.

Причина: device-specific token используется с другим `x-hwid`.

Решение:

- использовать user-level `/sub/{user_token}` с корректным `x-hwid`;
- revoke/reset devices у пользователя при необходимости.

### FClashX показывает profile как число или URL

Проверьте, что используется:

```text
format=clash
```

Backend должен вернуть headers:

```text
profile-title: akfa vpn
Content-Disposition: attachment; filename="akfa-vpn.yaml"
```

### FClashX error: cannot unmarshal string into config.RawConfig

Это значит, что клиент получил raw `vless://...` вместо YAML.

Решение:

```text
/sub/{user_token}?platform=windows&client=fclashx&format=clash
```

### Xray config не применился

Проверить:

- node status;
- SSH credentials;
- install/apply logs;
- Xray service name;
- config path;
- imported_safe/akfa_owned mode;
- backup config на VPS;
- backend logs.

### Docker не запускается

Если команда:

```bash
docker compose ps
```

возвращает ошибку подключения к Docker API, запустите Docker Desktop/daemon и повторите:

```bash
docker compose up -d
```

## Типовой рабочий цикл разработки

1. Обновить `.env`.
2. Запустить Docker.
3. Выполнить `docker compose up -d`.
4. Проверить миграции Alembic.
5. Создать администратора.
6. Создать тестовый node.
7. Создать VPN user с `device_limit`.
8. Открыть `/connect/{user_token}`.
9. Проверить `/sub/{user_token}` с `x-hwid`.
10. Проверить Xray config preview.
11. Запустить backend tests.
12. Запустить frontend build.
13. Проверить `git diff --stat`.

## Безопасность

Важные правила:

- raw `x-hwid` не хранить;
- SSH passwords/private keys хранить только encrypted;
- `.env` не коммитить;
- cookies в production только secure;
- admin panel лучше закрывать firewall;
- TOTP включать для всех админов;
- PostgreSQL backup хранить отдельно;
- Xray API не открывать наружу;
- imported_safe использовать для существующих Xray configs, чтобы не удалить unknown clients.

## Краткая карта API

Admin:

```text
POST   /auth/login
POST   /auth/2fa/verify
POST   /auth/2fa/setup/start
POST   /auth/2fa/setup/confirm
GET    /auth/me

GET    /admin/dashboard
GET    /admin/users
POST   /admin/users
PUT    /admin/users/{id}
GET    /admin/users/{id}/devices
POST   /admin/users/{id}/devices/{device_id}/revoke
POST   /admin/users/{id}/devices/reset

GET    /admin/nodes
POST   /admin/nodes
POST   /admin/nodes/probe
POST   /admin/nodes/{id}/probe
POST   /admin/nodes/{id}/import-xray
POST   /admin/nodes/{id}/dry-run
POST   /admin/nodes/{id}/install
POST   /admin/nodes/{id}/apply-config
GET    /admin/nodes/{id}/config-preview

GET    /admin/traffic/overview
POST   /admin/traffic/collect-now
GET    /admin/audit-log
GET    /admin/backup/export
POST   /admin/backup/import
```

Public:

```text
GET    /connect/{user_token}
GET    /public/connect/{user_token}
GET    /sub/{user_token}
GET    /sub/device/{device_token}
POST   /public/connect/{user_token}/install-link   # deprecated, 410 Gone
```