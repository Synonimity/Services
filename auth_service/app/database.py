"""
Async DB engine pointed at Supabase Postgres. Uses connection pooling and
requires SSL - Supabase enforces TLS on its Postgres endpoint by default,
which gives you encryption in transit for every query.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

_engine = None
_sessionmaker = None

def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        kwargs = {}
        if not settings.database_url.startswith("sqlite"):
            kwargs = {"pool_size": 5, "max_overflow": 10}
        
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            echo=False,
            **kwargs
        )
    return _engine

def get_sessionmaker():
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)
    return _sessionmaker

class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_sessionmaker()() as session:
        try:
            yield session
        finally:
            pass # Close is handled automatically by the context manager
