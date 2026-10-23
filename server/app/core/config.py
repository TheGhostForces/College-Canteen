"""Конфигурация приложения.

Единственный источник настроек - переменные окружения (локально их можно положить в файл `.env`).
Описание всех переменных - в `.env.example`.
"""

from functools import lru_cache

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore")

    # --- База данных (те же имена переменных использует контейнер postgres) ---
    postgres_user: str = "postgres"
    postgres_password: SecretStr
    postgres_db: str = "canteen"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # --- Безопасность ---
    secret_key: SecretStr = Field(min_length=32, description="openssl rand -hex 32")
    access_token_ttl_days: int = Field(30, ge=1)
    cookie_secure: bool = True

    # --- Почта (отправка кодов входа через Resend) ---
    resend_api_key: SecretStr | None = None
    mail_from: str | None = None

    # --- Прочее ---
    timezone: str = "Europe/Moscow"
    enable_docs: bool = False
    cors_origins: list[str] = ["https://voscollege.ru", "https://www.voscollege.ru"]

    # --- Бизнес-правила ---
    order_cancel_deadline_hour: int = Field(16, ge=0, le=23)
    max_cart_items: int = Field(5, ge=1)
    max_cart_amount: int = Field(1000, ge=1)
    login_code_ttl_minutes: int = 10
    login_code_max_attempts: int = 3

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> URL:
        # URL.create сам экранирует спецсимволы в пароле (в строке вида user:pass@host это ломалось бы)
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
