import asyncio
from app.db.database import engine
from sqlalchemy import text

async def check():
    try:
        async with engine.connect() as conn:
            print("SCHEMA_START")
            res_u = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"))
            print(f"USERS_COLUMNS: {', '.join([r[0] for r in res_u])}")
            
            res_o = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'otp_tokens'"))
            print(f"OTP_COLUMNS: {', '.join([r[0] for r in res_o])}")
            print("SCHEMA_END")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == '__main__':
    asyncio.run(check())
