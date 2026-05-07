# Руководство администратора AKFA VPN

Практическое руководство для эксплуатации установленной AKFA VPN. README остаётся технической точкой входа, а этот документ отвечает на вопрос: что делать администратору в рабочих ситуациях.

В примерах используются placeholders:

- `PANEL_DOMAIN`
- `DOCS_DOMAIN`
- `SERVER_IP`
- `ADMIN_EMAIL`
- `REPO_URL`

Не вставляйте реальные пароли, токены и секреты в git, README, issues или чаты.

## 1. Что входит в систему

AKFA VPN состоит из нескольких частей:

- Основная панель AKFA VPN: веб-интерфейс администратора.
- Backend: API на FastAPI, управляет пользователями, серверами, подписками и Xray.
- Frontend: React-приложение панели.
- PostgreSQL: база данных основной панели.
- База знаний / help-сайт: отдельное приложение `akfa-docs-platform` со статьями и файлами скачивания.
- Nginx: принимает внешние HTTP/HTTPS-запросы и проксирует их в нужный сервис.
- Let’s Encrypt SSL: сертификаты для HTTPS.
- Backend watchdog: systemd timer, который проверяет backend health и перезапускает backend при повторяющихся сбоях.
- Папка скачиваемых файлов: `/opt/akfa-downloads`, там лежат APK/EXE/DMG.
- GitHub: источник обновлений проекта.

## 2. Основные адреса

- `https://PANEL_DOMAIN` — админ-панель.
- `https://PANEL_DOMAIN/connect/<token>` — публичная страница пользователя.
- `https://DOCS_DOMAIN` — база знаний.
- `https://DOCS_DOMAIN/admin/login` — админка базы знаний.
- `https://DOCS_DOMAIN/downloads/...` — файлы APK/EXE/DMG.

## 3. Первичная установка на чистый VPS

Подключитесь к серверу:

```bash
ssh root@SERVER_IP
```

Установите проект:

```bash
cd /opt
git clone REPO_URL akfa-vpn
cd /opt/akfa-vpn
chmod +x scripts/*.sh
sudo ./scripts/install.sh
```

Установщик спросит:

- домен панели `PANEL_DOMAIN`;
- публичный connect-домен, он может совпадать с `PANEL_DOMAIN`;
- домен базы знаний `DOCS_DOMAIN`;
- email администратора основной панели;
- пароль администратора основной панели;
- email администратора базы знаний;
- пароль администратора базы знаний;
- email для Let’s Encrypt;
- нужно ли установить базу знаний;
- нужно ли выпускать SSL.

Пароли вводятся скрыто и не печатаются после установки.

Проверки после установки:

```bash
cd /opt/akfa-vpn
docker compose ps
curl --max-time 10 -i http://127.0.0.1:8000/health
curl -I http://127.0.0.1:8080
curl -I http://127.0.0.1:6876
sudo nginx -t
sudo ./scripts/doctor.sh
```

Ожидаемо:

- `backend`, `frontend`, `postgres` запущены;
- backend health возвращает `200`;
- frontend отвечает `200`;
- docs отвечает `200`, если база знаний установлена;
- `nginx -t` successful;
- `doctor.sh` не показывает критичных ошибок.

## 4. Что проверить после установки

Проверьте вручную:

- панель открывается;
- логин администратора панели работает;
- база знаний открывается;
- админка базы знаний открывается;
- файлы скачиваются;
- public connect page открывается;
- watchdog активен;
- SSL работает.

Команды:

```bash
curl -I https://PANEL_DOMAIN
curl -I https://DOCS_DOMAIN
curl -I https://DOCS_DOMAIN/downloads/happ-android.apk
systemctl status akfa-backend-watchdog.timer --no-pager
systemctl list-timers --all | grep akfa
```

Для public connect page используйте реальный token пользователя:

```bash
curl -I https://PANEL_DOMAIN/connect/<token>
curl -i https://PANEL_DOMAIN/public/connect/<token>
```

`/public/connect/<token>` должен возвращать JSON, не HTML.

## 5. Работа с пользователями

Типовой сценарий:

