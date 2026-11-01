from fastapi import FastAPI

from ..agent.agent import AgentRuntime
from ..config.settings import RuntimeSettings
from .routes.chat import router


def mount_runtime(application: FastAPI) -> None:
    application.include_router(router)

    @application.on_event("startup")
    async def start_agent_runtime() -> None:
        runtime = AgentRuntime(RuntimeSettings.load())
        application.state.agent_runtime = runtime
        try:
            await runtime.mcp.start()
        except Exception:
            await runtime.close()
            application.state.agent_runtime = None
            raise

    @application.on_event("shutdown")
    async def stop_agent_runtime() -> None:
        runtime = getattr(application.state, "agent_runtime", None)
        if runtime is not None:
            await runtime.close()