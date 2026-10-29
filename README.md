# College Canteen

Система предзаказа обедов в столовой колледжа. Студент накануне собирает корзину из меню на завтра и
оформляет заказ, поставщик планирует количество порций и видит, сколько заказано, оператор раздачи
по QR-коду студента находит заказ и отмечает его выданным.

## Роли

| Роль | Что делает |
|------|------------|
| `student` | смотрит меню на завтра, собирает корзину, оформляет и отменяет заказ, видит историю, показывает QR оператору |
| `provider` (поставщик) | выбирает заведение, задаёт количество порций на день, видит сколько заказано |
| `operator` (оператор раздачи) | по подписанному краткоживущему QR видит заказ **на сегодня** и отмечает его выданным; работает только со студентами своего заведения |
| `admin` | через `/admin/index.html` ведёт справочник блюд своего заведения и создаёт студентов, поставщиков, операторов |

Вход - по одноразовому коду из письма (без паролей). Сессия хранится в HttpOnly-cookie.

## Правила предметной области

- Заказ оформляется **сегодня**, выдаётся **завтра** (`Order.pickup_date`). Корзина всегда собирается на завтра.
- У студента не больше одного активного заказа; в корзине до **5 порций** на сумму до **1000 ₽** (настраивается).
- Отмена заказа возможна до **16:00** по времени колледжа в день оформления; порции возвращаются в остаток.
- Остаток порций списывается атомарно (условный `UPDATE`), поэтому продать больше, чем запланировано, нельзя.
- Если поставщик меняет план на день, уже сделанные заказы сохраняются: остаток = новое количество - уже заказано
  (меньше, чем уже заказано, поставить нельзя).
- Невыданные заказы после дня выдачи ночью (01:00) становятся `expired`.
- Удаление блюда - «мягкое» (`is_active = false`): история заказов не ломается, блюдо можно создать заново.

## Стек

Python 3.13, FastAPI, SQLAlchemy 2 (async) + asyncpg, PostgreSQL 15, Alembic, PyJWT, APScheduler, Resend (почта).
Фронтенд - статические HTML/CSS/JS (ES-модули) без сборки. Раздача и TLS - nginx. Всё запускается в Docker Compose.

## Структура репозитория

```
.
├── docker-compose.yml        # postgres + app + nginx
├── .env.example              # все настройки (копируется в .env)
├── nginx/                    # nginx.conf и общие заголовки безопасности
├── frontend/                 # статика: страницы по ролям + js/common.js (общие функции)
└── server/
    ├── Dockerfile
    ├── alembic/              # миграции БД
    ├── app/
    │   ├── main.py           # создание приложения, обработка ошибок, /health
    │   ├── __main__.py       # запуск: python -m app
    │   ├── core/             # config (настройки), security (JWT, коды), exceptions, timeutils
    │   ├── db/               # models, enums, session
    │   ├── schemas/          # pydantic-схемы запросов и ответов
    │   ├── repositories/     # работа с БД и правила предметной области
    │   ├── api/
    │   │   ├── deps.py       # зависимости: сессия, репозитории, текущий пользователь, роли
    │   │   └── routers/      # HTTP-эндпоинты по разделам
    │   └── services/         # почта и ночная очистка
    └── tests/                # pytest (на настоящем PostgreSQL)
```

Как устроены слои: `router` принимает запрос и проверяет права → `repository` выполняет запросы и проверяет правила
(бросает доменные ошибки из `app.core.exceptions`, ничего не знает про HTTP) → обработчик в `main.py` превращает
ошибку в ответ `{"detail": "..."}`. Сессия БД создаётся на каждый HTTP-запрос и передаётся репозиториям через зависимости.

## Локальный запуск (рекомендуемый способ)

Нужны Docker Engine / Docker Desktop и Docker Compose v2 или новее. Python, Node.js,
TLS-сертификаты и аккаунт Resend на компьютере не требуются. Выполните из корня проекта:

```bash
docker compose -f docker-compose.local.yml up -d --build --wait
```

- Сайт: **http://localhost:8080**.
- Swagger: **http://localhost:8080/api/docs** (включая выполнение запросов).
- Проверка приложения и БД: http://localhost:8080/api/health.

Первый запуск скачивает образы и зависимости, применяет миграции и создаёт демоданные:
заведение, пользователей всех ролей, блюда и меню на завтра. Повторный запуск не сбрасывает
данные и не восстанавливает уже заказанные порции; меню на новую дату добавляется при старте.

### Как войти

Откройте сайт, перейдите ко входу и укажите один из адресов:

