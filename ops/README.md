# Production: эксплуатация voscollege.ru

Все команды выполняются на VPS после установки Docker, настройки `.env`, DNS и TLS.
Путь установки в примерах: `/opt/college-canteen`. Не используйте `docker-compose.local.yml`
на публичном сервере. Файлы здесь не включают внешнее хранилище/уведомления автоматически.

## Перед обновлением

1. Сохраните дамп: `sudo bash ops/backup.sh /var/backups/college-canteen`.
2. Проверьте восстановление копии в отдельной БД и миграцию на тестовом окружении.
3. Разверните выбранный релиз: `sudo docker compose -f docker-compose.yml up -d --build --wait`.
4. Проверьте `curl -fsS https://voscollege.ru/api/health` и сценарии всех ролей.

Миграции выполняются при старте приложения. Новые ограничения могут отказать при
некорректных старых данных: сначала исправьте данные по диагностике, не удаляйте
базу и не помечайте миграцию применённой вручную. Откат Git не откатывает схему БД.

## Первый администратор

На пустой базе (после миграций):

```bash
sudo docker compose -f docker-compose.yml exec app python -m app.bootstrap_admin \
  --email REAL_ADMIN_EMAIL --institution-name 'Название колледжа'
```

Команда не должна повышать права уже существующих пользователей. Вход — обычным
кодом из письма, затем переход в `/admin/index.html`. В панели создаются пользователи
своего заведения (студент с профилем, поставщик, оператор) и ведётся справочник блюд.
Создание администраторов — только серверной командой, не публичным API.

## Мониторинг

Проверка вручную (на сервере, где установлен сертификат):

```bash
sudo bash ops/check-production.sh https://voscollege.ru
```

Проверяются HTTPS health с запросом к БД, состояние контейнеров, диск (<85%),
остаток действия локального TLS-сертификата (>14 дней).

Включение таймера:

```bash
sudo cp ops/canteen-health.service ops/canteen-health.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now canteen-health.timer
sudo systemctl start canteen-health.service
sudo journalctl -u canteen-health.service -n 50
```

Проверки пишут результат в journald и возвращают ненулевой код при проблеме.
**Настройте доставку оповещений отдельно** (свой systemd OnFailure или агент мониторинга).
Внешняя проверка `https://voscollege.ru/api/health` обязательна: локальный таймер
не сообщит о полном отключении VPS. Добавьте отдельную проверку отправки писем/ошибок Resend.
В тестах почта подменяется; реальную доставку проверьте вручную на вашем домене.

## Логи

Docker json-file ограничен 10 МБ × 5 файлов на контейнер. Пересоздание контейнеров
применит параметры. Access-логи nginx и Uvicorn не сохраняют query strings.
Production должен использовать `MAIL_BACKEND=resend`, никогда `console`.

Не записывайте тела auth-запросов, cookies и Authorization в внешнем proxy/APM.
Уже существующие исторические логи могут содержать секреты — ограничьте доступ,
обработайте их по политике хранения, не отправляйте в публичные баг-репорты.

## Резервные копии

```bash
sudo bash ops/backup.sh /var/backups/college-canteen
```

Скрипт создаёт PostgreSQL custom-format дамп с правами только владельцу,
проверяет каталог архива, публикует файл атомарно и блокирует параллельный запуск.
Он не удаляет старые копии и **не отправляет их во внешнее хранилище**.
Ежедневное расписание (02:15 по времени VPS, с задержкой до 10 минут):

```bash
sudo cp ops/canteen-backup.service ops/canteen-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now canteen-backup.timer
sudo systemctl start canteen-backup.service
sudo journalctl -u canteen-backup.service -n 50
```

Настройте зашифрованную offsite-репликацию и retention; копия на том же VPS не защищает
от потери сервера. Сохраняйте `.env` зашифрованно, `server/img`, конфигурацию и версию релиза отдельно.

Тест восстановления (только отдельная пустая БД, НЕ production):

```bash
# Замените canteen_restore_check уникальным именем проверочной базы.
sudo docker compose -f docker-compose.yml exec -T postgres \
  sh -c 'createdb -U "$POSTGRES_USER" canteen_restore_check'
sudo docker compose -f docker-compose.yml exec -T postgres \
  sh -c 'pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d canteen_restore_check' \
  < /var/backups/college-canteen/SELECTED_BACKUP.dump
```

Проверьте данные и работу приложения в изолированном окружении; затем удалите
только эту проверочную базу по вашей процедуре. Скрипт не автоматизирует удаление БД.
Не запускайте `down -v` на production: это удаляет том БД.

## HTTPS

HSTS действует только на текущий hostname, без `includeSubDomains`. Сертификат и его
автоматическое обновление остаются обязанностью хостинга: проверка срока не продлевает его.
После замены файлов в `nginx/ssl` выполните `nginx -t` и reload контейнера nginx.
DNS, firewall, внешние backup/alert-сервисы не меняются кодом приложения.
