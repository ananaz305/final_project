import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'reg-login-service')))
from logging.config import fileConfig

from sqlalchemy import create_engine
from sqlalchemy import pool

from alembic import context

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
from app.models import user  # impot User

target_metadata = Base.metadata

# Taking URL for offline mode from .ini
offline_url = config.get_main_option("sqlalchemy.url")
if not offline_url: # if not writen in .ini taking from settings
    offline_url = settings.SYNC_DATABASE_URL

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=offline_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Creating connection, using SYNC_DATABASE_URL from settings
    connectable = create_engine("postgresql+psycopg2://ananaz:ananaz@postgres_db:5432/microservice_db", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True  # <-- Allows alembic to detect changes in ENUMs
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
