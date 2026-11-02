import json
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


class InvalidToolCall(ValueError):
    pass


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]

    @classmethod
    def from_model(cls, payload: dict[str, Any]) -> "ToolCall":
        if not isinstance(payload, dict):
            raise InvalidToolCall("The model returned a malformed tool call.")
        function = payload.get("function")
        if not isinstance(function, dict):
            raise InvalidToolCall("The model returned a tool call without a function.")
        name = function.get("name")
        raw_arguments = function.get("arguments", "{}")
        if not isinstance(name, str) or not name or len(name) > 128:
            raise InvalidToolCall("The model returned a tool call without a name.")
        if isinstance(raw_arguments, str):
            if len(raw_arguments) > 16000:
                raise InvalidToolCall("Tool arguments exceed the maximum size.")
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as error:
                raise InvalidToolCall("The model returned invalid tool-call JSON.") from error
        else:
            arguments = raw_arguments
        if not isinstance(arguments, dict):
            raise InvalidToolCall("Tool arguments must be a JSON object.")
        if len(json.dumps(arguments, ensure_ascii=False)) > 16000:
            raise InvalidToolCall("Tool arguments exceed the maximum size.")

        call_id = payload.get("id")
        if not isinstance(call_id, str) or not call_id:
            call_id = "call-" + uuid4().hex
        return cls(call_id=call_id[:128], name=name, arguments=arguments)