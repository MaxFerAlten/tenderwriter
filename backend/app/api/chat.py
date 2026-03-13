"""Tender chat API endpoints (room, messages, attachments, realtime websocket)."""

from __future__ import annotations

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
from app.models import ChatAttachment, ChatMember, ChatMessage, ChatMessageType, ChatRoom, Tender, User
from app.services.chat import (
    ensure_official_chat_room,
    log_chat_message_sent,
    read_chat_attachment_blob,
    read_chat_message_text,
    sanitize_attachment_filename,
    store_chat_attachment_blob,
    store_chat_message_text,
    sync_chat_members_from_tender_permissions,
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


async def _get_user_from_ws_token(token: str, db: AsyncSession) -> UserResponse | None:
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
) -> ChatMessageResponse:
    attachments = sorted((message.attachments or []), key=lambda item: item.id)
    return ChatMessageResponse(
        id=message.id,
        chat_room_id=message.chat_room_id,
        sender_id=message.sender_id,
        sender_name=sender_name,
        message_type=message.message_type.value,
        text=text,
        attachments=[_build_attachment_response(item) for item in attachments],
        created_at=message.created_at,
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

    return ChatRoomResponse(
        id=room.id,
        tender_id=room.tender_id,
        is_official=bool(room.is_official),
        status=room.status.value,
        opened_at=room.opened_at,
        created_at=room.created_at,
        participant_count=participant_count,
    )


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
        text = read_chat_message_text(msg.text_bucket, msg.text_object_key)
        if text is None:
            text = msg.text_preview or ""

        items.append(
            _build_message_response(
                message=msg,
                text=text,
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
        bucket=settings.minio_chat_bucket,
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
