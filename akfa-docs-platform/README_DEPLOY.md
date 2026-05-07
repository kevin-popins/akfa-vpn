# Deploy AKFA Docs Platform

AKFA Docs Platform использует SQLite через native-модуль `better-sqlite3`.

Важно: Linux deploy archive нельзя собирать из обычного Windows PowerShell. В архив попадёт Windows native binary, и на Ubuntu будет ошибка вроде `better-sqlite3.node: invalid ELF header`.

Правильные варианты:

- из WSL/Linux: `npm run package:deploy`;
- из Windows/macOS/Linux через Docker Linux builder: `npm run package:deploy:linux`.

На VPS не нужно выполнять `npm install`, `npm rebuild`, `npm run build` или `docker build`.

## 1. Собрать архив

### Вариант A. WSL/Linux

```bash
cd akfa-docs-platform
npm install
npm run package:deploy
```

### Вариант B. Windows через Docker Linux builder

Docker Desktop должен быть запущен.

```powershell
cd akfa-docs-platform
npm run package:deploy:linux
```

Скрипт создаёт временную Linux-сборку в контейнере `node:20-bookworm` и кладёт готовый архив сюда:

```text
dist/akfa-docs-platform-deploy.tar.gz
```

## 2. Перенести архив на VPS

```bash
scp dist/akfa-docs-platform-deploy.tar.gz root@SERVER:/opt/
```

## 3. Распаковать

```bash
ssh root@SERVER
cd /opt
tar -xzf akfa-docs-platform-deploy.tar.gz
cd /opt/akfa-docs-platform
cp .env.example .env
```

Отредактируйте `.env`:

```bash
nano /opt/akfa-docs-platform/.env
```

Тестовый домен:

```text
NODE_ENV=production
HOSTNAME=127.0.0.1
PORT=6876
SITE_URL=https://DOCS_DOMAIN
DATA_DIR=/opt/akfa-docs-platform/data
SESSION_SECRET=replace-with-generated-secret
ADMIN_EMAIL=ADMIN_EMAIL
ADMIN_PASSWORD=replace-with-generated-admin-password
MAX_UPLOAD_MB=5
```

## 4. Проверить ручной запуск

```bash
cd /opt/akfa-docs-platform
PORT=6876 HOSTNAME=127.0.0.1 node server.js
```

В другом SSH-окне:

```bash
curl -I http://127.0.0.1:6876
curl -I http://127.0.0.1:6876/docs/android-happ
curl -I http://127.0.0.1:6876/docs/windows-fclashx
curl -I http://127.0.0.1:6876/docs/faq
```

## 5. Systemd

```bash
cp /opt/akfa-docs-platform/deploy/akfa-docs-platform.service /etc/systemd/system/akfa-docs-platform.service
systemctl daemon-reload
systemctl enable --now akfa-docs-platform
systemctl status akfa-docs-platform
```

После обновления архива:

```bash
systemctl restart akfa-docs-platform
systemctl status akfa-docs-platform
```

## 6. Nginx

```bash
export DOCS_DOMAIN=help.example.com
sed "s/DOCS_DOMAIN/$DOCS_DOMAIN/g" /opt/akfa-docs-platform/deploy/nginx-docs.conf > /etc/nginx/sites-available/akfa-docs.conf
ln -s /etc/nginx/sites-available/akfa-docs.conf /etc/nginx/sites-enabled/akfa-docs.conf
nginx -t
systemctl reload nginx
```

## 7. Downloads

Файлы приложений лежат отдельно и описаны в `seed-downloads/downloads.manifest.json`:

```text
/opt/akfa-downloads/happ-android.apk
/opt/akfa-downloads/fclashx-windows.exe
/opt/akfa-downloads/fclashx-macos.dmg
```

Nginx отдаёт их по `/downloads/`. Админка управляет заменой файлов через раздел **Файлы / Загрузки**, сохраняя стабильные public URL.

## 8. Если VPS очень маленький

Нормальный путь не требует сборки на VPS. Swap нужен только как аварийный вариант, если вы всё же вручную запускаете `npm install` или `npm run build` на сервере.
