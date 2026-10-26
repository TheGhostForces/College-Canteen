"""Ночная очистка: просроченные заказы и устаревшие позиции корзин."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import get_settings
from app.db.session import SessionFactory
from app.repositories.baskets import BasketRepository
from app.repositories.orders import OrdersRepository

logger = logging.getLogger("canteen.scheduler")


async def nightly_cleanup() -> None:
    async with SessionFactory() as session:
        expired = await OrdersRepository(session).expire_overdue()
        cleared = await BasketRepository(session).clear_stale_items()
    logger.info("Очистка: просрочено заказов - %s, удалено позиций из корзин - %s", expired, cleared)


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=get_settings().timezone)
    scheduler.add_job(nightly_cleanup, "cron", hour=1, minute=0, id="nightly_cleanup", replace_existing=True)
    return scheduler
