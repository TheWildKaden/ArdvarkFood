import re
from contextlib import AsyncExitStack
from typing import Any

from ..config.settings import RuntimeSettings
from .registry.registry import ToolRegistry
from .tool_definition import ToolDefinition


class MCPManager:
    """Connects explicitly configured stdio MCP servers and registers their tools."""

    def __init__(self, settings: RuntimeSettings, registry: ToolRegistry) -> None:
        self.settings = settings
        self.registry = registry
        self._stack: AsyncExitStack | None = None
        self._sessions: list[Any] = []

    async def start(self) -> None:
        if not self.settings.tools.mcp_servers:
            return
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as error:
            raise RuntimeError(
                "MCP servers are configured but the optional `mcp` package is missing."
            ) from error

        stack = AsyncExitStack()
        await stack.__aenter__()
        try:
            for server_name, config in self.settings.tools.mcp_servers.items():
                command = config.get("command")
                args = config.get("args", [])
                env = config.get("env")
                if (
                    not isinstance(command, str)
                    or not command
                    or not isinstance(args, list)
                    or not all(isinstance(arg, str) for arg in args)
                    or (env is not None and not isinstance(env, dict))
                ):
                    raise ValueError(f"Invalid MCP stdio configuration for {server_name}.")
                parameters = StdioServerParameters(
                    command=command,
                    args=args,
                    env=env,
                )
                read_stream, write_stream = await stack.enter_async_context(
                    stdio_client(parameters)
                )
                session = await stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()
                self._sessions.append(session)
                listed = await session.list_tools()
                for remote_tool in listed.tools:
                    suffix = re.sub(r"[^a-zA-Z0-9_.-]", "_", remote_tool.name)
                    tool_name = f"mcp.{server_name}.{suffix}"

                    async def invoke(
                        _session: Any = session,
                        _name: str = remote_tool.name,
                        **arguments: Any,
                    ) -> Any:
                        result = await _session.call_tool(_name, arguments=arguments)
                        if result.isError:
                            raise RuntimeError("The MCP tool reported an execution error.")
                        structured = getattr(result, "structuredContent", None)
                        if structured is not None:
                            return structured
                        return [
                            item.text
                            for item in result.content
                            if getattr(item, "type", None) == "text"
                        ]

                    self.registry.register(
                        ToolDefinition(
                            name=tool_name,
                            description=remote_tool.description or "MCP-provided tool.",
                            parameters=remote_tool.inputSchema
                            or {"type": "object", "properties": {}},
                            permission="mcp.call",
                            approval_required=True,
                        ),
                        invoke,
                    )
        except Exception:
            await stack.aclose()
            self._sessions.clear()
            raise
        self._stack = stack

    async def close(self) -> None:
        if self._stack is not None:
            stack, self._stack = self._stack, None
            await stack.aclose()
        self._sessions.clear()
