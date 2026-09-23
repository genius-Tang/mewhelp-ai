from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncEngine, AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings


class Base(AsyncAttrs, DeclarativeBase):
    pass


def create_database_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(), pool_pre_ping=True
    )


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
