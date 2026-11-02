"""Inspect and manage durable runtime memories through the runtime API."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Container, Input, Static

from ..services.runtime_api import RuntimeAPIError, request_json


class MemoryPane(Container):
    def compose(self) -> ComposeResult:
        yield Static("Saved memories are retrieved by the agent when relevant.")
        with Horizontal():
            yield Input(placeholder="Search memories", id="memory-query")
            yield Button("Search", id="memory-search", variant="primary")
        yield Static("Connect to the runtime to view saved memories.", id="memory-results")
        with Horizontal():
            yield Input(placeholder="Memory ID", id="memory-id")
            yield Button("Delete memory", id="memory-delete", variant="error")
        with Horizontal():
            yield Input(placeholder="Updated memory text", id="memory-content")
            yield Button("Update memory", id="memory-update", variant="success")

    def on_mount(self) -> None:
        self.run_worker(self.refresh(), exclusive=True)

    async def refresh(self) -> None:
        query = self.query_one("#memory-query", Input).value
        try:
            memories = await request_json(
                "GET",
                "/api/runtime/memory",
                params={"query": query, "limit": 100},
            )
        except RuntimeAPIError as error:
            self.query_one("#memory-results", Static).update(str(error))
            return
        lines = [
            f"{item['id'][:8]} · {item['metadata'].get('scope', 'user')} · "
            f"confidence {item['metadata'].get('confidence', '—')} · "
            f"{item['created_at']}\n  {item['content']}"
            for item in memories
        ]
        self.query_one("#memory-results", Static).update(
            "\n\n".join(lines) if lines else "No saved memories."
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        memory_id = self.query_one("#memory-id", Input).value.strip()
        try:
            if event.button.id == "memory-search":
                await self.refresh()
                return
            if event.button.id == "memory-delete":
                await request_json("DELETE", f"/api/runtime/memory/{memory_id}")
                self.notify("Memory deleted.")
            elif event.button.id == "memory-update":
                content = self.query_one("#memory-content", Input).value
                await request_json(
                    "PATCH",
                    f"/api/runtime/memory/{memory_id}",
                    payload={"content": content},
                )
                self.notify("Memory updated.")
            else:
                return
        except RuntimeAPIError as error:
            self.notify(str(error), severity="error", timeout=8)
            return
        await self.refresh()
