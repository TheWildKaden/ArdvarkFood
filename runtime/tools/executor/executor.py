import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from jsonschema import ValidationError, validate

from ...config.settings import RuntimeSettings
from ...storage.storage_manager import StorageManager
from ..permissions.permission_manager import PermissionDenied, PermissionManager
from ..registry.registry import ToolRegistry
from ..tool_call import ToolCall, InvalidToolCall
from ..tool_definition import ToolDefinition
from ..tool_result import ToolResult


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        permissions: PermissionManager,
        storage: StorageManager,
        settings: RuntimeSettings,
    ) -> None:
        self.registry = registry
        self.permissions = permissions
        self.storage = storage
        self.settings = settings
        self.workspace = Path(settings.tools.workspace_root).expanduser().resolve()
        self._register_builtin_tools()

    async def execute(
        self,
        execution_id: str,
        payload: dict[str, Any],
        notify: Any,
    ) -> ToolResult:
        try:
            call = ToolCall.from_model(payload)
        except InvalidToolCall as error:
            return ToolResult(
                call_id="invalid", name="unknown", status="error", content=None, error=str(error)
            )

        try:
            definition, handler = self.registry.get(call.name)
        except KeyError:
            self.storage.add_audit(
                execution_id,
                "tool.unknown",
                {"tool": call.name, "tool_call_id": call.call_id},
            )
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                status="error",
                content=None,
                error="Unknown tool.",
            )

        try:
            validate(instance=call.arguments, schema=definition.parameters)
        except ValidationError as error:
            self.storage.record_tool_event(
                execution_id,
                call.call_id,
                call.name,
                definition.permission,
                "invalid",
                call.arguments,
                {"error": error.message},
            )
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                status="error",
                content=None,
                error=f"Invalid tool arguments: {error.message}",
            )

        self.storage.record_tool_event(
            execution_id,
            call.call_id,
            call.name,
            definition.permission,
            "requested",
            call.arguments,
        )
        try:
            await self.permissions.authorize(execution_id, definition, call, notify)
            result = handler(**call.arguments)
            if asyncio.iscoroutine(result):
                result = await result
            result = self._normalize_output(definition, result)
            self.storage.record_tool_event(
                execution_id,
                call.call_id,
                call.name,
                definition.permission,
                "completed",
                call.arguments,
                result,
            )
            self.storage.add_audit(
                execution_id,
                "tool.completed",
                {"tool": call.name, "permission": definition.permission},
            )
            return ToolResult(
                call_id=call.call_id, name=call.name, status="ok", content=result
            )
        except Exception as error:
            self.storage.record_tool_event(
                execution_id,
                call.call_id,
                call.name,
                definition.permission,
                "failed",
                call.arguments,
                {"error": str(error)[:2000]},
            )
            self.storage.add_audit(
                execution_id,
                "tool.failed",
                {"tool": call.name, "error": str(error)[:500]},
            )
            return ToolResult(
                call_id=call.call_id,
                name=call.name,
                status="error",
                content=None,
                error=str(error)[:2000],
            )

    def _normalize_output(self, definition: ToolDefinition, result: Any) -> Any:
        if definition.output_schema:
            validate(instance=result, schema=definition.output_schema)
        encoded = json.dumps(result, ensure_ascii=False, default=str)
        limit = self.settings.tools.max_tool_output_chars
        if len(encoded) > limit:
            return {"truncated": True, "content": encoded[: limit - 64]}
        return result

    def _register_builtin_tools(self) -> None:
        self._register(
            "filesystem.read",
            "Read a UTF-8 text file inside the configured workspace.",
            {
                "type": "object",
                "properties": {"path": {"type": "string", "maxLength": 1024}},
                "required": ["path"],
                "additionalProperties": False,
            },
            self._read_file,
            read=True,
        )
        self._register(
            "filesystem.list",
            "List entries in a workspace directory.",
            {
                "type": "object",
                "properties": {"path": {"type": "string", "maxLength": 1024}},
                "additionalProperties": False,
            },
            self._list_directory,
            read=True,
        )
        self._register(
            "filesystem.write",
            "Create a UTF-8 workspace file, or update one only when its current SHA-256 is supplied.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "maxLength": 1024},
                    "content": {
                        "type": "string",
                        "maxLength": self.settings.tools.max_tool_output_chars,
                    },
                    "expected_sha256": {
                        "type": "string",
                        "pattern": "^[a-fA-F0-9]{64}$",
                        "description": "Required when replacing an existing file; SHA-256 of its current contents.",
                    },
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            self._write_file,
        )
        self._register(
            "terminal.execute",
            "Run a restricted read-only workspace command (pwd, ls, cat, rg, or git read commands).",
            {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 40,
                        "items": {"type": "string", "maxLength": 2048},
                    }
                },
                "required": ["command"],
                "additionalProperties": False,
            },
            self._terminal,
        )
        self._register(
            "python.execute",
            "Run Python code in an isolated interpreter process (approval required).",
            {
                "type": "object",
                "properties": {"code": {"type": "string", "maxLength": 12000}},
                "required": ["code"],
                "additionalProperties": False,
            },
            self._python,
        )
        self._register(
            "browser.fetch",
            "Fetch an allowlisted public HTTPS page without following redirects.",
            {
                "type": "object",
                "properties": {"url": {"type": "string", "maxLength": 2048}},
                "required": ["url"],
                "additionalProperties": False,
            },
            self._fetch,
        )
        self._register(
            "api.request",
            "Make an allowlisted HTTPS GET or JSON POST request (approval required).",
            {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": ["GET", "POST"]},
                    "url": {"type": "string", "maxLength": 2048},
                    "json_body": {"type": "object"},
                },
                "required": ["method", "url"],
                "additionalProperties": False,
            },
            self._api_request,
        )
        self._register(
            "git.status",
            "Get the current git status for the configured workspace.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            lambda: self._run_git(["status", "--short", "--branch"]),
            read=True,
        )
        self._register(
            "git.diff",
            "Get a bounded git diff for the configured workspace.",
            {"type": "object", "properties": {}, "additionalProperties": False},
            lambda: self._run_git(["diff", "--"]),
            read=True,
        )

    def _register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Any,
        *,
        read: bool = False,
    ) -> None:
        if name.startswith("git.") and read:
            permission = "git.read"
        elif name.startswith("filesystem.") and read:
            permission = "filesystem.read"
        else:
            permission = name
        self.registry.register(
            ToolDefinition(
                name=name,
                description=description,
                parameters=parameters,
                permission=permission,
                approval_required=not read,
            ),
            handler,
        )

    def _resolve_path(self, supplied: str) -> Path:
        candidate = Path(supplied)
        if not candidate.is_absolute():
            candidate = self.workspace / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self.workspace)
        except ValueError as error:
            raise PermissionDenied("Filesystem access is restricted to the workspace.") from error
        return resolved

    def _read_file(self, path: str) -> dict[str, Any]:
        target = self._resolve_path(path)
        if not target.is_file():
            raise FileNotFoundError("The requested workspace file does not exist.")
        content_bytes = target.read_bytes()
        content = content_bytes.decode("utf-8")
        limit = self.settings.tools.max_tool_output_chars
        return {"path": str(target.relative_to(self.workspace)), "content": content[:limit],
                "sha256": hashlib.sha256(content_bytes).hexdigest(),
                "truncated": len(content) > limit}

    def _list_directory(self, path: str = ".") -> dict[str, Any]:
        target = self._resolve_path(path)
        if not target.is_dir():
            raise NotADirectoryError("The requested workspace path is not a directory.")
        entries = sorted(item.name for item in target.iterdir())[:500]
        return {"path": str(target.relative_to(self.workspace)), "entries": entries}

    def _write_file(
        self, path: str, content: str, expected_sha256: str | None = None
    ) -> dict[str, Any]:
        target = self._resolve_path(path)
        exists = target.exists()
        if exists and not target.is_file():
            raise PermissionDenied("Only regular files can be replaced.")
        if exists:
            if expected_sha256 is None:
                raise PermissionDenied(
                    "Replacing an existing file requires its current SHA-256."
                )
            current_sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
            if not hmac.compare_digest(
                current_sha256, expected_sha256.lower()
            ):
                raise PermissionDenied(
                    "The file changed since it was read; read it again before proposing an update."
                )
        elif expected_sha256 is not None:
            raise PermissionDenied(
                "The expected SHA-256 was provided, but the file does not exist."
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        content_bytes = content.encode("utf-8")
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=f".{target.name}.", dir=target.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(content_bytes)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            if exists:
                os.chmod(temporary_path, target.stat().st_mode)
            os.replace(temporary_path, target)
        except Exception:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
            raise

        return {
            "path": str(target.relative_to(self.workspace)),
            "bytes": len(content_bytes),
            "sha256": hashlib.sha256(content_bytes).hexdigest(),
            "created": not exists,
        }

    async def _terminal(self, command: list[str]) -> dict[str, Any]:
        executable, *args = command
        if executable not in {"pwd", "ls", "cat", "rg", "git"}:
            raise PermissionDenied("This terminal command is not in the read-only allowlist.")
        if any(arg.startswith("/") or ".." in Path(arg).parts for arg in args):
            raise PermissionDenied("Terminal paths must remain inside the workspace.")
        if executable == "git" and (
            not args
            or args[0]
            not in {"status", "diff", "log", "branch", "rev-parse", "show"}
        ):
            raise PermissionDenied("Only read-only git subcommands are allowed.")
        if executable == "rg" and not any(not arg.startswith("-") for arg in args):
            args.append(".")
        return await asyncio.to_thread(self._run_command, [executable, *args])

    async def _python(self, code: str) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._run_command,
            ["python3", "-I", "-c", code],
        )

    async def _run_git(self, args: list[str]) -> dict[str, Any]:
        return await asyncio.to_thread(self._run_command, ["git", *args])

    def _run_command(self, command: list[str]) -> dict[str, Any]:
        completed = subprocess.run(
            command,
            cwd=self.workspace,
            capture_output=True,
            text=True,
            timeout=self.settings.tools.command_timeout_seconds,
            check=False,
            shell=False,
        )
        limit = self.settings.tools.max_tool_output_chars
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout[:limit],
            "stderr": completed.stderr[:limit],
            "truncated": len(completed.stdout) > limit or len(completed.stderr) > limit,
        }

    async def _validate_public_https(self, url: str):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise PermissionDenied(
                "Only allowlisted HTTPS URLs on port 443 without credentials are allowed."
            )
        hostname = parsed.hostname.lower().rstrip(".")
        allowed = {
            entry.lower().strip().lstrip(".").rstrip(".")
            for entry in self.settings.tools.outbound_allowed_hosts
        }
        if not any(
            hostname == entry or hostname.endswith("." + entry) for entry in allowed
        ):
            raise PermissionDenied("The requested host is not in the outbound allowlist.")
        try:
            addresses = await asyncio.to_thread(
                socket.getaddrinfo, hostname, 443, type=socket.SOCK_STREAM
            )
        except OSError as error:
            raise ValueError("The requested host could not be resolved.") from error
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise PermissionDenied("Requests to private or reserved network addresses are blocked.")
        return hostname

    async def _fetch(self, url: str) -> dict[str, Any]:
        await self._validate_public_https(url)
        return await self._request_public_https("GET", url)

    async def _api_request(
        self, method: str, url: str, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if method == "GET" and json_body is not None:
            raise ValueError("GET requests cannot include a JSON body.")
        await self._validate_public_https(url)
        return await self._request_public_https(method, url, json_body)

    async def _request_public_https(
        self, method: str, url: str, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        limit = self.settings.tools.max_tool_output_chars
        async with httpx.AsyncClient(
            timeout=10.0, follow_redirects=False, trust_env=False
        ) as client:
            async with client.stream(
                method,
                url,
                json=json_body if method == "POST" else None,
                headers={"User-Agent": "ArdvarkRuntime/1.0"},
            ) as response:
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    remaining = limit + 1 - len(content)
                    content.extend(chunk[:remaining])
                    if len(content) > limit:
                        break
                truncated = len(content) > limit
                body = bytes(content[:limit]).decode(
                    response.encoding or "utf-8", errors="replace"
                )
                return {
                    "status_code": response.status_code,
                    "content": body,
                    "truncated": truncated,
                }