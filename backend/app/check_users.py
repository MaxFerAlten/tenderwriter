import asyncio

from sqlalchemy import select

from app.db.database import async_session_factory
from app.models import User


async def main():
    async with async_session_factory() as session:
        result = await session.execute(select(User.email))
        emails = result.scalars().all()
        print(f"UTENTI NEL DB: {emails}")


if __name__ == "__main__":
    asyncio.run(main())
