from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ...models.inference import SamplingConfig


class ConversationCreate(BaseModel):
    title: str = Field(default="", max_length=256)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=32000)
    attachments: list[dict[str, Any]] = Field(default_factory=list, max_length=8)
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    stream: bool = False


class ApprovalRequest(BaseModel):
    approved: bool


class ModelLoadRequest(BaseModel):
    backend: str | None = Field(default=None, max_length=64)
    model_path: str | None = Field(default=None, max_length=2048)
    model_name: str | None = Field(default=None, max_length=256)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    context_size: int | None = Field(default=None, ge=256, le=131072)
    gpu_layers: int | None = Field(default=None, ge=0, le=256)
    chat_format: str | None = Field(default=None, max_length=128)
    clip_model_path: str | None = Field(default=None, max_length=2048)