1. Откройте `https://PANEL_DOMAIN`.
2. Войдите под администратором.
3. Перейдите в раздел пользователей.
4. Создайте пользователя.
5. Укажите ФИО или понятное имя.
6. Назначьте отдел.
7. Назначьте профиль доступа.
8. Выберите сервер или ноду, если интерфейс требует выбор.
9. Сохраните пользователя.
10. Скопируйте публичную ссылку подключения `/connect/<token>`.
11. Передайте ссылку пользователю.

Что можно проверить по пользователю:

- активен ли пользователь;
- какие устройства подключены;
- сколько устройств разрешено;
- текущий трафик;
- срок действия доступа;
- профиль доступа;
- доступные серверы.

Если нужно отключить пользователя:

- переведите пользователя в неактивный статус, если нужен временный запрет;
- удалите пользователя только если он больше не нужен;
- для отдельного устройства используйте отключение/удаление устройства в карточке пользователя.

## 6. Работа с серверами / нодами

Серверы добавляются в основной панели в разделе серверов или VPS.

Обычно нужны:

- IP или hostname сервера;
- SSH user;
- SSH password или private key;
- порт SSH;
- параметры Xray/Reality, если они задаются вручную;
- отделы или профили, которые могут использовать ноду.

Порядок работы:

1. Добавьте сервер.
2. Проверьте SSH.
3. Проверьте Xray или выполните установку через панель.
4. Убедитесь, что нода активна.
5. Назначьте пользователей или профили.

Активная нода означает, что панель может использовать её для выдачи конфигов. Неактивная нода не должна получать новых пользователей.

Если нода не проходит проверку:

```bash
cd /opt/akfa-vpn
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
sudo ./scripts/doctor.sh
```

Проверьте:

- доступен ли сервер по SSH;
- правильный ли SSH user;
- не заблокирован ли порт firewall;
- установлен ли Xray;
- корректны ли Reality keys;
- хватает ли прав у SSH user.

## 7. База знаний

Публичная база знаний открывается по адресу:

```text
https://DOCS_DOMAIN
```

Админка базы знаний:

```text
https://DOCS_DOMAIN/admin/login
```

В админке можно:

- редактировать статьи;
- менять slug;
- менять раздел;
- менять порядок сортировки;
- публиковать статьи или оставлять черновики;
- открывать публичную страницу статьи;
- управлять файлами скачивания.

Статьи хранятся в SQLite-базе внутри data-директории docs-платформы. Не редактируйте базу вручную без бэкапа.

## 8. Файлы скачивания APK/EXE/DMG

На VPS файлы лежат здесь:

```text
/opt/akfa-downloads
```

При установке стартовые файлы копируются из:

```text
akfa-docs-platform/seed-downloads/
```

Manifest:

```text
akfa-docs-platform/seed-downloads/downloads.manifest.json
```

Стабильные ссылки:

```text
/downloads/happ-android.apk
/downloads/fclashx-windows.exe
/downloads/fclashx-macos.dmg
```

Обновить файл без SSH:

1. Откройте `https://DOCS_DOMAIN/admin/login`.
2. Перейдите в раздел **Файлы / Загрузки**.
3. Нажмите **Заменить** у нужного файла.
4. Загрузите новый APK/EXE/DMG.
5. Публичная ссылка останется прежней.

Проверки:

```bash
curl -I https://DOCS_DOMAIN/downloads/happ-android.apk
curl -I https://DOCS_DOMAIN/downloads/fclashx-windows.exe
curl -I https://DOCS_DOMAIN/downloads/fclashx-macos.dmg
```

Если файл отдаёт `404`, проверьте:

```bash
ls -lah /opt/akfa-downloads
sudo nginx -t
sudo systemctl reload nginx
```

## 9. Создание или сброс администратора основной панели

CLI основной панели:

```bash
python -m app.cli seed-admin
```

Безопасный сброс пароля существующего администратора:

```bash
cd /opt/akfa-vpn
read -r -s -p "New admin password: " AKFA_ADMIN_PASSWORD; echo
docker compose exec -T \
  -e AKFA_ADMIN_PASSWORD="$AKFA_ADMIN_PASSWORD" \
  backend python -m app.cli seed-admin \
  --email ADMIN_EMAIL \
  --password-env AKFA_ADMIN_PASSWORD \
  --reset-password
unset AKFA_ADMIN_PASSWORD
```

Создание нового администратора выполняется той же командой с другим `ADMIN_EMAIL`.

Если нужно сразу включить требование TOTP при создании:

