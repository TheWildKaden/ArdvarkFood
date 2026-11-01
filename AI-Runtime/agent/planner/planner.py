from typing import Any


class Planner:
    """Produces an optional lightweight plan using the configured model."""

    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled

    def planning_instruction(self, user_message: str) -> dict[str, Any] | None:
        if not self.enabled or not user_message.strip():
            return None
        return {
            "role": "system",
            "content": (
                "For complex tasks, think through a concise plan before acting. "
                "Do not expose private chain-of-thought; provide only the answer "
                "and any brief high-level plan the user needs."
            ),
        }