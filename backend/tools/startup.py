"""Register all built-in tools at startup."""

import logging
from backend.tools.registry import ToolRegistry

logger = logging.getLogger("tenderclaw.tools")


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register all built-in tools into the registry."""
    from backend.tools.bash_tool import BashTool
    from backend.tools.file_read_tool import FileReadTool
    from backend.tools.file_write_tool import FileWriteTool
    from backend.tools.file_edit_tool import FileEditTool
    from backend.tools.glob_tool import GlobTool
    from backend.tools.grep_tool import GrepTool
    from backend.tools.hashline_read_tool import HashlineReadTool
    from backend.tools.hashline_edit_tool import HashlineEditTool
    from backend.tools.web_search_tool import WebSearchTool
    from backend.tools.agent_tool import AgentDelegateTool
    from backend.tools.ast_grep_tool import AstGrepTool
    from backend.tools.lsp_tools import (
        LspGotoDefinitionTool,
        LspFindReferencesTool,
        LspDiagnosticsTool,
    )

    tools = [
        BashTool(),
        FileReadTool(),
        FileWriteTool(),
        FileEditTool(),
        HashlineReadTool(),
        HashlineEditTool(),
        GlobTool(),
        GrepTool(),
        WebSearchTool(),
        AgentDelegateTool(),
        AstGrepTool(),
        LspGotoDefinitionTool(),
        LspFindReferencesTool(),
        LspDiagnosticsTool(),
    ]

    for tool in tools:
        registry.register(tool)
    
    _register_mcp_tools(registry)
    
    logger.info("Registered %d built-in tools", len(tools))


def _register_mcp_tools(registry: ToolRegistry) -> None:
    """Register tools from connected MCP servers."""
    try:
        from backend.mcp.bridge import create_mcp_tool_proxies
        
        mcp_tools = create_mcp_tool_proxies()
        for tool in mcp_tools:
            registry.register(tool)
        
        if mcp_tools:
            logger.info("Registered %d MCP tools", len(mcp_tools))
    except Exception as exc:
        logger.warning("Could not register MCP tools: %s", exc)
