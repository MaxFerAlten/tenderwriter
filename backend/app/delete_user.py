import asyncio
from app.db.database import async_session_factory
from app.models import User
from sqlalchemy import delete

async def main():
    email_to_delete = "registrazioni.hyperknow@gmail.com"
    async with async_session_factory() as session:
        async with session.begin():
            stmt = delete(User).where(User.email == email_to_delete)
            result = await session.execute(stmt)
            print(f"Eliminati {result.rowcount} utenti con email: {email_to_delete}")

if __name__ == "__main__":
    asyncio.run(main())
