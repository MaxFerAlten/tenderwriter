import asyncio
from app.db.database import async_session_factory
from app.models import User
from sqlalchemy import delete

async def main():
    async with async_session_factory() as session:
        async with session.begin():
            # Delete everyone except the main admin
            stmt = delete(User).where(User.email != "admin@admin.com")
            result = await session.execute(stmt)
            print(f"Eliminati {result.rowcount} utenti di test.")

if __name__ == "__main__":
    asyncio.run(main())
