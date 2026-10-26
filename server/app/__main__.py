"""Запуск: python -m app"""

import uvicorn

from app.core.logging import build_log_config

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        log_config=build_log_config(),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
