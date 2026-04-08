"""Session History Service — manage past session persistence and search."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger("tenderclaw.services.history")

HISTORY_DIR = Path(".tenderclaw/history")
STATE_DIR = Path(".tenderclaw/state")


class HistoryPage(TypedDict):
    entries: list[dict]
    total: int
    has_more: bool
    cursor: str | None


class MessagePage(TypedDict):
    messages: list[dict]
    has_more: bool
    cursor: str | None


class SessionHistoryService:
    """Service for managing session history with disk persistence."""

    def __init__(self) -> None:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    def _session_file(self, session_id: str) -> Path:
        return HISTORY_DIR / f"{session_id}.json"

    def _state_file(self, session_id: str) -> Path:
        return STATE_DIR / f"{session_id}.json"

    def _generate_title(self, messages: list[dict]) -> str:
        """Generate a title from the first user message."""
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content[:60] + ("..." if len(content) > 60 else "")
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text = part.get("text", "")[:60]
                            return text + ("..." if len(text) == 60 else "")
        return "Untitled Session"

    def _generate_preview(self, messages: list[dict]) -> str:
        """Generate a preview from the last assistant message."""
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content[:120] + ("..." if len(content) > 120 else "")
        return ""

    def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        keyword: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        """List sessions with optional filtering."""
        sessions: list[dict] = []
        state_files = list(STATE_DIR.glob("*.json"))

        for f in state_files:
            try:
                with open(f, encoding='utf-8') as fh:
                    data = json.load(fh)
                sid = data.get("session_id") or f.stem
                messages = data.get("messages", [])
                title = data.get("title") or self._generate_title(messages)
                preview = data.get("preview") or self._generate_preview(messages)
                created_at = data.get("created_at", "")
                msg_count = len(messages)

                if keyword:
                    kw_lower = keyword.lower()
                    if kw_lower not in title.lower() and kw_lower not in preview.lower():
                        continue

                if date_from:
                    try:
                        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        if dt < datetime.fromisoformat(date_from):
                            continue
                    except (ValueError, TypeError):
                        pass

                if date_to:
                    try:
                        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        if dt > datetime.fromisoformat(date_to):
                            continue
                    except (ValueError, TypeError):
                        pass

                sessions.append({
                    "session_id": sid,
                    "title": title,
                    "created_at": created_at,
                    "message_count": msg_count,
                    "model": data.get("model", ""),
                    "preview": preview,
                    "total_cost_usd": data.get("total_cost_usd", 0.0),
                })
            except Exception as exc:
                logger.warning("Failed to read session %s: %s", f, exc)

        sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return sessions[offset:offset + limit]

    def get_sessions(
        self,
        limit: int = 20,
        before_id: str | None = None,
        search: str | None = None,
    ) -> HistoryPage:
        """Get paginated session history using cursor-based pagination."""
        all_sessions = self._load_all_sessions(search=search)

        start_idx = 0
        if before_id:
            for i, s in enumerate(all_sessions):
                if s["session_id"] == before_id:
                    start_idx = i + 1
                    break

        entries = all_sessions[start_idx:start_idx + limit]
        has_more = len(all_sessions) > start_idx + limit
        next_cursor = entries[-1]["session_id"] if has_more and entries else None

        return {
            "entries": entries,
            "total": len(all_sessions),
            "has_more": has_more,
            "cursor": next_cursor,
        }

    def _load_all_sessions(
        self,
        search: str | None = None,
    ) -> list[dict]:
        """Load all sessions with optional filtering."""
        sessions: list[dict] = []
        state_files = list(STATE_DIR.glob("*.json"))

        for f in state_files:
            try:
                with open(f, encoding='utf-8') as fh:
                    data = json.load(fh)
                sid = data.get("session_id") or f.stem
                messages = data.get("messages", [])
                title = data.get("title") or self._generate_title(messages)
                preview = data.get("preview") or self._generate_preview(messages)
                created_at = data.get("created_at", "")
                msg_count = len(messages)

                if search:
                    kw_lower = search.lower()
                    if kw_lower not in title.lower() and kw_lower not in preview.lower():
                        continue

                sessions.append({
                    "session_id": sid,
                    "title": title,
                    "created_at": created_at,
                    "message_count": msg_count,
                    "model": data.get("model", ""),
                    "last_message": preview,
                    "total_cost_usd": data.get("total_cost_usd", 0.0),
                })
            except Exception as exc:
                logger.warning("Failed to read session %s: %s", f, exc)

        sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return sessions

    def get_session_detail(self, session_id: str) -> dict | None:
        """Get full session details including messages."""
        state_file = self._state_file(session_id)
        if not state_file.exists():
            return None

        try:
            with open(state_file, encoding='utf-8') as f:
                data = json.load(f)

            messages = data.get("messages", [])
            title = data.get("title") or self._generate_title(messages)

            return {
                "session_id": session_id,
                "title": title,
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", data.get("created_at", "")),
                "model": data.get("model", ""),
                "message_count": len(messages),
                "messages": messages,
                "total_usage": {
                    "input_tokens": data.get("total_usage_input", 0),
                    "output_tokens": data.get("total_usage_output", 0),
                },
                "total_cost_usd": data.get("total_cost_usd", 0.0),
                "working_directory": data.get("working_directory", "."),
            }
        except Exception as exc:
            logger.error("Failed to get session detail %s: %s", session_id, exc)
            return None

    def get_session_messages(self, session_id: str) -> list[dict] | None:
        """Get messages for a specific session."""
        state_file = self._state_file(session_id)
        if not state_file.exists():
            return None

        try:
            with open(state_file, encoding='utf-8') as f:
                data = json.load(f)
            return data.get("messages", [])
        except Exception as exc:
            logger.error("Failed to get session messages %s: %s", session_id, exc)
            return None

    def get_session_messages_paginated(
        self,
        session_id: str,
        limit: int = 50,
        before_id: str | None = None,
    ) -> MessagePage | None:
        """Get messages for a session with pagination."""
        messages = self.get_session_messages(session_id)
        if messages is None:
            return None

        start_idx = 0
        if before_id:
            for i, msg in enumerate(messages):
                if msg.get("message_id") == before_id:
                    start_idx = i + 1
                    break

        page_messages = messages[start_idx:start_idx + limit]
        has_more = len(messages) > start_idx + limit
        next_cursor = page_messages[-1].get("message_id") if has_more and page_messages else None

        return {
            "messages": page_messages,
            "has_more": has_more,
            "cursor": next_cursor,
        }

    def delete_session(self, session_id: str) -> bool:
        """Delete a session from disk."""
        state_file = self._state_file(session_id)
        if not state_file.exists():
            return False

        try:
            state_file.unlink()
            history_file = self._session_file(session_id)
            if history_file.exists():
                history_file.unlink()
            logger.info("Session deleted from history: %s", session_id)
            return True
        except Exception as exc:
            logger.error("Failed to delete session %s: %s", session_id, exc)
            return False

    def export_session(self, session_id: str) -> dict | None:
        """Export a single session to JSON."""
        detail = self.get_session_detail(session_id)
        if not detail:
            return None
        return {
            "exported_at": datetime.utcnow().isoformat(),
            "version": "1.0",
            "session": detail,
        }

    def export_all_sessions(self) -> dict:
        """Export all sessions to JSON."""
        sessions = self.list_sessions(limit=10000)
        exported_sessions = []
        for s in sessions:
            detail = self.get_session_detail(s["session_id"])
            if detail:
                exported_sessions.append(detail)
        return {
            "exported_at": datetime.utcnow().isoformat(),
            "version": "1.0",
            "total_sessions": len(exported_sessions),
            "sessions": exported_sessions,
        }

    def import_session(self, data: dict) -> str | None:
        """Import a session from exported JSON."""
        try:
            session_data = data.get("session") or data
            session_id = session_data.get("session_id")
            if not session_id:
                return None

            state_file = self._state_file(session_id)
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)

            logger.info("Session imported: %s", session_id)
            return session_id
        except Exception as exc:
            logger.error("Failed to import session: %s", exc)
            return None

    def get_stats(self) -> dict:
        """Get history statistics."""
        sessions = self.list_sessions(limit=10000)
        total_messages = sum(s.get("message_count", 0) for s in sessions)
        total_cost = sum(s.get("total_cost_usd", 0) for s in sessions)
        return {
            "total_sessions": len(sessions),
            "total_messages": total_messages,
            "total_cost_usd": total_cost,
        }


session_history_service = SessionHistoryService()
