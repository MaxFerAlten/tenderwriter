"""Agent delegation tool — spawn sub-agents for complex tasks.

Inspired by Claude Code's Agent tool and oh-my-openagent's delegate_task.
Allows the main agent to delegate work to specialized sub-agents
that run autonomously and return results.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from backend.schemas.tools import RiskLevel, ToolResult
from backend.tools.base import BaseTool, ToolContext

logger = logging.getLogger("tenderclaw.tools.agent")


class AgentDelegateTool(BaseTool):
    """Delegate a task to a specialized sub-agent."""

    name = "DelegateTask"
    description = (
        "Delegate a task to a specialized sub-agent. The sub-agent runs "
        "autonomously with its own context and returns a result. "
        "Use for complex tasks requiring different expertise or parallel work. "
        "The agent will follow its role (e.g. oracle for research, explorer for code)."
    )
    risk_level = RiskLevel.MEDIUM
    is_read_only = False
    concurrency_safe = False

    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent": {
                    "type": "string",
                    "description": (
                        "Agent to delegate to: oracle (research), explorer (codebase), "
                        "fixer (bugfix), librarian (docs), sentinel (security), scribe (docs)"
                    ),
                },
                "task": {
                    "type": "string",
                    "description": "Description of the task to perform",
                },
                "context": {
                    "type": "string",
                    "description": "Additional context for the sub-agent",
                    "default": "",
                },
            },
            "required": ["agent", "task"],
        }

    async def execute(self, tool_input: dict[str, Any], context: ToolContext) -> ToolResult:
        """Perform the actual delegation to the agent handler."""
        # Note: In a real implementation we would import here to avoid circular dependencies
        from backend.agents.handler import agent_handler
        from backend.agents.registry import agent_registry
        from backend.schemas.ws import WSAgentSwitch

        agent_name = tool_input.get("agent", "").lower()
        task = tool_input.get("task", "")
        extra_context = tool_input.get("context", "")

        try:
            agent = agent_registry.get(agent_name)
        except ValueError as exc:
            return ToolResult(
                tool_use_id=context.tool_use_id,
                content=str(exc),
                is_error=True,
            )

        # Notify frontend of agent switch
        if context.send:
            await context.send(WSAgentSwitch(agent_name=agent_name, task=task).model_dump())

        task_id = f"task_{uuid.uuid4().hex[:8]}"
        logger.info("Delegating to %s [%s]: %s", agent_name, task_id, task[:100])

        # Form a prompt for the sub-agent
        prompt = f"Executing task: {task}\nContext: {extra_context}"
        sub_messages = [{"role": "user", "content": prompt}]

        # Run the agent turn. Note: In Phase 3, this is sequential. 
        # Future phases will support background parallel execution with callbacks.
        results = []
        async for part in agent_handler.execute_agent_turn(
            agent_name=agent_name,
            messages=sub_messages,
        ):
            if part.get("type") == "assistant_text":
                results.append(part["delta"])

        final_response = "".join(results)
        
        # Switch back to sisyphus
        if context.send:
            await context.send(WSAgentSwitch(agent_name="sisyphus").model_dump())

        result_json = {
            "task_id": task_id,
            "agent": agent_name,
            "status": "completed",
            "result": final_response,
        }

        return ToolResult(
            tool_use_id=context.tool_use_id,
            content=json.dumps(result_json, indent=2),
        )
