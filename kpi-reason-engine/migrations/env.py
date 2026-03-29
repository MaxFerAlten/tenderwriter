from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _schema_name() -> str | None:
    normalized = str(config.get_main_option('kpi.schema') or '').strip()
    return normalized or None


def run_migrations_offline() -> None:
    url = config.get_main_option('sqlalchemy.url')
    schema_name = _schema_name()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        include_schemas=bool(schema_name),
        version_table_schema=schema_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        schema_name = _schema_name()
        if schema_name and connection.dialect.name != 'sqlite':
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"'))
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=bool(schema_name),
            version_table_schema=schema_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
