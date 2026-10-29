"""Конфигурация логирования uvicorn (единый формат для приложения и access-лога)."""

import copy
import logging

from uvicorn.config import LOGGING_CONFIG


class RedactQueryFilter(logging.Filter):
    """Не записывать query string, в том числе от устаревших клиентов, в access-лог."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, path, version, status = record.args
            record.args = (client, method, str(path).split("?", 1)[0], version, status)
        return True


def build_log_config() -> dict:
    config = copy.deepcopy(LOGGING_CONFIG)
    config["filters"] = {"redact_query": {"()": RedactQueryFilter}}
    config["handlers"]["access"]["filters"] = ["redact_query"]
    config["formatters"]["access"]["fmt"] = (
        '%(asctime)s | %(levelname)-8s | %(client_addr)s | "%(request_line)s" | %(status_code)s'
    )
    config["formatters"]["default"]["fmt"] = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    # логгеры приложения (canteen.*) пишут тем же форматом
    config["loggers"]["canteen"] = {"handlers": ["default"], "level": "INFO", "propagate": False}
    return config
