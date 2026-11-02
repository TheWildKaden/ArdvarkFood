import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.memory.memory_manager import MemoryManager
from agent.multimodal.input_router import InputRouter
from runtime.config.settings import RuntimeSettings
from runtime.compiler import ArtifactCompiler, ArtifactWatcher
from runtime.learning.manager import ConversationLearningManager
from runtime.learning.store import LearningStore
from runtime.learning.training import TrainingJobManager
from runtime.models.inference import InferenceEngine, SamplingConfig
from runtime.models.model_manager import ModelManager
from runtime.storage.storage_manager import StorageManager
from runtime.tools.executor.executor import ToolExecutor
from runtime.tools.mcp_manager import MCPManager
from runtime.tools.permissions.permission_manager import PermissionManager
from runtime.tools.registry.registry import ToolRegistry
from .context.context_builder import ContextBuilder
from .loop.agent_loop import AgentLoop
from .planner.planner import Planner
from .state.state import AgentState


logger = logging.getLogger(__name__)


@dataclass
class ExecutionHandle:
    state: AgentState
    events: asyncio.Queue[dict[str, Any]]
    task: asyncio.Task[str]


class AgentRuntime:
    def __init__(
        self,
        settings: RuntimeSettings,
        storage: StorageManager | None = None,
        model_manager: ModelManager | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.settings = settings
        self.storage = storage or StorageManager(settings.storage.database_path)
        self.learning_store = LearningStore(self.storage.database_path)
        self.learning = ConversationLearningManager(
            self.storage,
            self.learning_store,
            minimum_training_examples=settings.learning.minimum_training_examples,
            maximum_dataset_examples=settings.learning.maximum_dataset_examples,
            enabled=settings.learning.enabled,
        )
        self.training = TrainingJobManager(
            self.learning_store,
            output_directory=self.storage.database_path.parent
            / "learning"
            / "models",
            minimum_examples=settings.learning.minimum_training_examples,
            max_sequence_length=settings.learning.max_sequence_length,
            dataset_builder=self.learning.build_dataset,
            automatic_training=settings.learning.automatic_training,
            training_interval_hours=settings.learning.training_interval_hours,
            training_base_model=settings.learning.training_base_model,
        )
        self.compiler = ArtifactCompiler()
        self.watcher: ArtifactWatcher | None = None
        self.model_manager = model_manager or ModelManager(settings.model)
        self.inference = InferenceEngine(self.model_manager)
        self.memory = MemoryManager(self.storage)
        self.planner = Planner(settings.agent.planning_enabled)
        self.context = ContextBuilder(settings, self.storage, self.memory, self.planner)
        self.tool_registry = tool_registry or ToolRegistry()
        self.permissions = PermissionManager(
            auto_approve=settings.tools.auto_approve_permissions,
            approval_required=settings.tools.approval_permissions,
            denied=settings.tools.denied_permissions,
        )
        self.tool_executor = ToolExecutor(
            self.tool_registry, self.permissions, self.storage, settings
        )
        self.mcp = MCPManager(settings, self.tool_registry)
        self.input_router = InputRouter()
        self.loop = AgentLoop(
            settings,
            self.inference,
            self.tool_executor,
            self.context,
            self.storage,
            self.learning,
        )
        self._executions: dict[str, ExecutionHandle] = {}

    def start_background_workers(self) -> None:
        if self.settings.learning.enabled:
            self.learning.start_worker()
            self.training.start_worker()

    async def start(
        self,
        conversation_id: str,
        user_input: str,
        attachments: list[dict[str, Any]] | None = None,
        sampling: SamplingConfig | None = None,
        stream_tokens: bool = True,
    ) -> ExecutionHandle:
        self.start_background_workers()
        if not self.storage.conversation_exists(conversation_id):
            raise KeyError("Conversation not found.")
        if len(user_input) > 32000:
            raise ValueError("Message exceeds the 32,000 character limit.")
        normalized = self.input_router.process(attachments or [])
        execution_id = self.storage.start_execution(conversation_id)
        state = AgentState(execution_id=execution_id, conversation_id=conversation_id)
        events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        async def notify(event: str, data: dict[str, Any]) -> None:
            await events.put({"event": event, "data": data})

        async def execute() -> str:
            try:
                async with asyncio.timeout(self.settings.agent.timeout_seconds):
                    return await self.loop.run(
                        state,
                        user_input,
                        normalized,
                        notify,
                        sampling or SamplingConfig(),
                        stream_tokens=stream_tokens,
                    )
            except asyncio.CancelledError:
                state.status = "cancelled"
                state.cancelled = True
                self.storage.update_execution(
                    execution_id, "cancelled", state.snapshot()
                )
                await notify("cancelled", {"execution_id": execution_id})
                raise
            except Exception as error:
                state.status = "failed"
                state.error = str(error)[:2000]
                self.storage.update_execution(
                    execution_id, "failed", state.snapshot(), state.error
                )
                logger.exception("Agent execution %s failed.", execution_id)
                await notify(
                    "error",
                    {"execution_id": execution_id, "error": state.error},
                )
                raise
            finally:
                await events.put({"event": "end", "data": {}})

        task = asyncio.create_task(execute(), name=f"agent-{execution_id}")
        handle = ExecutionHandle(state=state, events=events, task=task)
        self._executions[execution_id] = handle
        task.add_done_callback(lambda _: self._executions.pop(execution_id, None))
        return handle

    async def cancel(self, execution_id: str) -> bool:
        handle = self._executions.get(execution_id)
        if handle is None or handle.task.done():
            return False
        handle.state.cancelled = True
        handle.state.status = "cancelled"
        self.storage.update_execution(
            execution_id, "cancelled", handle.state.snapshot()
        )
        self.permissions.cancel_execution(execution_id)
        handle.task.cancel()
        return True

    def approve(
        self, execution_id: str, tool_call_id: str, approved: bool
    ) -> bool:
        return self.permissions.resolve(execution_id, tool_call_id, approved)

    def execution_status(self, execution_id: str) -> dict[str, Any] | None:
        return self.storage.get_execution(execution_id)

    async def close(self) -> None:
        for execution_id in list(self._executions):
            await self.cancel(execution_id)
        if self._executions:
            await asyncio.gather(
                *(handle.task for handle in self._executions.values()),
                return_exceptions=True,
            )
        await self.mcp.close()
        if self.watcher is not None:
            await asyncio.to_thread(self.watcher.stop)
            self.watcher = None
        await self.learning.close()
        await self.training.close()
        await self.model_manager.unload()