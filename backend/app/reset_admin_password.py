"""Reset admin password to the value in .env"""

import asyncio

from sqlalchemy import select

from app.api.auth import hash_password
from app.config import settings
from app.db.database import async_session_factory
from app.models import User


async def main():
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.email == settings.admin_username))
        admin = result.scalar_one_or_none()

        if not admin:
            print(f"Admin user {settings.admin_username} not found!")
            return

        # Hash the password using the shared Argon2id hasher
        admin.hashed_password = hash_password(settings.admin_password)

        await session.commit()
        print(f"Password reset for {settings.admin_username}")
        print(f"New password: {settings.admin_password}")


if __name__ == "__main__":
    asyncio.run(main())
