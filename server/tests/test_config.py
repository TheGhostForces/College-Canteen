import subprocess
import sys

from app.core.config import Settings


def test_database_url_escapes_special_characters():
    settings = Settings(postgres_password="p@ss/w:rd#1", secret_key="x" * 32, _env_file=None)
    url = settings.database_url
    assert url.password == "p@ss/w:rd#1"
    assert "p@ss/w:rd#1" not in url.render_as_string(hide_password=False)  # в строке подключения экранирован


def test_secret_key_must_be_long_enough():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(postgres_password="x", secret_key="short", _env_file=None)


def test_models_match_migrations():
    """Если изменили модели, но забыли миграцию, alembic check упадёт."""
    result = subprocess.run([sys.executable, "-m", "alembic", "check"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
