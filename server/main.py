from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
from database.db import create_tables
from libs.scheduler import scheduler
from routers.auth_rt import router as auth_rt
from routers.institution_rt import router as institution_rt
from routers.dishes_rt import router as dishes_rt
from routers.dish_to_basket_rt import router as dish_to_basket_rt
from routers.order_rt import router as order_rt
from routers.history_rt import router as history_rt
from routers.user_rt import router as user_rt
from settings import CUSTOM_LOGGING_CONFIG


async def lifespan(app: FastAPI):
    await create_tables()
    print("База создана")
    scheduler.start()
    print("Планировщик запущен")
    yield
    scheduler.shutdown()
    print("Выключение")


app = FastAPI(lifespan=lifespan)

app.mount("/img", StaticFiles(directory="img"), name="images")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://voscollege.ru",
        "https://www.voscollege.ru",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_rt)
app.include_router(dishes_rt)
app.include_router(institution_rt)
app.include_router(dish_to_basket_rt)
app.include_router(order_rt)
app.include_router(history_rt)
app.include_router(user_rt)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_config=CUSTOM_LOGGING_CONFIG)
