import asyncio
import os
import sys

from sqlalchemy import delete, select, update

from app.db.database import async_session_factory
from app.models import (
    ChatEvent,
    ChatMember,
    ChatMessage,
    ChatRoom,
    ContentBlock,
    Document,
    OTPToken,
    Proposal,
    ProposalSection,
    SearchHistory,
    Tender,
    TenderPermission,
    User,
)


def resolve_target_email() -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    return os.getenv("DELETE_USER_EMAIL", "registrazioni.hyperknow@gmail.com")


async def main():
    email_to_delete = resolve_target_email()

    async with async_session_factory() as session:
        async with session.begin():
            user_result = await session.execute(
                select(User).where(User.email == email_to_delete)
            )
            user = user_result.scalar_one_or_none()

            if user is None:
                print(f"Nessun utente trovato con email: {email_to_delete}")
                return

            user_id = user.id
            print(f"Eliminazione utente id={user_id}, email={email_to_delete}")

            # Nullify FK references that otherwise block user deletion.
            fk_to_null = [
                (Tender, Tender.created_by, "tenders.created_by"),
                (Proposal, Proposal.created_by, "proposals.created_by"),
                (ProposalSection, ProposalSection.assigned_to, "proposal_sections.assigned_to"),
                (ContentBlock, ContentBlock.created_by, "content_blocks.created_by"),
                (Document, Document.uploaded_by, "documents.uploaded_by"),
                (TenderPermission, TenderPermission.granted_by, "tender_permissions.granted_by"),
                (ChatRoom, ChatRoom.created_by, "chat_rooms.created_by"),
                (ChatMessage, ChatMessage.sender_id, "chat_messages.sender_id"),
                (ChatEvent, ChatEvent.actor_id, "chat_events.actor_id"),
            ]
            for model, column, label in fk_to_null:
                result = await session.execute(
                    update(model).where(column == user_id).values({column.key: None})
                )
                if result.rowcount:
                    print(f"- Azzerati {result.rowcount} riferimenti in {label}")

            # Delete direct child rows for safety, even on old schemas without ON DELETE CASCADE.
            child_to_delete = [
                (OTPToken, OTPToken.user_id, "otp_tokens"),
                (SearchHistory, SearchHistory.user_id, "search_history"),
                (TenderPermission, TenderPermission.user_id, "tender_permissions(user_id)"),
                (ChatMember, ChatMember.user_id, "chat_members"),
            ]
            for model, column, label in child_to_delete:
                result = await session.execute(delete(model).where(column == user_id))
                if result.rowcount:
                    print(f"- Eliminati {result.rowcount} record da {label}")

            result = await session.execute(delete(User).where(User.id == user_id))
            print(f"Eliminati {result.rowcount} utenti con email: {email_to_delete}")


if __name__ == "__main__":
    asyncio.run(main())
