from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from vocabulary_bot.config import PROJECT_ROOT, BotConfig, load_env_file
from vocabulary_bot.schema import MANAGED_TABLES, metadata

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

load_env_file(PROJECT_ROOT / ".env")
database_url = BotConfig.from_env(require_token=False).database_url
sqlalchemy_url = database_url.replace(
    "postgresql://",
    "postgresql+psycopg://",
    1,
)
# ConfigParser treats '%' as interpolation syntax.
config.set_main_option("sqlalchemy.url", sqlalchemy_url.replace("%", "%%"))
target_metadata = metadata


def include_name(
    name: str | None,
    type_: str,
    parent_names: dict[str, str | None],
) -> bool:
    """Keep unrelated public tables out of autogenerate output."""
    if type_ == "table":
        return name in MANAGED_TABLES
    table_name = parent_names.get("table_name")
    return table_name is None or table_name in MANAGED_TABLES


def configure_context(**kwargs: object) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_name=include_name,
        include_schemas=False,
        **kwargs,
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    configure_context(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        configure_context(connection=connection)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
