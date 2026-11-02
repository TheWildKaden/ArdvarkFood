import asyncio
from dataclasses import dataclass
from typing import Any

from ..tool_definition import ToolDefinition
from ..tool_call import ToolCall


class PermissionDenied(PermissionError):
    pass


@dataclass
class _PendingApproval:
    permission: str
    decision: asyncio.Future[bool]


class PermissionManager:
    """Enforces server-owned allow/deny rules and per-execution approvals."""

    def __init__(
        self,
        auto_approve: list[str] | None = None,
        approval_required: list[str] | None = None,
        denied: list[str] | None = None,
    ) -> None:
        self.auto_approve = set(auto_approve or [])
        self.approval_required = set(approval_required or [])
        self.denied = set(denied or [])
        self._pending: dict[tuple[str, str], _PendingApproval] = {}

    async def authorize(
        self,
        execution_id: str,
        definition: ToolDefinition,
        call: ToolCall,
        notify: Any,
    ) -> None:
        permission = definition.permission
        if permission in self.denied:
            raise PermissionDenied(f"Permission is explicitly denied: {permission}")
        if permission in self.auto_approve:
            return
        if not definition.approval_required and permission not in self.approval_required:
            raise PermissionDenied(f"Permission has not been granted: {permission}")

        key = (execution_id, call.call_id)
        if key in self._pending:
            raise PermissionDenied("This tool call is already awaiting approval.")
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._pending[key] = _PendingApproval(permission=permission, decision=future)
        try:
            await notify(
                "approval_required",
                {
                    "execution_id": execution_id,
                    "tool_call_id": call.call_id,
                    "tool_name": call.name,
                    "permission": permission,
                    "arguments": call.arguments,
                },
            )
            try:
                approved = await asyncio.wait_for(future, timeout=300)
            except TimeoutError as error:
                raise PermissionDenied("Tool approval expired.") from error
            if not approved:
                raise PermissionDenied(f"The user denied permission: {permission}")
        finally:
            self._pending.pop(key, None)

    def resolve(
        self, execution_id: str, tool_call_id: str, approved: bool
    ) -> bool:
        pending = self._pending.get((execution_id, tool_call_id))
        if pending is None or pending.decision.done():
            return False
        pending.decision.set_result(approved)
        return True

    def cancel_execution(self, execution_id: str) -> None:
        for (pending_execution, _), pending in list(self._pending.items()):
            if pending_execution == execution_id and not pending.decision.done():
                pending.decision.set_result(False)