| Email | Роль |
|-------|------|
| `student@example.com` | студент |
| `provider@example.com` | поставщик |
| `operator@example.com` | оператор раздачи |
| `admin@example.com` | администратор, `/admin/index.html` |

Письма в локальном режиме **не отправляются**. После запроса кода посмотрите лог:

```bash
docker compose -f docker-compose.local.yml logs --tail=50 app
# LOCAL LOGIN CODE | student@example.com | <одноразовый код>
```

Введите код на странице подтверждения. Используется обычная авторизация с одноразовым
кодом и HttpOnly-cookie, без обхода проверки прав. Повторный запрос до истечения кода
может использовать прежний код — ищите его в логах, а не ожидайте нового письма.
После входа администратор автоматически попадает в `/admin/index.html`.

### Управление

```bash
# Состояние и логи
docker compose -f docker-compose.local.yml ps
docker compose -f docker-compose.local.yml logs -f app

# Остановить (база сохранится)
docker compose -f docker-compose.local.yml down

# Пересобрать backend после изменений Python
docker compose -f docker-compose.local.yml up -d --build --wait
```

HTML/CSS/JS подключены с компьютера: после изменения достаточно обновить страницу.
Если порт 8080 занят, задайте `LOCAL_PORT`, например в Bash:
`LOCAL_PORT=8081 docker compose -f docker-compose.local.yml up -d --build --wait`.
В PowerShell сначала выполните `$env:LOCAL_PORT = '8081'`.

Локальный стек имеет отдельное имя проекта и том БД, не читает настройки приложения из `.env`
и не меняет продакшен-конфигурацию. Наружу опубликован только nginx на `127.0.0.1`.
Для полного удаления **локальной базы** выполните
`docker compose -f docker-compose.local.yml down -v` — это необратимо удалит её данные.

**Не используйте этот compose в продакшене:** пароль БД и ключ JWT демонстрационные,
коды входа пишутся в лог, HTTPS отключён.

## Запуск в продакшене (Docker)

Подробная процедура для VPS, DNS `voscollege.ru`, TLS, резервных копий и мониторинга находится
в [`ops/README.md`](ops/README.md). Краткая команда после настройки секретов и сертификата:

```bash
sudo docker compose -f docker-compose.yml up -d --build --wait
```

Первого администратора создавайте только серверной командой:

```bash
sudo docker compose -f docker-compose.yml exec app python -m app.bootstrap_admin \
  --email admin@voscollege.ru --institution-name 'Название колледжа'
```

Не используйте `docker-compose.local.yml` и `app.seed` в продакшене. Перед открытием доступа
настройте `MAIL_BACKEND=resend`, `COOKIE_SECURE=true`, `ENABLE_DOCS=false`, уникальные секреты,
внешние backup и мониторинг.

## Локальная разработка без Docker

```bash
# PostgreSQL должен быть запущен отдельно; настройки POSTGRES_* задайте в .env.
cd server
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
# В .env: COOKIE_SECURE=false, ENABLE_DOCS=true; MAIL_BACKEND=console только локально.
alembic upgrade head
python -m app                      # http://localhost:8000/docs
```

Фронтенд ожидает API по пути `/api/`, поэтому для работы страниц проще локальный Docker Compose.

## Тесты и качество кода

```bash
cd server
pytest                 # только отдельная тестовая PostgreSQL БД, НЕ production!
ruff check . && ruff format --check .
alembic check
```

Тесты создают и очищают БД из `POSTGRES_DB` (по умолчанию `canteen_test`).
Не направляйте тесты в рабочую базу: фикстуры удаляют её таблицы/данные.
CI: `.github/workflows/ci.yml`.

## Миграции

```bash
alembic revision --autogenerate -m "что изменилось"    # после правки app/db/models.py; проверьте файл вручную
alembic upgrade head
alembic downgrade -1
```

## Переход существующей установки

Раньше таблицы создавались через `create_all`, настройки были другими. Порядок обновления:

1. Сделайте резервную копию: `docker compose exec postgres pg_dump -U <user> <db> > backup.sql`.
2. Обновите `.env` по образцу `.env.example`:

   | Было | Стало |
   |------|-------|
   | `ENGINE` | убрано (адрес БД собирается из `POSTGRES_*`) |
   | `DB_USER`, `DB_PASSWORD`, `DB_NAME` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (значения те же, что у работающей БД) |
   | `API_FOR_SENDER`, `SENDER_EMAIL` | `RESEND_API_KEY`, `MAIL_FROM` |
   | - | `SECRET_KEY` (обязателен, ≥ 32 символов) |

