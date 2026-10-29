import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.routers import auth, basket, dishes, history, institutions, orders, users
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.db.session import engine
from app.services.scheduler import create_scheduler

logger = logging.getLogger("canteen")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Планировщик запущен")
    yield
    scheduler.shutdown()
    logger.info("Выключение")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="College Canteen API",
        lifespan=lifespan,
        root_path=settings.api_root_path,
        # Swagger включается только явно (ENABLE_DOCS=true), в продакшене он закрыт
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def prevent_sensitive_response_caching(request: Request, call_next):
        response = await call_next(request)
        path = request.scope["path"].removeprefix(request.scope.get("root_path", ""))
        if path.startswith(("/auth/", "/orders/", "/admin/", "/basket/", "/history/")):
            # Include validation/authentication errors, not just successful token responses.
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        # тот же формат, что у HTTPException: {"detail": ...} - его ждёт фронтенд
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.get("/health", include_in_schema=False)
    async def health() -> dict:
        """Проверка живости для Docker/мониторинга: приложение отвечает и БД доступна."""
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    for module in (auth, dishes, institutions, basket, orders, history, users):
        app.include_router(module.router)

    if os.path.isdir("img"):
        app.mount("/img", StaticFiles(directory="img"), name="images")

    return app


app = create_app()
