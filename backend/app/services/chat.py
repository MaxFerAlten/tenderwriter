"""Chat domain service functions (room lifecycle, members sync, MinIO text and attachment storage)."""

from __future__ import annotations

import hashlib
import io
import json
import re
from datetime import datetime, timezone

from minio import Minio
from minio.error import S3Error
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import (
    ChatEvent,
    ChatMember,
    ChatMessage,
    ChatRoom,
    ChatRoomStatus,
    Tender,
)

DEFAULT_CHAT_BUCKET = "tenderwriter-chat"
_S3_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_S3_BUCKET_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")


def resolve_chat_bucket_name() -> str:
    candidate = (settings.minio_chat_bucket or "").strip().lower()
    if not candidate:
        return DEFAULT_CHAT_BUCKET

    if (
        not _S3_BUCKET_RE.match(candidate)
        or ".." in candidate
        or ".-" in candidate
        or "-." in candidate
        or _S3_BUCKET_IP_RE.match(candidate)
    ):
        return DEFAULT_CHAT_BUCKET

    return candidate


def get_chat_minio_client() -> Minio:
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_chat_bucket(minio_client: Minio | None = None) -> str:
    client = minio_client or get_chat_minio_client()
    bucket = resolve_chat_bucket_name()
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    return bucket

def sanitize_attachment_filename(filename: str | None) -> str:
    if not filename:
        return "attachment.bin"

    normalized = filename.replace("\\", "/").split("/")[-1].strip()
    if not normalized:
        return "attachment.bin"

    sanitized = re.sub(r"[^A-Za-z0-9._-]", "_", normalized)
    return sanitized[:180] or "attachment.bin"


def build_chat_text_object_name(
    tender_id: int,
    chat_room_id: int,
    message_id: int,
    created_at: datetime,
) -> str:
    dt = created_at.astimezone(timezone.utc)
    return (
        f"tenders/tender_{tender_id}/chat/room_{chat_room_id}/"
        f"messages/{dt:%Y/%m/%d}/{message_id}.json"
    )


