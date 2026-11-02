from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..config.settings import RuntimeSettings
from agent.agent import AgentRuntime
from .routes.chat import router


def mount_runtime(application: FastAPI) -> None:
    application.include_router(router)
    previous_lifespan = application.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with previous_lifespan(app):
            runtime = AgentRuntime(RuntimeSettings.load())
            app.state.agent_runtime = runtime
            try:
                await runtime.mcp.start()
                yield
            finally:
                await runtime.close()
                app.state.agent_runtime = None

    application.router.lifespan_context = lifespan