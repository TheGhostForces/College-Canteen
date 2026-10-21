from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from .models import Model
from settings import engine

async_engine = create_async_engine(
    engine
)

new_session = async_sessionmaker(async_engine, expire_on_commit=False, autoflush=False)


async def create_tables():
    async with async_engine.begin() as conn:
            await conn.run_sync(Model.metadata.create_all)