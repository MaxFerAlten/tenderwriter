"""
TenderWriter — Admin API

Admin-only endpoints for managing tender access permissions and users.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import UserResponse, get_current_user
from app.db.database import get_db
from app.models import Tender, TenderPermission, User
from app.services.chat import (
    deactivate_chat_member_for_tender,
    sync_chat_members_from_tender_permissions,
    upsert_chat_member_for_tender,
)

router = APIRouter()


# ── Schemas ──


class UserListItem(BaseModel):
    id: int
    email: str
    name: str
    role: str
    is_active: bool
    is_verified: bool
    created_at: datetime | None

    model_config = {"from_attributes": True}


class PermissionGrant(BaseModel):
    user_id: int
    permission: str = "viewer"  # viewer or editor


class PermissionResponse(BaseModel):
    id: int
    tender_id: int
    user_id: int
    user_name: str
    user_email: str
    permission: str
    granted_by: int | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


class TenderPermissionOverview(BaseModel):
    tender_id: int
    tender_title: str
    owner_id: int | None
    owner_name: str | None
    permissions: list[PermissionResponse]


# ── Helpers ──


def _require_admin(current_user: UserResponse):
    """Raise 403 if the current user is not an admin."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


# ── Routes ──


@router.get("/users", response_model=list[UserListItem])
async def list_users(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all users (admin only)."""
    _require_admin(current_user)

    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()

    return [
        UserListItem(
            id=u.id,
            email=u.email,
            name=u.name,
            role=u.role or "editor",
            is_active=u.is_active if u.is_active is not None else True,
            is_verified=u.is_verified if u.is_verified is not None else False,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.get("/tenders/permissions", response_model=list[TenderPermissionOverview])
async def list_all_tender_permissions(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all tenders with their access permissions (admin only)."""
    _require_admin(current_user)

    result = await db.execute(
        select(Tender)
        .options(
            selectinload(Tender.permissions).selectinload(TenderPermission.user),
            selectinload(Tender.created_by_user),
        )
        .order_by(Tender.created_at.desc())
    )
    tenders = result.scalars().all()

    items = []
    for t in tenders:
        perms = []
        for p in t.permissions or []:
            perms.append(
                PermissionResponse(
                    id=p.id,
                    tender_id=p.tender_id,
                    user_id=p.user_id,
                    user_name=p.user.name if p.user else "Unknown",
                    user_email=p.user.email if p.user else "",
                    permission=p.permission or "viewer",
                    granted_by=p.granted_by,
                    created_at=p.created_at,
                )
            )

        items.append(
            TenderPermissionOverview(
                tender_id=t.id,
                tender_title=t.title,
                owner_id=t.created_by,
                owner_name=t.created_by_user.name if t.created_by_user else None,
                permissions=perms,
            )
        )

    return items


@router.get("/tenders/{tender_id}/permissions", response_model=list[PermissionResponse])
async def get_tender_permissions(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get permissions for a specific tender (admin only)."""
    _require_admin(current_user)

    # Verify tender exists
    tender_result = await db.execute(select(Tender).where(Tender.id == tender_id))
    if not tender_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Tender not found")

    result = await db.execute(
        select(TenderPermission)
        .where(TenderPermission.tender_id == tender_id)
        .options(selectinload(TenderPermission.user))
    )
    perms = result.scalars().all()

    return [
        PermissionResponse(
            id=p.id,
            tender_id=p.tender_id,
            user_id=p.user_id,
            user_name=p.user.name if p.user else "Unknown",
            user_email=p.user.email if p.user else "",
            permission=p.permission or "viewer",
            granted_by=p.granted_by,
            created_at=p.created_at,
        )
        for p in perms
    ]


@router.post("/tenders/{tender_id}/permissions", response_model=PermissionResponse, status_code=201)
async def grant_tender_permission(
    tender_id: int,
    data: PermissionGrant,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grant a user access to a specific tender (admin only)."""
    _require_admin(current_user)

    # Verify tender exists
    tender_result = await db.execute(select(Tender).where(Tender.id == tender_id))
    tender = tender_result.scalar_one_or_none()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    # Verify user exists
    user_result = await db.execute(select(User).where(User.id == data.user_id))
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if permission already exists
    existing = await db.execute(
        select(TenderPermission).where(
            TenderPermission.tender_id == tender_id,
            TenderPermission.user_id == data.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400, detail="Permission already exists for this user on this tender"
        )

    perm = TenderPermission(
        tender_id=tender_id,
        user_id=data.user_id,
        permission=data.permission,
        granted_by=current_user.id,
    )
    db.add(perm)
    await db.flush()
    await db.refresh(perm)

    await upsert_chat_member_for_tender(
        db,
        tender_id=tender_id,
        user_id=data.user_id,
        role=data.permission or "viewer",
        source="permission",
        actor_id=current_user.id,
    )
    await sync_chat_members_from_tender_permissions(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
    )

    return PermissionResponse(
        id=perm.id,
        tender_id=perm.tender_id,
        user_id=perm.user_id,
        user_name=target_user.name,
        user_email=target_user.email,
        permission=perm.permission or "viewer",
        granted_by=perm.granted_by,
        created_at=perm.created_at,
    )


@router.delete("/tenders/{tender_id}/permissions/{user_id}", status_code=204)
async def revoke_tender_permission(
    tender_id: int,
    user_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a user's access to a specific tender (admin only)."""
    _require_admin(current_user)

    result = await db.execute(
        select(TenderPermission).where(
            TenderPermission.tender_id == tender_id,
            TenderPermission.user_id == user_id,
        )
    )
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")

    await db.delete(perm)
    await db.flush()

    await deactivate_chat_member_for_tender(
        db,
        tender_id=tender_id,
        user_id=user_id,
        actor_id=current_user.id,
        reason="permission_revoked",
    )
    await sync_chat_members_from_tender_permissions(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
    )
