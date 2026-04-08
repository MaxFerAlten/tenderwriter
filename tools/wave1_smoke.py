"""Wave 1 Smoke Test for TenderClaw (minimal MVP).

This script creates a session, adds a user message, builds the system prompt,
and prints a quick snapshot of the current prompt + messages. It serves as a
sanity check to ensure Wave 1 primitives (session_store, system prompt builder,
and message history) are wired correctly before implementing deeper orchestration.
"""

from __future__ import annotations

from backend.schemas.sessions import SessionCreate
from backend.schemas.messages import Message, Role
from backend.services.session_store import session_store
from backend.core.system_prompt import BASE_SYSTEM_PROMPT, build_system_prompt


def run_smoke():
    # Create a new session (Wave 1 MVP)
    create_body = SessionCreate(model=None, system_prompt_append=None, working_directory=".")
    state = session_store.create(create_body)
    session_id = state.session_id
    print(f"Created session: {session_id}")

    # Append a simple user message
    state.messages.append(Message(role=Role.USER, content="Hello TenderClaw Wave 1, this is a smoke test."))

    # Build the full system prompt for this session
    system = build_system_prompt(working_directory=state.working_directory, append=state.system_prompt_append)
    print("--- SYSTEM PROMPT ---")
    print(system)
    print("--- MESSAGES ---")
    for idx, m in enumerate(state.messages, start=1):
        content_preview = m.content if isinstance(m.content, str) else "<block content>"
        print(f"{idx}. {m.role.value}: {content_preview}")


if __name__ == "__main__":
    run_smoke()
