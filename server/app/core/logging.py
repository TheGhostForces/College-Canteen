"""Конфигурация логирования uvicorn (единый формат для приложения и access-лога)."""

import copy

from uvicorn.config import LOGGING_CONFIG


def build_log_config() -> dict:
    config = copy.deepcopy(LOGGING_CONFIG)
    config["formatters"]["access"]["fmt"] = (
        '%(asctime)s | %(levelname)-8s | %(client_addr)s | "%(request_line)s" | %(status_code)s'
    )
    config["formatters"]["default"]["fmt"] = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    # логгеры приложения (canteen.*) пишут тем же форматом
    config["loggers"]["canteen"] = {"handlers": ["default"], "level": "INFO", "propagate": False}
    return config
