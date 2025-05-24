import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reg-login-service')))
from logging.config import fileConfig

from sqlalchemy import create_engine # Используем create_engine для синхронной работы
from sqlalchemy import pool

from alembic import context

# Импортируем SYNC_DATABASE_URL из нашего конфига
from app.core.config import settings
# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
from app.db.database import Base
from app.models import user  # Импортируем модель User

target_metadata = Base.metadata

# Получаем URL для ОФФЛАЙН режима из alembic.ini (если он там есть и нужен)
# или можно также использовать settings.SYNC_DATABASE_URL
offline_url = config.get_main_option("sqlalchemy.url")
if not offline_url: # Если в .ini не указан, берем из settings
    offline_url = settings.SYNC_DATABASE_URL

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=offline_url, # Используем URL для оффлайн режима
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Создаем синхронный движок, используя SYNC_DATABASE_URL из settings
    connectable = create_engine(settings.SYNC_DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True  # <-- это позволяет Alembic отследить изменения ENUM
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
