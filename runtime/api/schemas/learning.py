from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LearningConsent(BaseModel):
    enabled: bool


class ExampleReview(BaseModel):
    approved: bool
    note: str = Field(default="", max_length=1000)


class HuggingFaceImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    split: str = Field(default="train", pattern="^(train|full)$")
    max_samples: int = Field(default=100, ge=1, le=1000)


class TrainingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1, max_length=64)
    base_model: str = Field(min_length=1, max_length=512)
    config: dict[str, Any] = Field(default_factory=dict)


class CompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str = Field(min_length=1, max_length=2048)
    deduplicate: bool = False


class DecompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_name: str = Field(min_length=1, max_length=256)


class WatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directories: list[str] = Field(min_length=1, max_length=16)
    interval_seconds: float = Field(default=1.0, ge=0.1, le=60)
