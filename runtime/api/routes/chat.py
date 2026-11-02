import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from agent.agent import AgentRuntime, ExecutionHandle
from ...models.inference import ModelNotLoaded
from ...models.model_manager import ModelManager
from ..schemas.messages import ChatRequest, ConversationCreate


router = APIRouter(prefix="/api/runtime", tags=["LLM and Agent Runtime"])


def _runtime(request: Request) -> AgentRuntime:
    runtime = getattr(request.app.state, "agent_runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="The runtime is not initialized.")
    return runtime


def _event_stream(handle: ExecutionHandle):
    async def stream():
        while True:
            item = await handle.events.get()
            if item["event"] == "end":
                break
            yield (
                f"event: {item['event']}\n"
                f"data: {json.dumps(item['data'], ensure_ascii=False, default=str)}\n\n"
            )
        try:
            await handle.task
        except Exception:
            pass

    return stream()


@router.get("/status")
async def runtime_status(request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    return {
        "model": runtime.model_manager.status,
        "tools": len(runtime.tool_registry.discover()),
        "storage": "sqlite",
    }


@router.get("/models")
async def model_status(request: Request) -> dict[str, Any]:
    return _runtime(request).model_manager.status


@router.post("/models/load")
async def load_model(request: Request, body: dict[str, Any] | None = None) -> dict[str, Any]:
    from ..schemas.messages import ModelLoadRequest
    from ...config.settings import ModelSettings

    runtime = _runtime(request)
    try:
        options = ModelLoadRequest.model_validate(body or {}).model_dump(exclude_none=True)
        settings = ModelSettings.model_validate(
            {**runtime.model_manager.settings.model_dump(), **options}
        )
        return await runtime.model_manager.load(settings)
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/models/unload")
async def unload_model(request: Request) -> dict[str, Any]:
    try:
        return await _runtime(request).model_manager.unload()
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error


@router.get("/config")
async def get_runtime_config(request: Request) -> dict[str, Any]:
    runtime = _runtime(request)
    return {
        "model": {
            **runtime.model_manager.settings.model_dump(exclude={"api_key"}),
            "api_key_configured": bool(runtime.model_manager.settings.api_key),
        },
        "agent": runtime.settings.agent.model_dump(),
        "tools": {
            "workspace_root": runtime.settings.tools.workspace_root,
            "auto_approve_permissions": runtime.settings.tools.auto_approve_permissions,
            "approval_permissions": runtime.settings.tools.approval_permissions,
            "denied_permissions": runtime.settings.tools.denied_permissions,
            "command_timeout_seconds": runtime.settings.tools.command_timeout_seconds,
            "outbound_allowed_hosts": runtime.settings.tools.outbound_allowed_hosts,
        },
    }


@router.get("/tools")
async def list_tools(request: Request) -> list[dict[str, Any]]:
    return [
        {
            **item.model_dump(),
            "schema": item.model_tool_schema(),
        }
        for item in _runtime(request).tool_registry.discover()
    ]


@router.get("/executions/{execution_id}")
async def execution_status(execution_id: str, request: Request) -> dict[str, Any]:
    result = _runtime(request).execution_status(execution_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Execution not found.")
    return result


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(execution_id: str, request: Request) -> dict[str, bool]:
    if not await _runtime(request).cancel(execution_id):
        raise HTTPException(status_code=404, detail="Active execution not found.")
    return {"cancelled": True}


@router.post("/executions/{execution_id}/tools/{tool_call_id}/approval")
async def resolve_approval(
    execution_id: str,
    tool_call_id: str,
    body: Any,
    request: Request,
) -> dict[str, bool]:
    from ..schemas.messages import ApprovalRequest

    approval = ApprovalRequest.model_validate(body)
    if not _runtime(request).approve(execution_id, tool_call_id, approval.approved):
        raise HTTPException(status_code=404, detail="Pending approval not found.")
    return {"resolved": True}


@router.post("/memory")
async def add_memory(body: dict[str, Any], request: Request) -> dict[str, str]:
    content = body.get("content")
    conversation_id = body.get("conversation_id")
    if not isinstance(content, str) or not content.strip() or len(content) > 4000:
        raise HTTPException(status_code=422, detail="Memory content must be 1-4000 characters.")
    return {
        "id": _runtime(request).memory.remember(content, conversation_id)
    }


@router.get("/conversations")
async def list_conversations(request: Request) -> list[dict[str, Any]]:
    return _runtime(request).storage.list_conversations()


@router.post("/conversations")
async def create_conversation(
    body: ConversationCreate, request: Request
) -> dict[str, Any]:
    return _runtime(request).storage.create_conversation(body.title)


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str, request: Request
) -> dict[str, Any]:
    runtime = _runtime(request)
    if not runtime.storage.conversation_exists(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {
        "id": conversation_id,
        "messages": runtime.storage.get_messages(conversation_id),
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request) -> dict[str, bool]:
    if not _runtime(request).storage.delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {"deleted": True}


@router.post("/chat")
async def chat(body: ChatRequest, request: Request):
    runtime = _runtime(request)
    conversation_id = body.conversation_id
    if conversation_id is None:
        conversation_id = runtime.storage.create_conversation(
            body.message[:80]
        )["id"]
    try:
        handle = await runtime.start(
            conversation_id,
            body.message,
            body.attachments,
            body.sampling,
            stream_tokens=body.stream,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ModelNotLoaded as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    if body.stream:
        return StreamingResponse(
            _event_stream(handle),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    try:
        response = await handle.task
    except ModelNotLoaded as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except TimeoutError as error:
        raise HTTPException(status_code=504, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {
        "conversation_id": conversation_id,
        "execution_id": handle.state.execution_id,
        "response": response,
    }