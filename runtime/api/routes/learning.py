from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from agent.agent import AgentRuntime
from runtime.config.settings import ModelSettings
from runtime.compiler import ArtifactWatcher
from ..schemas.learning import (
    CompileRequest,
    DecompileRequest,
    ExampleReview,
    HuggingFaceImport,
    LearningConsent,
    TrainingRequest,
    WatchRequest,
)


router = APIRouter(prefix="/api/runtime", tags=["Learning and Compiler"])


def _runtime(request: Request) -> AgentRuntime:
    runtime = getattr(request.app.state, "agent_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="The runtime is not initialized.")
    return runtime


def _workspace_file(runtime: AgentRuntime, value: str, *, must_exist: bool) -> Path:
    root = Path(runtime.settings.tools.workspace_root).expanduser().resolve(strict=True)
    candidate = Path(value).expanduser()
    candidate = candidate if candidate.is_absolute() else root / candidate
    try:
        path = candidate.resolve(strict=must_exist)
    except OSError as error:
        raise HTTPException(status_code=404, detail="Workspace path was not found.") from error
    if root not in path.parents and path != root:
        raise HTTPException(status_code=403, detail="Path is outside the configured workspace.")
    return path


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)


@router.get("/memory")
async def list_memories(
    request: Request,
    query: str = Query(default="", max_length=400),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    runtime = _runtime(request)
    if query.strip():
        return runtime.storage.search_memories(query, limit)
    return runtime.storage.list_memories(limit)


@router.patch("/memory/{memory_id}")
async def update_memory(
    memory_id: str, body: MemoryUpdate, request: Request
) -> dict[str, bool]:
    runtime = _runtime(request)
    from runtime.learning.privacy import contains_sensitive_data

    if contains_sensitive_data(body.content):
        raise HTTPException(status_code=422, detail="Memory contains private or sensitive data.")
    if not runtime.storage.update_memory(memory_id, body.content.strip()):
        raise HTTPException(status_code=404, detail="Memory not found.")
    runtime.storage.add_audit(None, "memory.updated", {"memory_id": memory_id})
    return {"updated": True}


@router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str, request: Request) -> dict[str, bool]:
    runtime = _runtime(request)
    if not runtime.storage.delete_memory(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found.")
    runtime.storage.add_audit(None, "memory.deleted", {"memory_id": memory_id})
    return {"deleted": True}


@router.put("/conversations/{conversation_id}/learning")
async def set_conversation_learning(
    conversation_id: str, body: LearningConsent, request: Request
) -> dict[str, bool]:
    runtime = _runtime(request)
    try:
        runtime.learning.set_conversation_learning(conversation_id, body.enabled)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if body.enabled:
        runtime.start_background_workers()
    runtime.storage.add_audit(
        None,
        "conversation.learning_consent",
        {"conversation_id": conversation_id, "enabled": body.enabled},
    )
    return {"enabled": body.enabled}


@router.post("/learning/conversations/{conversation_id}/examples")
async def queue_training_examples(
    conversation_id: str, request: Request
) -> dict[str, str]:
    runtime = _runtime(request)
    if not runtime.storage.conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if not runtime.learning_store.conversation_learning_enabled(conversation_id):
        raise HTTPException(
            status_code=409,
            detail="Enable learning for this conversation before reviewing its examples.",
        )
    job_id = runtime.learning.queue_training_examples(conversation_id)
    runtime.start_background_workers()
    return {"queue_id": job_id, "status": "queued"}


@router.get("/learning/status")
async def learning_status(request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    return {
        **runtime.learning_store.get_status_counts(),
        "examples": runtime.learning_store.list_examples(limit=100),
        "training_jobs": runtime.learning_store.list_training_jobs(limit=50),
        "datasets": runtime.learning_store.list_datasets(limit=50),
        "models": runtime.learning_store.list_models(),
        "active_model": runtime.model_manager.status,
        "training_enabled": runtime.settings.learning.enabled,
        "minimum_training_examples": runtime.settings.learning.minimum_training_examples,
    }


@router.get("/learning/examples")
async def list_training_examples(
    request: Request,
    status: str | None = Query(default=None, pattern="^(pending_review|approved|rejected)$"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    try:
        return _runtime(request).learning_store.list_examples(status, limit)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.patch("/learning/examples/{example_id}")
async def review_training_example(
    example_id: str, body: ExampleReview, request: Request
) -> dict[str, bool]:
    runtime = _runtime(request)
    if not runtime.learning_store.review_example(
        example_id, body.approved, body.note
    ):
        raise HTTPException(
            status_code=404, detail="Pending training example not found."
        )
    runtime.storage.add_audit(
        None,
        "training_example.reviewed",
        {"example_id": example_id, "approved": body.approved},
    )
    return {"reviewed": True, "approved": body.approved}


@router.delete("/learning/examples/{example_id}")
async def delete_training_example(
    example_id: str, request: Request
) -> dict[str, bool]:
    runtime = _runtime(request)
    if not runtime.learning_store.delete_example(example_id):
        raise HTTPException(
            status_code=404,
            detail="Example not found or already included in a dataset; rebuild the dataset first.",
        )
    runtime.storage.add_audit(None, "training_example.deleted", {"example_id": example_id})
    return {"deleted": True}


@router.post("/learning/import/huggingface")
async def import_huggingface_dataset(
    body: HuggingFaceImport, request: Request
) -> dict[str, Any]:
    runtime = _runtime(request)
    if not runtime.settings.learning.enabled:
        raise HTTPException(status_code=409, detail="Learning is disabled in runtime settings.")
    try:
        result = await runtime.learning.import_huggingface_dataset(
            split=body.split,
            max_samples=min(
                body.max_samples, runtime.settings.learning.maximum_dataset_examples
            ),
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    runtime.storage.add_audit(
        None,
        "learning.dataset.imported",
        {
            "dataset": result["dataset"],
            "split": result["split"],
            "processed": result["processed"],
            "imported": result["imported"],
        },
    )
    return result


@router.post("/learning/datasets")
async def build_training_dataset(request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    try:
        return await asyncio.to_thread(runtime.learning.build_dataset)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (OSError, RuntimeError) as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.post("/learning/training")
async def queue_training(body: TrainingRequest, request: Request) -> dict[str, str]:
    runtime = _runtime(request)
    if not runtime.settings.learning.enabled:
        raise HTTPException(status_code=409, detail="Learning is disabled in runtime settings.")
    try:
        job_id = runtime.training.queue(body.dataset_id, body.base_model, body.config)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    runtime.start_background_workers()
    return {"job_id": job_id, "status": "queued"}


@router.post("/learning/training/{job_id}/cancel")
async def cancel_training(job_id: str, request: Request) -> dict[str, bool]:
    if not _runtime(request).learning_store.cancel_training_job(job_id):
        raise HTTPException(status_code=404, detail="Queued or running training job not found.")
    return {"cancelled": True}


@router.post("/models/{model_id}/activate")
async def activate_model(model_id: str, request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    model = runtime.learning_store.get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Registered model not found.")
    if (
        not model["compatible"]
        or model["export_format"] != "gguf:q4_k_m"
        or model["evaluation_metrics"].get("passed") is not True
    ):
        raise HTTPException(
            status_code=409,
            detail="Only evaluated, compatible GGUF models can be activated.",
        )
    model_path = Path(model["adapter_path"]).resolve(strict=True)
    allowed_root = (
        runtime.learning_store.database_path.parent / "learning" / "models"
    ).resolve()
    if allowed_root not in model_path.parents or not model_path.is_file():
        raise HTTPException(status_code=409, detail="Registered model artifact is unavailable.")
    settings = ModelSettings.model_validate(
        {
            **runtime.model_manager.settings.model_dump(),
            "backend": "llama_cpp",
            "model_path": str(model_path),
            "model_name": f"ardvark-{model_id[:8]}",
        }
    )
    try:
        status = await runtime.model_manager.load(settings)
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not runtime.learning_store.activate_model(model_id):
        raise HTTPException(status_code=409, detail="Model evaluation gate was not satisfied.")
    return {"activated": True, "model": model_id, "runtime": status}


@router.post("/models/rollback")
async def rollback_model(request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    model_id = runtime.learning_store.rollback_model_id()
    if model_id is None:
        raise HTTPException(status_code=404, detail="No previous registered model is available.")
    model = runtime.learning_store.get_model(model_id)
    if model is None or not model["evaluation_metrics"].get("passed"):
        raise HTTPException(status_code=409, detail="Previous model did not pass evaluation.")
    model_path = Path(model["adapter_path"]).resolve(strict=True)
    settings = ModelSettings.model_validate(
        {
            **runtime.model_manager.settings.model_dump(),
            "backend": "llama_cpp",
            "model_path": str(model_path),
            "model_name": f"ardvark-{model_id[:8]}",
        }
    )
    try:
        status = await runtime.model_manager.load(settings)
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    if not runtime.learning_store.activate_model(model_id):
        raise HTTPException(status_code=409, detail="Previous model could not be activated.")
    return {"rolled_back": True, "model": model_id, "runtime": status}


@router.get("/compiler/status")
async def compiler_status(request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    return {
        "watching": bool(runtime.watcher and runtime.watcher.running),
        "builds": runtime.learning_store.list_compiler_builds(50),
    }


@router.post("/compiler/compile")
async def compile_artifact(body: CompileRequest, request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    source = _workspace_file(runtime, body.source_path, must_exist=True)
    if source.suffix.lower() not in {".json", ".jsonl"}:
        raise HTTPException(status_code=422, detail="Only JSON and JSONL sources are supported.")
    root = Path(runtime.settings.tools.workspace_root).expanduser().resolve()
    output_directory = runtime.learning_store.database_path.parent / "learning" / "compiled"
    output = output_directory / source.relative_to(root)
    output = output.with_name(output.name + ".min")
    output = output.with_suffix(output.suffix + source.suffix.lower())
    try:
        result = await asyncio.to_thread(
            runtime.compiler.compile, source, output, deduplicate=body.deduplicate
        )
    except (ValueError, OSError) as error:
        runtime.learning_store.record_compiler_build(
            source.name, output.name, "error", {"error": type(error).__name__}
        )
        raise HTTPException(status_code=422, detail=str(error)) from error
    runtime.learning_store.record_compiler_build(
        source.name,
        output.name,
        "cached" if result["cache_hit"] else "built",
        {
            "source_size_bytes": result["source_size_bytes"],
            "output_size_bytes": result["output_size_bytes"],
            "size_ratio": result["size_ratio"],
            "records": result["records"],
            "deduplicated": result["deduplicated"],
        },
    )
    return result


@router.post("/compiler/decompile")
async def decompile_artifact(
    body: DecompileRequest, request: Request
) -> dict[str, Any]:
    runtime = _runtime(request)
    if Path(body.artifact_name).name != body.artifact_name:
        raise HTTPException(status_code=422, detail="Artifact name must be a basename.")
    compiled_directory = (
        runtime.learning_store.database_path.parent / "learning" / "compiled"
    ).resolve()
    try:
        compiled = (compiled_directory / body.artifact_name).resolve(strict=True)
    except OSError as error:
        raise HTTPException(status_code=404, detail="Compiled artifact was not found.") from error
    if compiled_directory not in compiled.parents or not compiled.is_file():
        raise HTTPException(status_code=404, detail="Compiled artifact was not found.")
    output_directory = (
        runtime.learning_store.database_path.parent / "learning" / "decompiled"
    )
    output = output_directory / f"{compiled.name}.readable"
    try:
        result = await asyncio.to_thread(
            runtime.compiler.decompile, compiled, output
        )
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "output_path": result.output_path,
        "records": result.records,
        "exact_source_recovered": result.exact_source_recovered,
        "notes": result.notes,
    }


@router.post("/compiler/watch")
async def start_compiler_watch(body: WatchRequest, request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    directories = [
        _workspace_file(runtime, value, must_exist=True) for value in body.directories
    ]
    if any(not directory.is_dir() for directory in directories):
        raise HTTPException(status_code=422, detail="All watch paths must be directories.")
    output_directory = (
        runtime.learning_store.database_path.parent / "learning" / "compiled"
    )

    def record_build(result: dict[str, Any]) -> None:
        runtime.learning_store.record_compiler_build(
            Path(result.get("source", result.get("source_path", "unknown"))).name,
            Path(result.get("output_path", "")).name,
            result.get("status", "built"),
            {
                key: result[key]
                for key in ("error", "source_size_bytes", "output_size_bytes", "size_ratio")
                if key in result
            },
        )

    try:
        if runtime.watcher is not None:
            await asyncio.to_thread(runtime.watcher.stop)
        runtime.watcher = ArtifactWatcher(
            directories,
            output_directory,
            interval_seconds=body.interval_seconds,
            on_build=record_build,
        )
        runtime.watcher.start()
    except (ValueError, OSError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"watching": True, "directories": [str(path) for path in directories]}


@router.delete("/compiler/watch")
async def stop_compiler_watch(request: Request) -> dict[str, bool]:
    runtime = _runtime(request)
    if runtime.watcher is not None:
        await asyncio.to_thread(runtime.watcher.stop)
        runtime.watcher = None
    return {"watching": False}
