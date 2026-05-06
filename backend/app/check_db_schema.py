import asyncio

from sqlalchemy import text

from app.config import settings
from app.db.database import engine


async def check():
    try:
        async with engine.connect() as conn:
            print("SCHEMA_START")
            print(f"BOOTSTRAP_MODE_CONFIG: {settings.db_schema_bootstrap_mode}")

            revision_res = await conn.execute(
                text(
                    "SELECT EXISTS ("
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'alembic_version'"
                    ")"
                )
            )
            has_alembic_version = bool(revision_res.scalar())
            print(f"ALEMBIC_VERSION_TABLE: {str(has_alembic_version).lower()}")

            if has_alembic_version:
                version_res = await conn.execute(text("SELECT version_num FROM alembic_version"))
                print(f"ALEMBIC_VERSION: {version_res.scalar()}")

            res_u = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'users' ORDER BY column_name"
                )
            )
            print(f"USERS_COLUMNS: {', '.join([r[0] for r in res_u])}")

            res_gateway = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'ai_gateway_targets' ORDER BY column_name"
                )
            )
            print(f"AI_GATEWAY_TARGET_COLUMNS: {', '.join([r[0] for r in res_gateway])}")

            res_tables = await conn.execute(
                text("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'")
            )
            print(f"PUBLIC_TABLE_COUNT: {res_tables.scalar()}")
            print("SCHEMA_END")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    asyncio.run(check())
