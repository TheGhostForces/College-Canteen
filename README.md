# College Canteen

Система предзаказа обедов в столовой колледжа. Студент накануне собирает корзину из меню на завтра и
оформляет заказ, поставщик планирует количество порций и видит, сколько заказано, оператор раздачи
по QR-коду студента находит заказ и отмечает его выданным.

## Роли

| Роль | Что делает |
|------|------------|
| `student` | смотрит меню на завтра, собирает корзину, оформляет и отменяет заказ, видит историю, показывает QR оператору |
| `provider` (поставщик) | выбирает заведение, задаёт количество порций на день, видит сколько заказано |
| `operator` (оператор раздачи) | по QR/ID студента видит заказ **на сегодня** и отмечает его выданным; работает только со студентами своего заведения |
| `admin` | ведёт справочник блюд своего заведения и заводит пользователей (через API) |

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

## Быстрый старт (Docker)

```bash
cp .env.example .env
# заполните POSTGRES_PASSWORD, SECRET_KEY (openssl rand -hex 32), RESEND_API_KEY, MAIL_FROM
docker compose up -d --build
```

Приложение при старте само применяет миграции (`alembic upgrade head`). nginx ждёт сертификаты в `nginx/ssl/`
(`fullchain.pem`, `privkey.pem`) - для продакшена, см. ниже.

## Локальная разработка без Docker

```bash
# 1. PostgreSQL (например, в Docker): docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15-alpine
# 2. зависимости
cd server
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
# 3. настройки: в .env (корень проекта или server/) задайте POSTGRES_PASSWORD, SECRET_KEY, COOKIE_SECURE=false, ENABLE_DOCS=true
# 4. миграции и запуск
alembic upgrade head
python -m app                      # http://localhost:8000/docs
```

Фронтенд ожидает API по пути `/api/` (его даёт nginx), поэтому для работы страниц удобнее поднять весь стек в Docker.

## Тесты и качество кода

```bash
cd server
pytest                 # нужен PostgreSQL; БД canteen_test создаётся и мигрируется автоматически
ruff check . && ruff format --check .
alembic check          # проверка, что миграции соответствуют моделям (запускается и в pytest)
```

Тесты и линтер запускаются в GitHub Actions (`.github/workflows/ci.yml`).

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
| Заказы | `POST/GET/DELETE /orders/order` (студент); `GET /orders/student_order`, `PATCH /orders/order`, `GET /orders/orders_date` (оператор); `GET /orders/orders`, `/orders/total_quantity` (поставщик) |
| История | `GET /history/history?month=&year=` |
| Прочее | `GET /institution/institutions`, `POST /admin/user`, `GET /health` |

Имена полей в ответах (`Ok`, `Orders`, `Student_ID`...) - контракт с фронтендом и мобильным приложением, менять их нельзя.

## Продакшен

- TLS-сертификаты: `nginx/ssl/fullchain.pem` и `privkey.pem`; продление через certbot (webroot `certbot/www`, путь `/.well-known/acme-challenge/` уже обслуживается).
- В `.env`: `COOKIE_SECURE=true`, `ENABLE_DOCS=false`.
- nginx отдаёт заголовки безопасности (HSTS, CSP, X-Frame-Options...) из `nginx/security_headers.conf`; он подключается в **каждый** `location`, потому что `add_header` в nginx не наследуется.
  Если добавляете внешние скрипты/стили, расширьте CSP.
- Лимиты запросов по IP мягкие: весь колледж может выходить в сеть с одного адреса. Защита кода входа - счётчик попыток в приложении (3 попытки на код).

## Известные ограничения

- QR-код студента содержит его числовой `id`: его можно подобрать. Нужен подписанный/ротируемый токен.
- Запрос `/auth/generate` сообщает, существует ли email (нужно для понятной ошибки на странице входа).
- Параметры `/auth/confirm` передаются в строке запроса и попадают в логи доступа; лучше перенести в тело (сломает старые клиенты).
- Названия таблиц в БД в стиле `"Users"`, `"EducationInstitution"` (требуют кавычек) - историческое наследие; переименование возможно отдельной миграцией.
- У фронтенда нет автотестов и сборки; JS лежит прямо в HTML-страницах.
