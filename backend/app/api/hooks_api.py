"""Hook Management API — REST endpoints for hook management."""

from __future__ import annotations

import uuid
import time
import structlog
from typing import Any, Callable, Awaitable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hooks.dispatcher import hook_dispatcher
from hooks.engine import hook_registry
from hooks.types import (
    HookEventType,
    HookEventData,
    HookConfig,
    HookMetadata,
    HookResponse,
    RegisteredHook,
)


logger = structlog.get_logger()
router = APIRouter()


class HookRegistrationRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    event_type: HookEventType
    description: str | None = None
    config: HookConfig = Field(default_factory=HookConfig)
    handler_type: str = Field(default="async", pattern="^(async|sync)$")
    code: str = Field(..., min_length=1, max_length=10000)


class HookRegistrationResponse(BaseModel):
    id: str
    name: str
    event_type: str
    description: str | None = None
    config: HookConfig
    registered_at: float
    message: str


class HookInfoResponse(BaseModel):
    id: str
    name: str
    event_type: str
    description: str | None = None
    config: HookConfig
    registered_at: float | None = None
    call_count: int
    last_called: float | None = None
    last_error: str | None = None


class HookEventInfo(BaseModel):
    value: str
    label: str
    description: str | None = None


class HookEventListResponse(BaseModel):
    events: list[HookEventInfo]


def _create_async_handler(code: str) -> Callable[..., Awaitable[HookResponse]]:
    """Create an async handler from code string."""
    async def handler(event: dict) -> HookResponse:
        try:
            local_vars = {"event": event}
            exec(code, {"HookResponse": HookResponse}, local_vars)
            result = local_vars.get("result")
            if result:
                return result
            return HookResponse(handled=True, modified=False, data=local_vars)
        except Exception as e:
            return HookResponse(handled=True, error=str(e))
    return handler


def _create_sync_handler(code: str) -> Callable[..., HookResponse]:
    """Create a sync handler from code string."""
    def handler(event: dict) -> HookResponse:
        try:
            local_vars = {"event": event}
            exec(code, {"HookResponse": HookResponse}, local_vars)
            result = local_vars.get("result")
            if result:
                return result
            return HookResponse(handled=True, modified=False, data=local_vars)
        except Exception as e:
            return HookResponse(handled=True, error=str(e))
    return handler


@router.get("/hooks")
async def list_hooks() -> list[HookInfoResponse]:
    """List all registered hooks."""
    metadata_list = hook_dispatcher.get_registered_hooks()
    return [
        HookInfoResponse(
            id=m.id,
            name=m.name,
            event_type=m.event_type.value,
            description=m.description,
            config=m.config,
            registered_at=m.registered_at,
            call_count=m.call_count,
            last_called=m.last_called,
            last_error=m.last_error,
        )
        for m in metadata_list
    ]


@router.post("/hooks", response_model=HookRegistrationResponse, status_code=201)
async def register_hook(request: HookRegistrationRequest) -> HookRegistrationResponse:
    """Register a new hook."""
    hook_id = str(uuid.uuid4())
    registered_at = time.time()

    try:
        if request.handler_type == "async":
            handler = _create_async_handler(request.code)
            is_async = True
        else:
            handler = _create_sync_handler(request.code)
            is_async = False

        hook_registry.register(
            name=request.name,
            event_type=request.event_type,
            handler=handler,
            config=request.config,
            is_async=is_async,
            description=request.description,
        )

        hook_dispatcher.register_hook_metadata(
            id=hook_id,
            name=request.name,
            event_type=request.event_type,
            config=request.config,
            description=request.description,
        )

        logger.info(
            "Hook registered",
            hook_id=hook_id,
            name=request.name,
            event_type=request.event_type.value,
        )

        return HookRegistrationResponse(
            id=hook_id,
            name=request.name,
            event_type=request.event_type.value,
            description=request.description,
            config=request.config,
            registered_at=registered_at,
            message=f"Hook '{request.name}' registered successfully for {request.event_type.value}",
        )

    except Exception as e:
        logger.error("Failed to register hook", name=request.name, error=str(e))
        raise HTTPException(status_code=400, detail=f"Failed to register hook: {str(e)}")


@router.delete("/hooks/{hook_id}", status_code=204)
async def unregister_hook(hook_id: str) -> None:
    """Unregister a hook by ID."""
    hook_registry.unregister(hook_id)
    success = hook_dispatcher.unregister_hook(hook_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Hook not found")
    
    logger.info("Hook unregistered", hook_id=hook_id)


@router.get("/hooks/events")
async def list_hook_events() -> HookEventListResponse:
    """Get all available hook event types."""
    events = hook_dispatcher.get_available_events()
    
    descriptions = {
        HookEventType.PRE_TOOL_USE.value: "Called before a tool is executed",
        HookEventType.POST_TOOL_USE.value: "Called after a tool is executed successfully",
        HookEventType.POST_TOOL_USE_FAILURE.value: "Called after a tool execution fails",
        HookEventType.SESSION_START.value: "Called when a new session starts",
        HookEventType.USER_PROMPT_SUBMIT.value: "Called when user submits a prompt",
        HookEventType.SETUP.value: "Called during system setup",
        HookEventType.SUBAGENT_START.value: "Called when a subagent starts",
        HookEventType.PERMISSION_DENIED.value: "Called when a permission is denied",
        HookEventType.PERMISSION_REQUEST.value: "Called when a permission is requested",
        HookEventType.ELICITATION.value: "Called during user elicitation",
        HookEventType.CWD_CHANGED.value: "Called when working directory changes",
        HookEventType.FILE_CHANGED.value: "Called when a file is modified",
        HookEventType.WORKTREE_CREATE.value: "Called when a git worktree is created",
    }

    return HookEventListResponse(
        events=[
            HookEventInfo(
                value=e["value"],
                label=e["label"],
                description=descriptions.get(e["value"]),
            )
            for e in events
        ]
    )


@router.post("/hooks/{hook_id}/test")
async def test_hook(
    hook_id: str,
    event_type: HookEventType,
    test_data: dict[str, Any] | None = None,
) -> HookResponse:
    """Test a specific hook with optional test data."""
    metadata = hook_dispatcher.get_hook(hook_id)
    
    if not metadata:
        raise HTTPException(status_code=404, detail="Hook not found")
    
    hooks = hook_registry.get_hooks_for_event(event_type)
    target_hook = None
    for h in hooks:
        if h.id == hook_id or h.name == metadata.name:
            target_hook = h
            break
    
    if not target_hook:
        raise HTTPException(status_code=404, detail="Hook not found for this event type")
    
    test_event = test_data or {}
    test_event["session_id"] = "test_session"
    
    try:
        if target_hook.is_async:
            result = await target_hook.handler(test_event)
        else:
            result = target_hook.handler(test_event)
        
        if not isinstance(result, HookResponse):
            result = HookResponse(handled=True, data={"result": result})
        
        return result
        
    except Exception as e:
        return HookResponse(handled=False, error=str(e))
