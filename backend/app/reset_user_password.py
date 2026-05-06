"""Reset a local password for any TenderWriter user by email.

Usage examples:

    python app/reset_user_password.py --email user@example.com --password NewPassw0rd!
    python app/reset_user_password.py --email user@example.com --generate
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import string

from sqlalchemy import select

from app.api.auth import hash_password
from app.db.database import async_session_factory
from app.models import User


def generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def main() -> int:
    parser = argparse.ArgumentParser(description="Reset a TenderWriter user's local password.")
    parser.add_argument("--email", required=True, help="User email")
    parser.add_argument("--password", help="New local password")
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate a temporary password and print it once",
    )
    args = parser.parse_args()

    if not args.password and not args.generate:
        parser.error("Specify --password or --generate")

    new_password = args.password or generate_password()

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.email == args.email))
        user = result.scalar_one_or_none()

        if not user:
            print(f"User not found: {args.email}")
            return 1

        user.hashed_password = hash_password(new_password)
        user.is_verified = True
        user.is_active = True
        await session.commit()

    print(f"Password reset completed for {args.email}")
    print(f"New password: {new_password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
