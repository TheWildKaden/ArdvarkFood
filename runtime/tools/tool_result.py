import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    name: str
    status: str
    content: Any
    error: str | None = None

    def to_message(self) -> dict[str, str]:
        value = {"status": self.status, "result": self.content}
        if self.error:
            value["error"] = self.error
        return {
            "role": "tool",
            "tool_call_id": self.call_id,
            "name": self.name,
            "content": json.dumps(value, ensure_ascii=False, default=str),
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)