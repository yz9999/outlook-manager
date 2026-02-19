from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    async with engine.begin() as conn:
        from models import Account, Email  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
        # Auto-migrate: add missing columns for SQLite
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(conn):
    """Add columns that exist in models but not in the database (SQLite only)."""
    from sqlalchemy import inspect as sa_inspect, text
    inspector = sa_inspect(conn)
    if not inspector.has_table("accounts"):
        return
    existing = {c["name"] for c in inspector.get_columns("accounts")}
    new_cols = {
        "imap_enabled": "BOOLEAN",
        "pop3_enabled": "BOOLEAN",
        "graph_enabled": "BOOLEAN",
    }
    for col, dtype in new_cols.items():
        if col not in existing:
            conn.execute(text(f"ALTER TABLE accounts ADD COLUMN {col} {dtype}"))


async def get_session():
    async with async_session() as session:
        yield session
