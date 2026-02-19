"""
TenderWriter — Content Library API

CRUD endpoints for reusable content blocks (past answers, case studies,
team bios, certifications, boilerplate text).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models import ContentBlock

router = APIRouter()


# ── Schemas ──


class ContentBlockCreate(BaseModel):
    title: str
    content: str
    category: str | None = None
    tags: list[str] = []


class ContentBlockUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    quality_rating: float | None = None


class ContentBlockResponse(BaseModel):
    id: int
    title: str
    content: str
    category: str | None
    tags: list[str]
    usage_count: int
    quality_rating: float
    created_at: datetime | None

    model_config = {"from_attributes": True}


class ContentBlockListResponse(BaseModel):
    items: list[ContentBlockResponse]
    total: int


# ── Routes ──


@router.get("", response_model=ContentBlockListResponse)
async def list_content_blocks(
    category: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List content blocks with filtering and search."""
    query = select(ContentBlock)

    if category:
        query = query.where(ContentBlock.category == category)
    if tag:
        query = query.where(ContentBlock.tags.any(tag))
    if search:
        query = query.where(
            ContentBlock.title.ilike(f"%{search}%")
            | ContentBlock.content.ilike(f"%{search}%")
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(ContentBlock.usage_count.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    blocks = result.scalars().all()

    return ContentBlockListResponse(
        items=[
            ContentBlockResponse(
                id=b.id,
                title=b.title,
                content=b.content,
                category=b.category,
                tags=b.tags or [],
                usage_count=b.usage_count or 0,
                quality_rating=b.quality_rating or 0.0,
                created_at=b.created_at,
            )
            for b in blocks
        ],
        total=total,
    )


@router.post("", response_model=ContentBlockResponse, status_code=201)
async def create_content_block(
    data: ContentBlockCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new reusable content block."""
    block = ContentBlock(
        title=data.title,
        content=data.content,
        category=data.category,
        tags=data.tags,
    )
    db.add(block)
    await db.flush()
    await db.refresh(block)

    return ContentBlockResponse(
        id=block.id,
        title=block.title,
        content=block.content,
        category=block.category,
        tags=block.tags or [],
        usage_count=0,
        quality_rating=0.0,
        created_at=block.created_at,
    )


@router.get("/{block_id}", response_model=ContentBlockResponse)
async def get_content_block(block_id: int, db: AsyncSession = Depends(get_db)):
    """Get a content block by ID."""
    result = await db.execute(select(ContentBlock).where(ContentBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Content block not found")

    return ContentBlockResponse(
        id=block.id,
        title=block.title,
        content=block.content,
        category=block.category,
        tags=block.tags or [],
        usage_count=block.usage_count or 0,
        quality_rating=block.quality_rating or 0.0,
        created_at=block.created_at,
    )


@router.put("/{block_id}", response_model=ContentBlockResponse)
async def update_content_block(
    block_id: int,
    data: ContentBlockUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a content block."""
    result = await db.execute(select(ContentBlock).where(ContentBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Content block not found")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(block, key, value)

    await db.flush()
    await db.refresh(block)

    return ContentBlockResponse(
        id=block.id,
        title=block.title,
        content=block.content,
        category=block.category,
        tags=block.tags or [],
        usage_count=block.usage_count or 0,
        quality_rating=block.quality_rating or 0.0,
        created_at=block.created_at,
    )


@router.delete("/{block_id}", status_code=204)
async def delete_content_block(block_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a content block."""
    result = await db.execute(select(ContentBlock).where(ContentBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Content block not found")

    await db.delete(block)


@router.post("/{block_id}/use", response_model=ContentBlockResponse)
async def increment_usage(block_id: int, db: AsyncSession = Depends(get_db)):
    """Increment usage count when a content block is used in a proposal."""
    result = await db.execute(select(ContentBlock).where(ContentBlock.id == block_id))
    block = result.scalar_one_or_none()
    if not block:
        raise HTTPException(status_code=404, detail="Content block not found")

    block.usage_count = (block.usage_count or 0) + 1
    await db.flush()
    await db.refresh(block)

    return ContentBlockResponse(
        id=block.id,
        title=block.title,
        content=block.content,
        category=block.category,
        tags=block.tags or [],
        usage_count=block.usage_count,
        quality_rating=block.quality_rating or 0.0,
        created_at=block.created_at,
    )
