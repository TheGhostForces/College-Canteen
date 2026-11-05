"""Конфигурация приложения.

Единственный источник настроек - переменные окружения (локально их можно положить в файл `.env`).
Описание всех переменных - в `.env.example`.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    # --- База данных (те же имена переменных использует контейнер postgres) ---
    postgres_user: str = "postgres"
    postgres_password: SecretStr | None = None
    canteen_test_pgpass: bool = False
    postgres_db: str = "canteen"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # --- Безопасность ---
    secret_key: SecretStr = Field(min_length=32, description="openssl rand -hex 32")
    access_token_ttl_days: int = Field(30, ge=1)
    cookie_secure: bool = True

    # --- Почта (console только для локальной разработки: коды выводятся в лог) ---
    mail_backend: Literal["resend", "console"] = "resend"
    resend_api_key: SecretStr | None = None
    mail_from: str | None = None

    # --- Прочее ---
    timezone: str = "Europe/Moscow"
    enable_docs: bool = False
    api_root_path: str = ""
    cors_origins: list[str] = ["https://voscollege.ru", "https://www.voscollege.ru"]

    # --- Бизнес-правила ---
    order_cancel_deadline_hour: int = Field(16, ge=0, le=23)
    max_cart_items: int = Field(5, ge=1)
    max_cart_amount: int = Field(1000, ge=1)
    login_code_ttl_minutes: int = 10
    login_code_max_attempts: int = 3

    def __init__(self, **values):
        try:
            super().__init__(**values)
        except ValidationError as error:
            # Pydantic normally retains raw input in errors() and json(), even
            # when hide_input_in_errors hides it from the formatted exception.
            raise ValidationError.from_exception_data("Settings", error.errors(include_input=False)) from None

    @model_validator(mode="after")
    def validate_database_credentials(self):
        if self.canteen_test_pgpass:
            if (self.postgres_host, self.postgres_port, self.postgres_db, self.postgres_user) != (
                "localhost", 5432, "test", "postgres"
            ) or self.postgres_password is not None:
                raise ValueError("Test pgpass requires the authorized test database and no explicit password")
        elif self.postgres_password is None:
            raise ValueError("POSTGRES_PASSWORD is required")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> URL:
        # URL.create сам экранирует спецсимволы в пароле (в строке вида user:pass@host это ломалось бы)
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value() if self.postgres_password is not None else None,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
