"""Tender chat API endpoints (room, messages, attachments, retrospective, realtime websocket)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import ALGORITHM, UserResponse, get_current_user
from app.config import settings
from app.db.database import async_session_factory, get_db
from app.models import (
    ChatAttachment,
    ChatEvent,
    ChatMember,
    ChatMessage,
    ChatMessageType,
    ChatRoom,
    Tender,
    User,
)
from app.services.chat import (
    ensure_official_chat_room,
    log_chat_message_sent,
    read_chat_attachment_blob,
    read_chat_message_text,
    sanitize_attachment_filename,
    store_chat_attachment_blob,
    store_chat_message_text,
    sync_chat_members_from_tender_permissions,
    resolve_chat_bucket_name,
)

router = APIRouter()

MAX_CHAT_ATTACHMENT_BYTES = 25 * 1024 * 1024


class ChatConnectionManager:
    """In-memory websocket connection manager for chat rooms."""

    def __init__(self):
        self._connections: dict[int, set[WebSocket]] = defaultdict(set)

    async def connect(self, room_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[room_id].add(websocket)

    def disconnect(self, room_id: int, websocket: WebSocket) -> None:
        if room_id not in self._connections:
            return
        self._connections[room_id].discard(websocket)
        if not self._connections[room_id]:
            self._connections.pop(room_id, None)

    async def broadcast(self, room_id: int, payload: dict) -> None:
        sockets = list(self._connections.get(room_id, set()))
        stale: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_json(payload)
            except Exception:
                stale.append(socket)

        for socket in stale:
            self.disconnect(room_id, socket)


chat_connections = ChatConnectionManager()


class ChatRoomResponse(BaseModel):
    id: int
    tender_id: int
    is_official: bool
    status: str
    opened_at: datetime | None
    created_at: datetime | None
    participant_count: int


class ChatMessageCreate(BaseModel):
    text: str


class ChatAttachmentResponse(BaseModel):
    id: int
    message_id: int
    filename: str
    mime_type: str | None
    size_bytes: int | None
    created_at: datetime | None


class ChatMessageResponse(BaseModel):
    id: int
    chat_room_id: int
    sender_id: int | None
    sender_name: str | None
    message_type: str
    text: str
    attachments: list[ChatAttachmentResponse] = []
    created_at: datetime | None


class ChatMessageListResponse(BaseModel):
    items: list[ChatMessageResponse]
    next_before_id: int | None = None


class ChatParticipantResponse(BaseModel):
    user_id: int
    user_name: str | None
    user_email: str | None
    role: str
    source: str
    is_active: bool
    joined_at: datetime | None
    left_at: datetime | None


class ChatRetrospectiveTimelineItem(BaseModel):
    kind: str
    created_at: datetime | None
    message: ChatMessageResponse | None = None
    event_id: int | None = None
    event_type: str | None = None
    actor_id: int | None = None
    actor_name: str | None = None
    payload: dict | None = None


class ChatRetrospectiveResponse(BaseModel):
    room: ChatRoomResponse
    participants: list[ChatParticipantResponse]
    message_count: int
    attachment_count: int
    event_count: int
    first_message_at: datetime | None
    last_message_at: datetime | None
    generated_at: datetime
    timeline: list[ChatRetrospectiveTimelineItem]


async def _get_user_from_ws_token(token: str, db: AsyncSession) -> UserResponse | None:
    from app.auth.provider import _get_provider

    try:
        provider = _get_provider()
        return await provider.validate_token(token, db)
    except Exception:
        pass

    # Fallback: try legacy JWT decode for backward compatibility
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    return UserResponse.model_validate(user)


async def _check_tender_chat_access(
    tender_id: int,
    user: UserResponse,
    db: AsyncSession,
) -> Tender:
    result = await db.execute(
        select(Tender).where(Tender.id == tender_id).options(selectinload(Tender.permissions))
    )
    tender = result.scalar_one_or_none()
    if not tender:
        raise HTTPException(status_code=404, detail="Tender not found")

    if user.role == "admin":
        return tender

    if tender.created_by == user.id:
        return tender

    has_perm = any(p.user_id == user.id for p in (tender.permissions or []))
    if has_perm:
        return tender

    raise HTTPException(status_code=404, detail="Tender not found")


def _resolve_message_text(message: ChatMessage) -> str:
    text = read_chat_message_text(message.text_bucket, message.text_object_key)
    if text is None:
        return message.text_preview or ""
    return text


def _build_attachment_response(attachment: ChatAttachment) -> ChatAttachmentResponse:
    return ChatAttachmentResponse(
        id=attachment.id,
        message_id=attachment.message_id,
        filename=attachment.filename,
        mime_type=attachment.mime_type,
        size_bytes=attachment.size_bytes,
        created_at=attachment.created_at,
    )


def _build_message_response(
    message: ChatMessage,
    text: str,
    sender_name: str | None,
    attachments: list[ChatAttachment] | None = None,
) -> ChatMessageResponse:
    raw_attachments = attachments
    if raw_attachments is None:
        # Avoid async lazy-load here: use relationship only if already loaded.
        raw_attachments = list(message.__dict__.get("attachments") or [])

    ordered_attachments = sorted(raw_attachments, key=lambda item: item.id)
    return ChatMessageResponse(
        id=message.id,
        chat_room_id=message.chat_room_id,
        sender_id=message.sender_id,
        sender_name=sender_name,
        message_type=message.message_type.value,
        text=text,
        attachments=[_build_attachment_response(item) for item in ordered_attachments],
        created_at=message.created_at,
    )


def _build_room_response(room: ChatRoom, participant_count: int) -> ChatRoomResponse:
    return ChatRoomResponse(
        id=room.id,
        tender_id=room.tender_id,
        is_official=bool(room.is_official),
        status=room.status.value,
        opened_at=room.opened_at,
        created_at=room.created_at,
        participant_count=participant_count,
    )


def _build_participant_response(member: ChatMember) -> ChatParticipantResponse:
    return ChatParticipantResponse(
        user_id=member.user_id,
        user_name=member.user.name if member.user else None,
        user_email=member.user.email if member.user else None,
        role=member.role or "viewer",
        source=member.source or "permission",
        is_active=bool(member.is_active),
        joined_at=member.joined_at,
        left_at=member.left_at,
    )


@router.get("/{tender_id}/chat/room", response_model=ChatRoomResponse)
async def get_official_chat_room(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_tender_chat_access(tender_id, current_user, db)

    room = await ensure_official_chat_room(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        open_now=False,
    )
    await sync_chat_members_from_tender_permissions(db, tender_id=tender_id, actor_id=current_user.id)

    count_result = await db.execute(
        select(func.count(ChatMember.id)).where(
            ChatMember.chat_room_id == room.id,
            ChatMember.is_active.is_(True),
        )
    )
    participant_count = count_result.scalar() or 0

    return _build_room_response(room, participant_count)


@router.get("/{tender_id}/chat/messages", response_model=ChatMessageListResponse)
async def list_chat_messages(
    tender_id: int,
    before_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_tender_chat_access(tender_id, current_user, db)

    room = await ensure_official_chat_room(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        open_now=False,
    )

    query = (
        select(ChatMessage)
        .where(
            ChatMessage.chat_room_id == room.id,
            ChatMessage.deleted_at.is_(None),
        )
        .options(
            selectinload(ChatMessage.sender),
            selectinload(ChatMessage.attachments),
        )
        .order_by(ChatMessage.id.desc())
        .limit(limit)
    )

    if before_id is not None:
        query = query.where(ChatMessage.id < before_id)

    result = await db.execute(query)
    messages_desc = result.scalars().all()

    next_before_id = messages_desc[-1].id if len(messages_desc) == limit else None

    items: list[ChatMessageResponse] = []
    for msg in reversed(messages_desc):
        items.append(
            _build_message_response(
                message=msg,
                text=_resolve_message_text(msg),
                sender_name=msg.sender.name if msg.sender else None,
            )
        )

    return ChatMessageListResponse(items=items, next_before_id=next_before_id)


@router.post("/{tender_id}/chat/messages", response_model=ChatMessageResponse, status_code=201)
async def send_chat_message(
    tender_id: int,
    data: ChatMessageCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_tender_chat_access(tender_id, current_user, db)

    text = (data.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message text cannot be empty")

    room = await ensure_official_chat_room(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        open_now=True,
    )
    await sync_chat_members_from_tender_permissions(db, tender_id=tender_id, actor_id=current_user.id)

    now = datetime.now(timezone.utc)
    preview = text[:280]

    message = ChatMessage(
        chat_room_id=room.id,
        sender_id=current_user.id,
        message_type=ChatMessageType.TEXT,
        text_preview=preview,
        created_at=now,
    )
    db.add(message)
    await db.flush()

    bucket, object_key, sha256, payload_size = store_chat_message_text(
        tender_id=tender_id,
        chat_room_id=room.id,
        message_id=message.id,
        text=text,
        sender_id=current_user.id,
        sent_at=now,
    )

    message.text_bucket = bucket
    message.text_object_key = object_key
    message.text_sha256 = sha256
    message.text_size = payload_size
    await db.flush()

    await log_chat_message_sent(db, room=room, message=message, actor_id=current_user.id)

    response = _build_message_response(
        message=message,
        text=text,
        sender_name=current_user.name,
        attachments=[],
    )
    await chat_connections.broadcast(
        room.id,
        {
            "type": "message_created",
            "message": response.model_dump(mode="json"),
        },
    )
    return response


@router.post("/{tender_id}/chat/attachments", response_model=ChatMessageResponse, status_code=201)
async def upload_chat_attachment(
    tender_id: int,
    file: UploadFile = File(...),
    text: str | None = Form(default=None),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_tender_chat_access(tender_id, current_user, db)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Attachment filename is missing")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Attachment is empty")

    if len(content) > MAX_CHAT_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Attachment too large (max {MAX_CHAT_ATTACHMENT_BYTES // (1024 * 1024)} MB)",
        )

    room = await ensure_official_chat_room(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        open_now=True,
    )
    await sync_chat_members_from_tender_permissions(db, tender_id=tender_id, actor_id=current_user.id)

    now = datetime.now(timezone.utc)
    safe_filename = sanitize_attachment_filename(file.filename)
    caption = (text or "").strip()
    preview_text = caption if caption else f"[file] {safe_filename}"

    message = ChatMessage(
        chat_room_id=room.id,
        sender_id=current_user.id,
        message_type=ChatMessageType.TEXT,
        text_preview=preview_text[:280],
        created_at=now,
    )
    db.add(message)
    await db.flush()

    text_bucket, text_object_key, text_sha256, text_payload_size = store_chat_message_text(
        tender_id=tender_id,
        chat_room_id=room.id,
        message_id=message.id,
        text=caption,
        sender_id=current_user.id,
        sent_at=now,
    )

    message.text_bucket = text_bucket
    message.text_object_key = text_object_key
    message.text_sha256 = text_sha256
    message.text_size = text_payload_size
    await db.flush()

    attachment = ChatAttachment(
        message_id=message.id,
        bucket=resolve_chat_bucket_name(),
        object_key=f"pending/{message.id}",
        filename=safe_filename,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
    )
    db.add(attachment)
    await db.flush()

    bucket, object_key, sha256, payload_size = store_chat_attachment_blob(
        tender_id=tender_id,
        chat_room_id=room.id,
        message_id=message.id,
        attachment_id=attachment.id,
        filename=safe_filename,
        content=content,
        content_type=file.content_type,
        sent_at=now,
    )
    attachment.bucket = bucket
    attachment.object_key = object_key
    attachment.sha256 = sha256
    attachment.size_bytes = payload_size
    await db.flush()

    await log_chat_message_sent(db, room=room, message=message, actor_id=current_user.id)

    message_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.id == message.id)
        .options(selectinload(ChatMessage.sender), selectinload(ChatMessage.attachments))
    )
    created_message = message_result.scalar_one()

    response = _build_message_response(
        message=created_message,
        text=caption,
        sender_name=current_user.name,
    )
    await chat_connections.broadcast(
        room.id,
        {
            "type": "message_created",
            "message": response.model_dump(mode="json"),
        },
    )
    return response


@router.get("/{tender_id}/chat/attachments/{attachment_id}/download")
async def download_chat_attachment(
    tender_id: int,
    attachment_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_tender_chat_access(tender_id, current_user, db)

    result = await db.execute(
        select(ChatAttachment)
        .join(ChatAttachment.message)
        .join(ChatMessage.chat_room)
        .where(
            ChatAttachment.id == attachment_id,
            ChatRoom.tender_id == tender_id,
            ChatMessage.deleted_at.is_(None),
        )
    )
    attachment = result.scalar_one_or_none()

    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    raw = read_chat_attachment_blob(attachment.bucket, attachment.object_key)
    if raw is None:
        raise HTTPException(status_code=404, detail="Attachment blob not found in storage")

    safe_filename = sanitize_attachment_filename(attachment.filename)
    ascii_filename = safe_filename.encode("ascii", errors="ignore").decode("ascii")
    ascii_filename = (ascii_filename or f"attachment-{attachment.id}.bin").replace('"', "")

    content_disposition = (
        f"attachment; filename=\"{ascii_filename}\"; "
        f"filename*=UTF-8''{quote(safe_filename)}"
    )

    return Response(
        content=raw,
        media_type=attachment.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": content_disposition,
            "Content-Length": str(len(raw)),
        },
    )


@router.get("/{tender_id}/chat/retrospective", response_model=ChatRetrospectiveResponse)
async def get_chat_retrospective(
    tender_id: int,
    timeline_limit: int = Query(default=200, ge=10, le=2000),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_tender_chat_access(tender_id, current_user, db)

    room = await ensure_official_chat_room(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        open_now=False,
    )
    await sync_chat_members_from_tender_permissions(db, tender_id=tender_id, actor_id=current_user.id)

    participants_result = await db.execute(
        select(ChatMember)
        .where(ChatMember.chat_room_id == room.id)
        .options(selectinload(ChatMember.user))
        .order_by(ChatMember.joined_at.asc(), ChatMember.id.asc())
    )
    participants = participants_result.scalars().all()

    participant_count = len([p for p in participants if p.is_active])

    message_count_result = await db.execute(
        select(func.count(ChatMessage.id)).where(
            ChatMessage.chat_room_id == room.id,
            ChatMessage.deleted_at.is_(None),
        )
    )
    message_count = message_count_result.scalar() or 0

    attachment_count_result = await db.execute(
        select(func.count(ChatAttachment.id))
        .join(ChatAttachment.message)
        .where(
            ChatMessage.chat_room_id == room.id,
            ChatMessage.deleted_at.is_(None),
        )
    )
    attachment_count = attachment_count_result.scalar() or 0

    event_count_result = await db.execute(
        select(func.count(ChatEvent.id)).where(ChatEvent.chat_room_id == room.id)
    )
    event_count = event_count_result.scalar() or 0

    first_last_result = await db.execute(
        select(func.min(ChatMessage.created_at), func.max(ChatMessage.created_at)).where(
            ChatMessage.chat_room_id == room.id,
            ChatMessage.deleted_at.is_(None),
        )
    )
    first_message_at, last_message_at = first_last_result.one()

    messages_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.chat_room_id == room.id,
            ChatMessage.deleted_at.is_(None),
        )
        .options(selectinload(ChatMessage.sender), selectinload(ChatMessage.attachments))
        .order_by(ChatMessage.id.desc())
        .limit(timeline_limit)
    )
    messages = list(reversed(messages_result.scalars().all()))

    events_result = await db.execute(
        select(ChatEvent)
        .where(ChatEvent.chat_room_id == room.id)
        .options(selectinload(ChatEvent.actor))
        .order_by(ChatEvent.id.desc())
        .limit(timeline_limit)
    )
    events = list(reversed(events_result.scalars().all()))

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    timeline: list[ChatRetrospectiveTimelineItem] = []

    for message in messages:
        timeline.append(
            ChatRetrospectiveTimelineItem(
                kind="message",
                created_at=message.created_at,
                message=_build_message_response(
                    message=message,
                    text=_resolve_message_text(message),
                    sender_name=message.sender.name if message.sender else None,
                ),
            )
        )

    for event in events:
        timeline.append(
            ChatRetrospectiveTimelineItem(
                kind="event",
                created_at=event.created_at,
                event_id=event.id,
                event_type=event.event_type,
                actor_id=event.actor_id,
                actor_name=event.actor.name if event.actor else None,
                payload=event.payload_json or {},
            )
        )

    timeline.sort(
        key=lambda item: (
            item.created_at or epoch,
            0 if item.kind == "event" else 1,
            item.event_id or (item.message.id if item.message else 0),
        )
    )
    if len(timeline) > timeline_limit:
        timeline = timeline[-timeline_limit:]

    return ChatRetrospectiveResponse(
        room=_build_room_response(room, participant_count),
        participants=[_build_participant_response(member) for member in participants],
        message_count=message_count,
        attachment_count=attachment_count,
        event_count=event_count,
        first_message_at=first_message_at,
        last_message_at=last_message_at,
        generated_at=datetime.now(timezone.utc),
        timeline=timeline,
    )


@router.get("/{tender_id}/chat/retrospective/export")
async def export_chat_retrospective(
    tender_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _check_tender_chat_access(tender_id, current_user, db)

    room = await ensure_official_chat_room(
        db,
        tender_id=tender_id,
        actor_id=current_user.id,
        open_now=False,
    )
    await sync_chat_members_from_tender_permissions(db, tender_id=tender_id, actor_id=current_user.id)

    participants_result = await db.execute(
        select(ChatMember)
        .where(ChatMember.chat_room_id == room.id)
        .options(selectinload(ChatMember.user))
        .order_by(ChatMember.joined_at.asc(), ChatMember.id.asc())
    )
    participants = participants_result.scalars().all()

    messages_result = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.chat_room_id == room.id,
            ChatMessage.deleted_at.is_(None),
        )
        .options(selectinload(ChatMessage.sender), selectinload(ChatMessage.attachments))
        .order_by(ChatMessage.id.asc())
    )
    messages = messages_result.scalars().all()

    events_result = await db.execute(
        select(ChatEvent)
        .where(ChatEvent.chat_room_id == room.id)
        .options(selectinload(ChatEvent.actor))
        .order_by(ChatEvent.id.asc())
    )
    events = events_result.scalars().all()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tender_id": tender_id,
        "room": {
            "id": room.id,
            "status": room.status.value,
            "is_official": bool(room.is_official),
            "opened_at": room.opened_at.isoformat() if room.opened_at else None,
            "created_at": room.created_at.isoformat() if room.created_at else None,
        },
        "participants": [
            {
                "user_id": member.user_id,
                "user_name": member.user.name if member.user else None,
                "user_email": member.user.email if member.user else None,
                "role": member.role,
                "source": member.source,
                "is_active": bool(member.is_active),
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
                "left_at": member.left_at.isoformat() if member.left_at else None,
            }
            for member in participants
        ],
        "message_count": len(messages),
        "attachment_count": sum(len(message.attachments or []) for message in messages),
        "event_count": len(events),
        "messages": [
            {
                "id": message.id,
                "chat_room_id": message.chat_room_id,
                "sender_id": message.sender_id,
                "sender_name": message.sender.name if message.sender else None,
                "message_type": message.message_type.value,
                "text": _resolve_message_text(message),
                "created_at": message.created_at.isoformat() if message.created_at else None,
                "text_storage": {
                    "bucket": message.text_bucket,
                    "object_key": message.text_object_key,
                    "sha256": message.text_sha256,
                    "size": message.text_size,
                },
                "attachments": [
                    {
                        "id": attachment.id,
                        "filename": attachment.filename,
                        "mime_type": attachment.mime_type,
                        "size_bytes": attachment.size_bytes,
                        "sha256": attachment.sha256,
                        "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
                        "storage": {
                            "bucket": attachment.bucket,
                            "object_key": attachment.object_key,
                        },
                    }
                    for attachment in sorted((message.attachments or []), key=lambda item: item.id)
                ],
            }
            for message in messages
        ],
        "events": [
            {
                "id": event.id,
                "event_type": event.event_type,
                "actor_id": event.actor_id,
                "actor_name": event.actor.name if event.actor else None,
                "payload": event.payload_json or {},
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in events
        ],
    }

    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    now = datetime.now(timezone.utc)
    filename = f"tender_{tender_id}_chat_retrospective_{now:%Y%m%d_%H%M%S}.json"
    content_disposition = (
        f"attachment; filename=\"{filename}\"; "
        f"filename*=UTF-8''{quote(filename)}"
    )

    return Response(
        content=raw,
        media_type="application/json",
        headers={
            "Content-Disposition": content_disposition,
            "Content-Length": str(len(raw)),
        },
    )


@router.websocket("/{tender_id}/chat/ws")
async def chat_websocket(
    websocket: WebSocket,
    tender_id: int,
):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing token")
        return

    room_id: int | None = None
    try:
        async with async_session_factory() as db:
            user = await _get_user_from_ws_token(token, db)
            if user is None:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
                return

            await _check_tender_chat_access(tender_id, user, db)
            room = await ensure_official_chat_room(
                db,
                tender_id=tender_id,
                actor_id=user.id,
                open_now=False,
            )
            await sync_chat_members_from_tender_permissions(db, tender_id=tender_id, actor_id=user.id)
            await db.commit()
            room_id = room.id

        await chat_connections.connect(room_id, websocket)
        await websocket.send_json(
            {
                "type": "connected",
                "room_id": room_id,
                "tender_id": tender_id,
            }
        )

        while True:
            incoming = await websocket.receive_json()
            event_type = incoming.get("type")
            if event_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif event_type == "refresh":
                await websocket.send_json({"type": "refresh_ack"})
            else:
                await websocket.send_json({"type": "unsupported_event"})

    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass
    finally:
        if room_id is not None:
            chat_connections.disconnect(room_id, websocket)
