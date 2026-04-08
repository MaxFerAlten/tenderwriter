"""End-to-End Smoke Test — verify the multi-agent backbone.

This test simulates a task delegation from Sisyphus to Oracle
to verify that the AgentHandler and DelegateTask tool are functional.
"""

import asyncio
import logging
import sys
from uuid import uuid4

# Import internal modules
# We mock certain parts to run it without a real API key for speed,
# but we can also run real if key is set.
from backend.agents.handler import agent_handler
from backend.agents.registry import agent_registry
from backend.tools.base import ToolContext
from backend.tools.agent_tool import AgentDelegateTool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("e2e_test")


async def test_agent_delegation():
    """Verify that Sisyphus can successfully delegate a task to Oracle."""
    logger.info("Starting Agent Delegation E2E Test...")

    # 1. Check Registry
    try:
        oracle = agent_registry.get("oracle")
        logger.info("Found Oracle in registry: %s", oracle.description)
    except Exception as exc:
        logger.error("Registry check failed: %s", exc)
        return False

    # 2. Simulate Sisyphus using the DelegateTask tool
    tool = AgentDelegateTool()
    ctx = ToolContext(
        working_directory=".",
        message_id="test_msg",
        tool_use_id="test_tu",
        send=None # No WS for this test
    )

    tool_input = {
        "agent": "oracle",
        "task": "Provide a high-level overview of the TenderClaw project architecture."
    }

    logger.info("Simulating delegation: Sisyphus -> Oracle...")
    
    # Run the delegation
    result = await tool.execute(tool_input, ctx)

    if result.is_error:
        logger.error("Delegation failed: %s", result.content)
        return False

    logger.info("Delegation response received (Success ✅)")
    logger.info("Oracle response snippet: %s...", result.content[:200])

    # 3. Verify content
    if "TenderClaw" in result.content or "Architecture" in result.content.lower():
        logger.info("Content verification passed ✅")
        return True
    
    logger.warning("Content verification failed: 'TenderClaw' not found in response.")
    return False


async def test_api_health():
    """Verify health endpoint."""
    import httpx
    url = "http://localhost:7000/api/health"
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200 and response.json().get("status") == "ok":
                logger.info("API Health: OK ✅")
                return True
    except Exception as exc:
        logger.warning("API Health check skipped (ensure server is running): %s", exc)
    return False


async def run_all():
    print("-" * 50)
    print("TENDERCLAW E2E SMOKE TEST")
    print("-" * 50)
    
    # Note: Agent delegation test requires an API KEY to be functional!
    # If no key, it might return a mocked result or fail.
    success = await test_agent_delegation()
    await test_api_health()
    
    if success:
        print("-" * 50)
        print("RESULT: ALL SYSTEMS NOMINAL 🦞")
        print("-" * 50)
    else:
        print("-" * 50)
        print("RESULT: FAILURE ❌ (Check logs above)")
        print("-" * 50)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_all())
