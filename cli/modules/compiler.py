"""Compile, inspect, and watch supported data artifacts via the runtime API."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from ..services.runtime_api import RuntimeAPIError, request_json


class CompilerPane(Vertical):
    def compose(self) -> ComposeResult:
        yield Static(
            "JSON and JSONL only. Source files are never overwritten; builds are cached and traceable."
        )
        with Horizontal():
            yield Input(placeholder="Workspace-relative JSON or JSONL source", id="compile-source")
            yield Button("Compile", id="compile-run", variant="primary")
        with Horizontal():
            yield Input(placeholder="Compiled artifact filename", id="decompile-name")
            yield Button("Decompile", id="decompile-run")
        with Horizontal():
            yield Input(placeholder="Workspace-relative directory", id="watch-directory")
            yield Button("Start watch", id="watch-start", variant="success")
            yield Button("Stop watch", id="watch-stop", variant="error")
        yield Static("Compiler builds appear here.", id="compiler-results")

    def on_mount(self) -> None:
        self.run_worker(self.refresh(), exclusive=True)

    async def refresh(self) -> None:
        try:
            result = await request_json("GET", "/api/runtime/compiler/status")
        except RuntimeAPIError as error:
            self.query_one("#compiler-results", Static).update(str(error))
            return
        builds = result["builds"]
        details = "\n".join(
            f"{item['created_at']} · {item['status']} · {item['source_name']} → "
            f"{item['artifact_name']} · {item['details']}"
            for item in builds
        )
        self.query_one("#compiler-results", Static).update(
            f"Watcher: {'running' if result['watching'] else 'stopped'}\n"
            + (details or "No compiler builds.")
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        try:
            if event.button.id == "compile-run":
                source = self.query_one("#compile-source", Input).value.strip()
                result = await request_json(
                    "POST",
                    "/api/runtime/compiler/compile",
                    payload={"source_path": source, "deduplicate": False},
                )
                self.notify(
                    f"Compiled {result['records']} records · "
                    f"{result['source_size_bytes']} → {result['output_size_bytes']} bytes."
                )
            elif event.button.id == "decompile-run":
                name = self.query_one("#decompile-name", Input).value.strip()
                result = await request_json(
                    "POST",
                    "/api/runtime/compiler/decompile",
                    payload={"artifact_name": name},
                )
                self.notify(
                    f"Decompiled {result['records']} records; exact source restored: "
                    f"{result['exact_source_recovered']}."
                )
            elif event.button.id == "watch-start":
                directory = self.query_one("#watch-directory", Input).value.strip()
                result = await request_json(
                    "POST",
                    "/api/runtime/compiler/watch",
                    payload={"directories": [directory]},
                )
                self.notify(f"Watching {len(result['directories'])} directory.")
            elif event.button.id == "watch-stop":
                await request_json("DELETE", "/api/runtime/compiler/watch")
                self.notify("Compiler watcher stopped.")
            else:
                return
        except RuntimeAPIError as error:
            self.notify(str(error), severity="error", timeout=10)
            return
        await self.refresh()
