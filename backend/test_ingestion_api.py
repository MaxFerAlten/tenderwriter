import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, desc
from app.models import Document, Tender

DATABASE_URL = "postgresql+asyncpg://tenderwriter:DefaultPg2024Pass@tw-postgres:5432/tenderwriter"

async def test_list():
    engine = create_async_engine(DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        try:
            query = (
                select(Document, Tender.title.label("tender_title"))
                .outerjoin(Tender, Document.tender_id == Tender.id)
                .order_by(desc(Document.created_at))
                .limit(10)
            )
            result = await db.execute(query)
            rows = result.all()
            print(f"Returned {len(rows)} rows.")
            for row in rows:
                doc = row[0]
                tender_title = row[1]
                print(f"doc id: {doc.id}, title: {tender_title}")
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_list())