```bash
cd /opt/akfa-vpn
read -r -s -p "New admin password: " AKFA_ADMIN_PASSWORD; echo
docker compose exec -T \
  -e AKFA_ADMIN_PASSWORD="$AKFA_ADMIN_PASSWORD" \
  backend python -m app.cli seed-admin \
  --email ADMIN_EMAIL \
  --password-env AKFA_ADMIN_PASSWORD \
  --reset-password \
  --enable-totp
unset AKFA_ADMIN_PASSWORD
```

## 10. Сброс администратора базы знаний

Если база пустая, docs-платформа создаёт администратора из `.env` при старте. Для пустой базы:

```bash
sudo nano /opt/akfa-docs-platform/.env
sudo systemctl restart akfa-docs-platform
sudo systemctl status akfa-docs-platform --no-pager
```

Для существующего администратора изменение `.env` само по себе не сбрасывает пароль, потому админ уже есть в SQLite. Используйте DB reset:

```bash
cd /opt/akfa-docs-platform
read -r -s -p "New docs admin password: " DOCS_ADMIN_PASSWORD; echo
sudo DOCS_ADMIN_EMAIL="ADMIN_EMAIL" DOCS_ADMIN_PASSWORD="$DOCS_ADMIN_PASSWORD" node - <<'NODE'
const path = require('node:path');
const bcrypt = require('bcryptjs');
const Database = require('better-sqlite3');

const dataDir = process.env.DATA_DIR || '/opt/akfa-docs-platform/data';
const email = process.env.DOCS_ADMIN_EMAIL;
const password = process.env.DOCS_ADMIN_PASSWORD;
if (!email || !password) throw new Error('DOCS_ADMIN_EMAIL and DOCS_ADMIN_PASSWORD are required');

const db = new Database(path.join(dataDir, 'akfa-docs.sqlite'));
const hash = bcrypt.hashSync(password, 12);
const existing = db.prepare('SELECT id FROM admins WHERE email = ?').get(email);
if (existing) {
  db.prepare('UPDATE admins SET password_hash = ? WHERE email = ?').run(hash, email);
} else {
  db.prepare('INSERT INTO admins (email, password_hash) VALUES (?, ?)').run(email, hash);
}
NODE
unset DOCS_ADMIN_PASSWORD
sudo chown -R www-data:www-data /opt/akfa-docs-platform/data
sudo systemctl restart akfa-docs-platform
sudo systemctl status akfa-docs-platform --no-pager
```

## 11. Обновление проекта с GitHub

Обычный flow:

```bash
cd /opt/akfa-vpn
git pull
sudo ./scripts/update.sh
sudo ./scripts/doctor.sh
```

Простые правила:

- если менялся только README или docs-текст в репозитории, пересборка панели может быть не нужна;
- если менялся frontend, нужен rebuild frontend;
- если менялся backend, нужен rebuild backend;
- если менялись nginx templates, нужен `nginx -t` и reload;
- если менялась docs platform, нужен rebuild/package и restart docs service.

`scripts/update.sh` делает backup, подтягивает код, пересобирает backend/frontend, применяет миграции и проверяет health. Он не удаляет volumes.

## 12. Бэкап

Перед крупным обновлением делайте backup:

```bash
cd /opt/akfa-vpn
sudo ./scripts/backup.sh
```

Backup обычно включает:

- PostgreSQL dump;
- `.env`;
- `docker-compose.yml`;
- deploy templates.

Ищите архивы в:

```text
/opt/akfa-backups
```

Храните backup безопасно: в нём могут быть чувствительные данные.

## 13. Если всё упало

Начните с общей диагностики:

```bash
cd /opt/akfa-vpn
docker compose ps
sudo ./scripts/doctor.sh
```

### A. Панель не открывается

```bash
cd /opt/akfa-vpn
docker compose ps
curl -I http://127.0.0.1:8080
docker compose logs --tail=100 frontend
sudo nginx -t
systemctl status nginx --no-pager
```

### B. Backend не отвечает

```bash
cd /opt/akfa-vpn
curl --max-time 10 -i http://127.0.0.1:8000/health
docker compose logs --tail=100 backend
systemctl status akfa-backend-watchdog.timer --no-pager
/usr/local/bin/akfa-backend-watchdog status
```

