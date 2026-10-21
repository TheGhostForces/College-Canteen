from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database.repository import BasketDishesRepository


scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

scheduler.add_job(
    BasketDishesRepository.expired_all_orders_and_clear_all_baskets,
    'cron',
    hour=1,
    minute=0,
    id='daily_task',
    replace_existing=True
)
