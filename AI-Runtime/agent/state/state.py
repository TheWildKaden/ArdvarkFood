from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    execution_id: str
    conversation_id: str
    status: str = "running"
    step: int = 0
    tool_calls: int = 0
    messages: list[dict[str, Any]] = field(default_factory=list)
    final_response: str | None = None
    error: str | None = None
    cancelled: bool = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "conversation_id": self.conversation_id,
            "status": self.status,
            "step": self.step,
            "tool_calls": self.tool_calls,
            "cancelled": self.cancelled,
            "final_response": self.final_response,
        }