### C. Frontend не отвечает

```bash
cd /opt/akfa-vpn
curl -I http://127.0.0.1:8080
docker compose logs --tail=100 frontend
docker compose ps
```

### D. Docs не открываются

```bash
curl -I http://127.0.0.1:6876
systemctl status akfa-docs-platform --no-pager
journalctl -u akfa-docs-platform -n 100 --no-pager
```

### E. Nginx ругается

```bash
nginx -t
systemctl status nginx --no-pager
journalctl -u nginx -n 100 --no-pager
```

### F. Закончилось место на диске

```bash
df -h /
du -h --max-depth=1 /opt | sort -h
du -h --max-depth=1 /var/lib/docker 2>/dev/null | sort -h
du -h --max-depth=1 /var/lib/containerd 2>/dev/null | sort -h
```

### G. SSL не выпустился или истёк

```bash
certbot certificates
certbot renew --dry-run
nginx -t
systemctl reload nginx
```

### H. Public connect page не работает

```bash
curl -I https://PANEL_DOMAIN/connect/<token>
curl -i https://PANEL_DOMAIN/public/connect/<token>
docker compose logs --tail=100 backend
sudo nginx -t
```

`/public/connect/<token>` должен возвращать JSON. Если возвращается HTML, проверьте nginx location `/public/`.

### I. Файлы скачивания дают 404

```bash
ls -lah /opt/akfa-downloads
curl -I https://DOCS_DOMAIN/downloads/happ-android.apk
sudo nginx -t
systemctl status nginx --no-pager
```

## 14. Watchdog

Watchdog проверяет backend health endpoint:

```text
http://127.0.0.1:8000/health
```

Если несколько проверок подряд не проходят, watchdog перезапускает docker compose service `backend`. Он не удаляет volumes и не трогает PostgreSQL.

Проверить timer:

```bash
systemctl status akfa-backend-watchdog.timer --no-pager
systemctl list-timers --all | grep akfa
```

Проверить состояние watchdog:

```bash
/usr/local/bin/akfa-backend-watchdog status
journalctl -u akfa-backend-watchdog.service -n 50 --no-pager
tail -n 100 /var/log/akfa-backend-watchdog.log
```

Вручную запустить проверку:

```bash
sudo /usr/local/bin/akfa-backend-watchdog check
```

Временно отключить:

```bash
sudo systemctl disable --now akfa-backend-watchdog.timer
```

Включить обратно:

```bash
sudo systemctl enable --now akfa-backend-watchdog.timer
```

## 15. Диагностика места на диске

Маленький VPS может забиться из-за Docker build cache, образов и download-файлов.

Проверить место:

```bash
df -h /
docker system df
```

Очистить build cache:

```bash
docker builder prune -af
```

Очистить неиспользуемые Docker objects:

```bash
docker system prune -af
```

Очистить apt cache и старые journal logs:

```bash
apt-get clean
journalctl --vacuum-time=2d
```

Важно: не выполняйте `docker compose down --volumes` без понимания последствий. Это удалит PostgreSQL volume и базу данных основной панели.

## 16. SSL / сертификаты

Посмотреть сертификаты:

```bash
certbot certificates
```

Проверить продление:

```bash
certbot renew --dry-run
```

Проверить nginx:

```bash
nginx -t
systemctl reload nginx
```

Если certbot временно failed, повторите позже. Install оставляет nginx в HTTP-only режиме, если сертификат не выпущен.

## 17. Что нельзя делать без бэкапа

Не делайте без свежего backup:

- `docker compose down --volumes`;
- `rm -rf /opt/akfa-vpn`;
- `rm -rf /opt/akfa-docs-platform`;
- `rm -rf /opt/akfa-downloads`;
- менять `.env` без копии;
- force-pull/reset на VPS без понимания последствий.

Перед рискованными действиями:

```bash
cd /opt/akfa-vpn
sudo ./scripts/backup.sh
```

## 18. Быстрый чеклист здоровья

```bash
cd /opt/akfa-vpn
docker compose ps
curl --max-time 10 -i http://127.0.0.1:8000/health
curl -I http://127.0.0.1:8080
curl -I http://127.0.0.1:6876
sudo nginx -t
systemctl status akfa-backend-watchdog.timer --no-pager
sudo ./scripts/doctor.sh
```

