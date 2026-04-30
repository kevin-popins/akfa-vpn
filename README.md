# AKFA VPN

AKFA VPN - панель управления корпоративным доступом в интернет через узлы Xray-core с VLESS Reality.

Проект состоит из backend на FastAPI, frontend на React/Vite и PostgreSQL. В локальной разработке все можно поднять через Docker Compose, а для точечной разработки backend и frontend запускаются отдельно.

## Возможности

- Авторизация администратора через защищенные cookie-сессии.
- Поддержка входа по паролю и опциональной двухфакторной аутентификации TOTP.
- CSRF-защита для административных запросов.
- Управление отделами, профилями доступа, пользователями VPN и Xray-узлами.
- Генерация конфигураций Xray для VLESS, TCP, REALITY и XTLS Vision.
- Проверка SSH-доступа, dry-run установки, установка и применение конфигурации на VPS.
- Просмотр метрик узлов, сбор статистики трафика и контроль лимитов.
- Подписочные ссылки для пользователей: `GET /sub/{token}`.
- Журнал аудита административных действий.

## Стек

- Backend: Python 3.11+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, AsyncSSH.
- Frontend: React 18, TypeScript, Vite, Tailwind CSS, локальные UI-компоненты.
- Инфраструктура: Docker Compose, Nginx для production-сборки frontend.
- Тесты backend: pytest, pytest-asyncio.

## Структура проекта

```text
.
|-- backend/              # FastAPI-приложение, Alembic-миграции, тесты
|   |-- app/              # Основной код backend
|   |-- alembic/          # Миграции базы данных
|   |-- tests/            # Backend-тесты
|   |-- Dockerfile
|   `-- pyproject.toml
|-- frontend/             # React/Vite-приложение
|   |-- public/
|   |-- src/
|   |-- Dockerfile
|   |-- package.json
|   `-- package-lock.json
|-- docker-compose.yml    # Локальный запуск PostgreSQL, backend и frontend
|-- .env.example          # Пример переменных окружения
|-- .gitignore            # Исключения для Git
|-- .gitattributes        # Нормализация переносов строк
`-- README.md
```

## Быстрый запуск через Docker

1. Скопируйте пример окружения:

```bash
cp .env.example .env
```

2. Для локального запуска можно оставить значения из примера, но для production обязательно замените секреты.

3. Соберите и запустите контейнеры:

```bash
docker compose build
docker compose up -d
```

4. Создайте администратора:

```bash
docker compose exec backend python -m app.cli seed-admin --email admin@example.com --password 'ChangeMe123!'
```

5. Проверьте backend:

```bash
curl http://localhost:8000/health
```

После запуска:

- Web-панель: `http://localhost:8080`
- Backend API: `http://localhost:8000`
- Healthcheck: `http://localhost:8000/health`

## Переменные окружения

Файл `.env` не должен попадать в Git. Используйте `.env.example` как шаблон.

| Переменная | Назначение |
| --- | --- |
| `ENVIRONMENT` | Окружение приложения: `development`, `production` и т.п. |
| `DATABASE_URL` | DSN PostgreSQL для SQLAlchemy/psycopg. |
| `SESSION_SECRET` | Секрет подписи сессий. В production задайте длинное случайное значение. |
| `ENCRYPTION_KEY` | Fernet-ключ для шифрования сохраненных SSH-учетных данных. |
| `CORS_ORIGINS` | JSON-массив разрешенных origin для frontend. |
| `SECURE_COOKIES` | `true`, если панель работает через HTTPS. |
| `SUBSCRIPTION_BASE_URL` | Базовый URL для пользовательских подписочных ссылок. |

Сгенерировать Fernet-ключ можно так:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Разработка backend

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate
pip install -e ".[test]"
alembic upgrade head
python -m app.cli seed-admin --email admin@example.com --password 'ChangeMe123!' --enable-totp
uvicorn app.main:app --reload
pytest
```

Полезные команды Alembic:

```bash
cd backend
alembic revision --autogenerate -m "описание изменения"
alembic upgrade head
```

## Разработка frontend

```bash
cd frontend
npm install
npm run lint
npm run build
npm run dev
```

По умолчанию dev-сервер Vite доступен на `http://localhost:5173`.

## Проверки

Backend:

```bash
cd backend
pytest
```

Frontend:

```bash
cd frontend
npm run lint
npm run build
```

Docker smoke test:

```bash
docker compose build
docker compose up -d
docker compose exec backend python -m app.cli seed-admin --email admin@example.com --password 'ChangeMe123!'
curl http://localhost:8000/health
```

## Git и чистота репозитория

Репозиторий должен хранить исходный код, конфигурацию и документацию. В Git не нужно добавлять:

- `.env` и другие локальные секреты;
- `node_modules/`;
- `dist/`, `build/`, `.vite/`;
- `__pycache__/`, `.pytest_cache/`, `pytest-cache-files-*`;
- локальные виртуальные окружения `.venv/` и `venv/`;
- логи, coverage-отчеты и временные файлы редакторов.

Первичная инициализация:

```bash
git init
git status
git add .
git commit -m "Initial project setup"
```

Перед коммитом полезно выполнить:

```bash
git status --short
```

## Production-рекомендации

- Замените `SESSION_SECRET` и `ENCRYPTION_KEY` до первого production-запуска.
- Включите HTTPS и установите `SECURE_COOKIES=true`.
- Не публикуйте Xray API наружу; он должен быть доступен только локально на узле, например `127.0.0.1:10085`.
- Ограничьте доступ к административной панели firewall-правилами или приватной сетью.
- Храните данные PostgreSQL на защищенном диске и настройте регулярные backup.
- После установки узла пересмотрите SSH-доступы и ротацию ключей согласно внутренней политике.
- Проверяйте логи установки и применения конфигурации после каждого изменения VPS.

## Что уже покрывают smoke-тесты

- `/health`;
- вход администратора и защищенная сессия;
- CRUD для отделов, профилей доступа, узлов и пользователей;
- генерация серверной конфигурации Xray;
- dry-run установки через SSH и логирование;
- безопасность подписок для отключенных пользователей;
- разбор статистики Xray и enforcement лимитов трафика.

## Типовой рабочий цикл

1. Обновить локальный `.env` при необходимости.
2. Запустить инфраструктуру через `docker compose up -d` или сервисы по отдельности.
3. Выполнить миграции Alembic.
4. Создать или проверить администратора.
5. Запустить проверки backend/frontend.
6. Проверить `git status --short`.
7. Закоммитить только исходники, конфигурацию и документацию.
