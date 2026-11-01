import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=2000)
    parameters: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    output_schema: dict[str, Any] | None = None
    permission: str = Field(min_length=1, max_length=128)
    approval_required: bool = False

    @model_validator(mode="after")
    def validate_tool_schema(self) -> "ToolDefinition":
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]*", self.name):
            raise ValueError("Tool names must start with a letter and use . _ - only.")
        if self.parameters.get("type") != "object":
            raise ValueError("Tool parameters must use a JSON object schema.")
        return self

    def model_tool_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }