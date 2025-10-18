import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import AsyncGenerator  # <-- 1. ADD THIS IMPORT

# Use a file-based SQLite database named "nimbus.db"
DATABASE_URL = "sqlite+aiosqlite:///./nimbus.db"

# Create the async engine
engine = create_async_engine(DATABASE_URL, echo=True)

# Create a sessionmaker to generate new sessions.
# This is what your background task will use.
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:  # <-- 2. FIX THE TYPE HINT HERE
    """
    FastAPI dependency to get an async database session and
    handle commit/rollback automatically.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise