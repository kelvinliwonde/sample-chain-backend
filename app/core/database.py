from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.core.config import settings
import ssl

# Neon requires SSL. asyncpg needs an actual ssl context passed via connect_args,
# NOT a "sslmode=require" query string on the URL (that's a psycopg2-only param
# and asyncpg will choke on it / cause SQLAlchemy to mis-resolve the driver).
ssl_context = ssl.create_default_context()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"ssl": ssl_context},
    # Neon (and most serverless/managed Postgres) silently closes idle connections.
    # pool_pre_ping tests each connection with a lightweight query before using it,
    # transparently reconnecting if it was dropped, instead of raising InterfaceError.
    pool_pre_ping=True,
    # Proactively recycle connections before Neon's idle timeout can close them.
    pool_recycle=300,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

Base = declarative_base()


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
