from typing import Literal

from pydantic import BaseModel, Field, model_validator


MAX_MESSAGE_LENGTH = 8_000
MAX_CONVERSATION_MESSAGES = 32
MAX_IMAGE_PROMPT_LENGTH = 4_000


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(
        min_length=1, max_length=MAX_CONVERSATION_MESSAGES
    )

    @model_validator(mode="after")
    def validate_conversation(self) -> "ChatRequest":
        for index, message in enumerate(self.messages):
            expected_role = "user" if index % 2 == 0 else "assistant"
            if message.role != expected_role:
                raise ValueError("Messages must alternate between user and assistant.")
        if self.messages[-1].role != "user":
            raise ValueError("The conversation must end with a user message.")
        return self


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=MAX_IMAGE_PROMPT_LENGTH)
    steps: int = Field(default=1, ge=1, le=4)
    seed: int | None = Field(default=None, ge=0, le=4_294_967_295)
