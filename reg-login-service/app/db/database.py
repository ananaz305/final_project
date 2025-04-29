from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import MetaData

from app.core.config import settings

# Create async engine
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False, # Set to True for SQL logging
    # pool_size=10, # Example pool configuration
    # max_overflow=20
)

# Async Session Maker
AsyncSessionFactory = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False, # Important for FastAPI background tasks
    autocommit=False,
    autoflush=False,
)

# Base class for declarative models
# Using a naming convention for constraints
convention = {
    "ix": 'ix_%(column_0_label)s',
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s"
}

metadata = MetaData(naming_convention=convention)
Base = declarative_base(metadata=metadata)

# Dependency to get DB session in FastAPI routes
async def get_db() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit() # Commit if no exceptions
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Function to test DB connection (optional, called at startup)
async def test_connection():
    try:
        async with engine.connect() as connection:
            print('[DB] Database connection successful.')
    except Exception as e:
        print(f'[DB] Database connection failed: {e}')
        raise

# Function to initialize DB (create tables)
async def init_db():
    async with engine.begin() as conn:
        # await conn.run_sync(Base.metadata.drop_all) # Use with caution!
        await conn.run_sync(Base.metadata.create_all)
    print("[DB] Database tables created/updated.")