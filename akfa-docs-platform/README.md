# AKFA Docs Platform

Отдельная публичная база знаний AKFA VPN с приватной админкой для редактирования статей.

Проект не связан с AKFA panel и не меняет её backend/frontend.

## Стек

- Next.js App Router
- TypeScript
- SQLite через `better-sqlite3`
- Markdown editor в админке
- Server-rendered public pages
- Standalone production build

SQLite выбран потому, что база знаний маленькая, self-hosted и должна просто жить на VPS без отдельного PostgreSQL.

## Локальный запуск

```bash
npm install
npm run dev
```

Откройте:

```text
http://127.0.0.1:6876
http://127.0.0.1:6876/admin
```

## Build

```bash
npm run build
```

## Готовый deploy-архив

Из WSL/Linux:

```bash
npm run package:deploy
```

Из Windows PowerShell используйте Linux builder, чтобы не положить в архив Windows binary для SQLite:

```powershell
npm run package:deploy:linux
```

После выполнения появится:

```text
dist/akfa-docs-platform/
dist/akfa-docs-platform-deploy.tar.gz
```

Архив можно переносить на VPS. На VPS не нужен `npm install`, `npm run build` или `docker build`.

## Первый вход

По умолчанию:

```text
admin@example.com
ChangeMe123!
```

Перед production запуском обязательно задайте свои значения в `.env`:

```text
ADMIN_EMAIL=...
ADMIN_PASSWORD=...
SESSION_SECRET=...
```

Если админ уже создан, изменение `ADMIN_PASSWORD` не меняет существующий пароль. Для чистого запуска удалите старую SQLite-базу или добавьте смену пароля через будущую админскую страницу.

В админке можно включить 2FA: откройте `/admin`, нажмите **Включить 2FA**, отсканируйте QR-код и подтвердите 6-значный код. До подтверждения 2FA не считается включённой.

## Контент

При первом запуске приложение создаёт SQLite-базу и начальные статьи:

- `/docs/android-happ` — Android / Happ: установка и подключение
- `/docs/iphone-happ` — iPhone / iPad / Happ: установка и подключение
- `/docs/windows-fclashx` — Windows / FlClashX: установка и подключение
- `/docs/macos-fclashx` — macOS / FlClashX: установка и подключение
- `/docs/faq` — FAQ и решение проблем

Публичные страницы показывают только опубликованные статьи. Черновики видны в админке. Slug статьи редактируется в админке; публичный URL показывается рядом с редактором.

## Загрузки приложений

Установщики не хранятся в проекте. Ссылки ведут на:

```text
/downloads/Happ.apk
/downloads/Happ.macOS.universal.dmg
/downloads/FlClashX-windows-amd64-setup.exe
/downloads/FlClashX-macos-arm64.dmg
```

Nginx должен отдавать `/downloads/` из `/opt/akfa-downloads/`.