3. `docker compose up -d --build`. Базовая миграция увидит, что таблицы уже есть, и пропустится; вторая добавит
   `Order.pickup_date` (заполнит для старых заказов), уникальные ограничения и индексы. Если в данных были дубликаты
   блюд (одно имя в одном заведении), у лишних появится суффикс ` #<id>`.
4. Сервис приложения теперь называется `app` (раньше `fastapi-app`).

## Настройки

Все переменные описаны в [`.env.example`](.env.example). Читаются классом `app.core.config.Settings`
(pydantic-settings): неверные значения останавливают запуск с понятной ошибкой, а не ломают работу позже.

## Основные эндпоинты

Все пути - за префиксом `/api/` в nginx. Подробности - в Swagger (`ENABLE_DOCS=true`, `/docs`).

| Раздел | Эндпоинты |
|--------|-----------|
| Авторизация | `POST /auth/generate` (код на почту), `POST /auth/confirm`, `POST /auth/logout` |
| Меню | `GET /dishes/dishes_tomorrow` (студент); `GET/PUT /dishes/date_dishes`, `/dishes/dishes` (поставщик); `GET /dishes/date_dishes_operator` (оператор) |
| Справочник блюд | `GET/POST/PATCH/DELETE /dishes/dish` (админ) |
| Корзина | `GET/POST/DELETE /basket/dish`, `POST /basket/quantity` |
| Заказы | `POST/GET/DELETE /orders/order` (студент), `POST /orders/pickup_token` (QR); `POST /orders/student_order`, `PATCH /orders/order` с JSON `{pickup_token}` (оператор); `GET /orders/orders_date`, `/orders/orders`, `/orders/total_quantity` |
| История | `GET /history/history?month=&year=` |
| Администрирование | `GET /admin/me`, `/admin/users?limit=25&offset=0`, `/admin/dishes`, `POST /admin/user` (только своё заведение) |
| Прочее | `GET /institution/institutions`, `GET /health` |

Имена полей в ответах (`Ok`, `Orders`, `Student_ID`...) - контракт с фронтендом и мобильным приложением, менять их нельзя.

## Продакшен

- TLS-сертификаты: `nginx/ssl/fullchain.pem` и `privkey.pem`; продление через certbot (webroot `certbot/www`, путь `/.well-known/acme-challenge/` уже обслуживается).
- В `.env`: `COOKIE_SECURE=true`, `ENABLE_DOCS=false`.
- nginx отдаёт заголовки безопасности (HSTS, CSP, X-Frame-Options...) из `nginx/security_headers.conf`; он подключается в **каждый** `location`, потому что `add_header` в nginx не наследуется.
  Если добавляете внешние скрипты/стили, расширьте CSP.
- Лимиты запросов по IP мягкие: весь колледж может выходить в сеть с одного адреса. Защита кода входа - счётчик попыток в приложении (3 попытки на код).

## Совместимость при обновлении

- `/auth/generate` принимает JSON `{email}`, `/auth/confirm` — JSON
  `{user_id, temporary_code_id, code}`. Query-only запросы больше не поддерживаются.
- QR содержит отдельный JWT с `purpose=pickup`, срок — 5 минут; корзина обновляет его автоматически.
  Поиск и выдача требуют JSON `{pickup_token}`, числовой ID недостаточен. Старые QR недействительны.
- Access cookie теперь требует `purpose=access`: после обновления пользователям потребуется повторный вход.
  Pickup JWT не подходит для авторизации. Все клиенты API, включая мобильные, нужно обновить вместе с сервером.
- Миграция `0003` добавляет ограничения ролей/категорий/дат/цен/количеств, уникальность email без
  учёта регистра, одной корзины и одного активного заказа на студента. Некорректные старые данные
  вызывают явный отказ с диагностикой, без автоматического удаления.
- `OrderDish.unit_price` хранит цену оформления. Для заказов до миграции используется текущая
  цена каталога: восстановить неизвестную историческую цену невозможно. Дальнейшее изменение
  справочника не меняет сумму уже оформленного заказа.
- Корзина, оформление и отмена используют общий протокол блокировок; цены/остатки и ограничения
  проверяются также в репозиториях, в том числе при параллельных операциях.

## Известные ограничения

- Запрос `/auth/generate` сообщает, существует ли email (нужно для понятной ошибки на странице входа).
- Названия таблиц в БД в стиле `"Users"`, `"EducationInstitution"` (требуют кавычек) — историческое наследие.
- Фронтенд без сборки; CI проверяет синтаксис JS, inline-модулей и QR-кодирование. Полный браузерный
  e2e всех ролей пока не включён в CI.
- Мониторинг, offsite-backup и оповещения нужно включить на VPS по [`ops/README.md`](ops/README.md).
