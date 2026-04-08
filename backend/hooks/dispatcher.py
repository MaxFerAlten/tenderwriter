"""Hook Dispatcher — Advanced hook system for TenderClaw.

This module provides a comprehensive API to dispatch lifecycle hooks through
the central hook registry with support for all event types, timeout management,
permission behavior control, and system message injection.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from hooks.engine import hook_registry
from hooks.types import (
    HookEventType,
    HookEventData,
    HookResponse,
    SyncHookResponse,
    AsyncHookResponse,
    HookConfig,
    HookMetadata,
    HookExecutionResult,
    RegisteredHook,
    PermissionBehavior,
)


class HookDispatcher:
    """Dispatch hooks for lifecycle events with advanced features."""

    def __init__(self):
        self._registered_hooks: dict[str, HookMetadata] = {}
        self._permission_behaviors: dict[str, PermissionBehavior] = {}
        self._system_messages: dict[HookEventType, str] = {}

    async def dispatch(
        self,
        event_type: HookEventType,
        data: HookEventData | dict[str, Any],
        session_id: str = "",
        timeout_ms: int = 5000,
    ) -> list[HookExecutionResult]:
        """Dispatch an event to all registered hooks for that event type."""
        if isinstance(data, dict):
            data = HookEventData(**data)
        
        event_data = data.model_dump() if hasattr(data, 'model_dump') else data
        event_data['session_id'] = session_id

        hooks = hook_registry.get_hooks_for_event(event_type)
        results = []

        for hook in hooks:
            result = await self._execute_hook(
                hook,
                event_data,
                timeout_ms,
            )
            results.append(result)
            self._update_hook_metadata(hook.id, result)

        return results

    async def _execute_hook(
        self,
        hook: RegisteredHook,
        event_data: dict[str, Any],
        timeout_ms: int,
    ) -> HookExecutionResult:
        """Execute a single hook with timeout support."""
        start_time = time.time()
        hook_id = hook.id

        try:
            if hook.is_async:
                response = await asyncio.wait_for(
                    hook.handler(event_data),
                    timeout=timeout_ms / 1000,
                )
            else:
                response = hook.handler(event_data)
                if asyncio.iscoroutine(response):
                    response = await asyncio.wait_for(
                        response,
                        timeout=timeout_ms / 1000,
                    )

            duration = (time.time() - start_time) * 1000

            if not isinstance(response, HookResponse):
                response = HookResponse(handled=True, data={"result": response})

            return HookExecutionResult(
                hook_id=hook_id,
                success=True,
                response=response,
                duration_ms=duration,
            )

        except asyncio.TimeoutError:
            duration = (time.time() - start_time) * 1000
            return HookExecutionResult(
                hook_id=hook_id,
                success=False,
                error=f"Hook timed out after {timeout_ms}ms",
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            return HookExecutionResult(
                hook_id=hook_id,
                success=False,
                error=str(e),
                duration_ms=duration,
            )

    def _update_hook_metadata(self, hook_id: str, result: HookExecutionResult) -> None:
        """Update hook metadata after execution."""
        if hook_id in self._registered_hooks:
            metadata = self._registered_hooks[hook_id]
            metadata.call_count += 1
            metadata.last_called = time.time()
            if not result.success:
                metadata.last_error = result.error

    async def dispatch_sync(
        self,
        event_type: HookEventType,
        data: HookEventData | dict[str, Any],
        session_id: str = "",
    ) -> SyncHookResponse:
        """Dispatch event synchronously, blocking until complete."""
        results = await self.dispatch(event_type, data, session_id)

        if not results:
            return SyncHookResponse(handled=False)

        for result in results:
            if result.success and result.response:
                if result.response.block or result.response.modified:
                    return SyncHookResponse(
                        hook_id=result.hook_id,
                        handled=result.response.handled,
                        modified=result.response.modified,
                        data=result.response.data,
                        block=result.response.block,
                    )

        first_result = results[0]
        return SyncHookResponse(
            hook_id=first_result.hook_id,
            handled=first_result.success,
            data=first_result.response.data if first_result.response else {},
        )

    async def dispatch_async(
        self,
        event_type: HookEventType,
        data: HookEventData | dict[str, Any],
        session_id: str = "",
    ) -> list[AsyncHookResponse]:
        """Dispatch event asynchronously with parallel execution."""
        if isinstance(data, dict):
            data = HookEventData(**data)

        hooks = hook_registry.get_hooks_for_event(event_type)
        tasks = []

        for hook in hooks:
            if hook.config.allow_parallel:
                task = self._execute_hook_async(hook, data, hook.config.timeout_ms)
                tasks.append(task)
            else:
                result = await self._execute_hook(hook, data, hook.config.timeout_ms)
                tasks.append(self._wrap_result(result))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        responses = []
        for r in results:
            if isinstance(r, HookExecutionResult):
                responses.append(AsyncHookResponse(
                    hook_id=r.hook_id,
                    handled=r.success,
                    data=r.response.data if r.response else {},
                    error=r.error,
                ))
            else:
                responses.append(AsyncHookResponse(
                    hook_id="unknown",
                    handled=False,
                    error=str(r),
                ))

        return responses

    async def _execute_hook_async(
        self,
        hook: RegisteredHook,
        data: HookEventData,
        timeout_ms: int,
    ) -> HookExecutionResult:
        """Execute hook asynchronously."""
        return await self._execute_hook(hook, data, timeout_ms)

    async def _wrap_result(self, result: HookExecutionResult) -> HookExecutionResult:
        """Wrap result for async execution."""
        return result

    def set_permission_behavior(
        self,
        event_type: HookEventType,
        behavior: PermissionBehavior,
    ) -> None:
        """Set permission behavior for an event type."""
        self._permission_behaviors[event_type.value] = behavior

    def get_permission_behavior(
        self,
        event_type: HookEventType,
    ) -> PermissionBehavior:
        """Get permission behavior for an event type."""
        return self._permission_behaviors.get(
            event_type.value,
            PermissionBehavior.DEFAULT,
        )

    def inject_system_message(
        self,
        event_type: HookEventType,
        message: str,
    ) -> None:
        """Set a system message to inject for an event type."""
        self._system_messages[event_type] = message

    def get_system_message(
        self,
        event_type: HookEventType,
    ) -> str | None:
        """Get the injected system message for an event type."""
        return self._system_messages.get(event_type)

    def register_hook_metadata(
        self,
        id: str,
        name: str,
        event_type: HookEventType,
        config: HookConfig | None = None,
        description: str | None = None,
    ) -> HookMetadata:
        """Register hook metadata for tracking."""
        metadata = HookMetadata(
            id=id,
            name=name,
            event_type=event_type,
            config=config or HookConfig(),
            description=description,
            registered_at=time.time(),
        )
        self._registered_hooks[id] = metadata
        return metadata

    def get_registered_hooks(self) -> list[HookMetadata]:
        """Get all registered hook metadata."""
        return list(self._registered_hooks.values())

    def get_hook(self, hook_id: str) -> HookMetadata | None:
        """Get metadata for a specific hook."""
        return self._registered_hooks.get(hook_id)

    def unregister_hook(self, hook_id: str) -> bool:
        """Unregister a hook by ID."""
        if hook_id in self._registered_hooks:
            del self._registered_hooks[hook_id]
            return True
        return False

    def get_available_events(self) -> list[dict[str, str]]:
        """Get all available hook event types."""
        return [
            {"value": event.value, "label": event.name.replace("_", " ").title()}
            for event in HookEventType
        ]


# Global singleton
hook_dispatcher = HookDispatcher()