def store_chat_message_text(
    tender_id: int,
    chat_room_id: int,
    message_id: int,
    text: str,
    sender_id: int | None,
    sent_at: datetime,
) -> tuple[str, str, str, int]:
    minio_client = get_chat_minio_client()
    bucket = ensure_chat_bucket(minio_client)
    object_name = build_chat_text_object_name(tender_id, chat_room_id, message_id, sent_at)

    payload = {
        "message_id": message_id,
        "chat_room_id": chat_room_id,
        "tender_id": tender_id,
        "sender_id": sender_id,
        "sent_at": sent_at.isoformat(),
        "text": text,
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sha256 = hashlib.sha256(raw).hexdigest()

    minio_client.put_object(
        bucket,
        object_name,
        io.BytesIO(raw),
        length=len(raw),
        content_type="application/json",
    )

    return bucket, object_name, sha256, len(raw)


def build_chat_attachment_object_name(
    tender_id: int,
    chat_room_id: int,
    message_id: int,
    attachment_id: int,
    created_at: datetime,
    filename: str,
) -> str:
    dt = created_at.astimezone(timezone.utc)
    safe_filename = sanitize_attachment_filename(filename)
    return (
        f"tenders/tender_{tender_id}/chat/room_{chat_room_id}/"
        f"messages/{dt:%Y/%m/%d}/{message_id}/attachments/"
        f"{attachment_id}_{safe_filename}"
    )


def store_chat_attachment_blob(
    tender_id: int,
    chat_room_id: int,
    message_id: int,
    attachment_id: int,
    filename: str,
    content: bytes,
    content_type: str | None,
    sent_at: datetime,
) -> tuple[str, str, str, int]:
    minio_client = get_chat_minio_client()
    bucket = ensure_chat_bucket(minio_client)
    object_name = build_chat_attachment_object_name(
        tender_id=tender_id,
        chat_room_id=chat_room_id,
        message_id=message_id,
        attachment_id=attachment_id,
        created_at=sent_at,
        filename=filename,
    )
    sha256 = hashlib.sha256(content).hexdigest()

    minio_client.put_object(
        bucket,
        object_name,
        io.BytesIO(content),
        length=len(content),
        content_type=content_type or "application/octet-stream",
    )
    return bucket, object_name, sha256, len(content)


def read_chat_attachment_blob(bucket: str | None, object_name: str | None) -> bytes | None:
    if not bucket or not object_name:
        return None

    minio_client = get_chat_minio_client()
    try:
        response = minio_client.get_object(bucket, object_name)
        raw = response.read()
        response.close()
        response.release_conn()
        return raw
    except S3Error:
        return None


def read_chat_message_text(bucket: str | None, object_name: str | None) -> str | None:
    if not bucket or not object_name:
        return None

    minio_client = get_chat_minio_client()
    try:
        response = minio_client.get_object(bucket, object_name)
        raw = response.read()
        response.close()
        response.release_conn()
    except S3Error:
        return None

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    text = payload.get("text")
    if isinstance(text, str):
        return text
    return None


async def create_chat_event(
    db: AsyncSession,
    chat_room_id: int,
    event_type: str,
    actor_id: int | None = None,
    payload: dict | None = None,
) -> ChatEvent:
    event = ChatEvent(
        chat_room_id=chat_room_id,
        actor_id=actor_id,
        event_type=event_type,
        payload_json=payload or {},
    )
    db.add(event)
    await db.flush()
    return event


async def ensure_official_chat_room(
    db: AsyncSession,
    tender_id: int,
    actor_id: int | None = None,
    open_now: bool = False,
) -> ChatRoom:
    result = await db.execute(
        select(ChatRoom).where(
            ChatRoom.tender_id == tender_id,
            ChatRoom.is_official.is_(True),
        )
    )
    room = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if not room:
        room = ChatRoom(
            tender_id=tender_id,
            is_official=True,
            status=ChatRoomStatus.OPEN if open_now else ChatRoomStatus.PROVISIONED,
            created_by=actor_id,
            opened_at=now if open_now else None,
        )
        db.add(room)
        await db.flush()

        await create_chat_event(
            db,
            chat_room_id=room.id,
            event_type="room_created",
            actor_id=actor_id,
            payload={"tender_id": tender_id, "status": room.status.value},
        )

        if open_now:
            await create_chat_event(
                db,
                chat_room_id=room.id,
                event_type="room_opened",
                actor_id=actor_id,
                payload={"reason": "tender_started"},
            )
        return room

    if open_now and room.status != ChatRoomStatus.OPEN:
        room.status = ChatRoomStatus.OPEN
        if room.opened_at is None:
            room.opened_at = now
        await create_chat_event(
            db,
            chat_room_id=room.id,
            event_type="room_opened",
            actor_id=actor_id,
            payload={"reason": "tender_started"},
        )

    return room


async def upsert_chat_member_for_tender(
    db: AsyncSession,
    tender_id: int,
    user_id: int,
    role: str,
    source: str,
    actor_id: int | None = None,
) -> ChatMember:
    room = await ensure_official_chat_room(db, tender_id=tender_id, actor_id=actor_id, open_now=False)

    result = await db.execute(
        select(ChatMember).where(
            ChatMember.chat_room_id == room.id,
            ChatMember.user_id == user_id,
        )
    )
    member = result.scalar_one_or_none()

    if not member:
        member = ChatMember(
            chat_room_id=room.id,
            user_id=user_id,
            role=role,
            source=source,
            is_active=True,
        )
        db.add(member)
        await db.flush()
        await create_chat_event(
            db,
            chat_room_id=room.id,
            event_type="member_added",
            actor_id=actor_id,
            payload={"user_id": user_id, "role": role, "source": source},
        )
        return member

    was_inactive = not bool(member.is_active)
    member.role = role
    member.source = source
    member.is_active = True
    member.left_at = None

    await db.flush()

    if was_inactive:
        await create_chat_event(
            db,
            chat_room_id=room.id,
            event_type="member_reactivated",
            actor_id=actor_id,
            payload={"user_id": user_id, "role": role, "source": source},
        )

    return member


async def deactivate_chat_member_for_tender(
    db: AsyncSession,
    tender_id: int,
    user_id: int,
    actor_id: int | None = None,
    reason: str = "permission_revoked",
) -> ChatMember | None:
    room_result = await db.execute(
        select(ChatRoom).where(
            ChatRoom.tender_id == tender_id,
            ChatRoom.is_official.is_(True),
        )
    )
    room = room_result.scalar_one_or_none()
    if not room:
        return None

    member_result = await db.execute(
        select(ChatMember).where(
            ChatMember.chat_room_id == room.id,
            ChatMember.user_id == user_id,
            ChatMember.is_active.is_(True),
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        return None

    member.is_active = False
    member.left_at = datetime.now(timezone.utc)
    await db.flush()

    await create_chat_event(
        db,
        chat_room_id=room.id,
        event_type="member_removed",
        actor_id=actor_id,
        payload={"user_id": user_id, "reason": reason},
    )

    return member


async def sync_chat_members_from_tender_permissions(
    db: AsyncSession,
    tender_id: int,
    actor_id: int | None = None,
) -> ChatRoom | None:
    tender_result = await db.execute(
        select(Tender)
        .where(Tender.id == tender_id)
        .options(selectinload(Tender.permissions))
    )
    tender = tender_result.scalar_one_or_none()
    if not tender:
        return None

    room = await ensure_official_chat_room(db, tender_id=tender_id, actor_id=actor_id, open_now=False)

    desired_roles: dict[int, tuple[str, str]] = {}

    if tender.created_by:
        desired_roles[tender.created_by] = ("owner", "owner")

    for perm in tender.permissions or []:
        desired_roles[perm.user_id] = (perm.permission or "viewer", "permission")

    for user_id, (role, source) in desired_roles.items():
        await upsert_chat_member_for_tender(
            db,
            tender_id=tender_id,
            user_id=user_id,
            role=role,
            source=source,
            actor_id=actor_id,
        )

    active_members_result = await db.execute(
        select(ChatMember).where(
            ChatMember.chat_room_id == room.id,
            ChatMember.is_active.is_(True),
        )
    )
    active_members = active_members_result.scalars().all()

    desired_user_ids = set(desired_roles.keys())
    for member in active_members:
        if member.user_id not in desired_user_ids:
            await deactivate_chat_member_for_tender(
                db,
                tender_id=tender_id,
                user_id=member.user_id,
                actor_id=actor_id,
                reason="permissions_sync",
            )

    return room


async def log_chat_message_sent(
    db: AsyncSession,
    room: ChatRoom,
    message: ChatMessage,
    actor_id: int | None,
) -> None:
    await create_chat_event(
        db,
        chat_room_id=room.id,
        event_type="message_sent",
        actor_id=actor_id,
        payload={"message_id": message.id, "message_type": message.message_type.value},
    )
