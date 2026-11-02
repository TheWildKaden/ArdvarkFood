"""Review registered model versions and request guarded activation or rollback."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from ..services.runtime_api import RuntimeAPIError, request_json


class ModelsPane(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("Only evaluated GGUF exports can be activated in the llama.cpp runtime.")
        with Horizontal():
            yield Input(placeholder="Registered model ID", id="model-id")
            yield Button("Activate evaluated model", id="model-activate", variant="primary")
            yield Button("Rollback", id="model-rollback", variant="warning")
        yield Static("Registered models appear here.", id="model-results")

    def on_mount(self) -> None:
        self.run_worker(self.refresh(), exclusive=True)

    async def refresh(self) -> None:
        try:
            status = await request_json("GET", "/api/runtime/learning/status")
        except RuntimeAPIError as error:
            self.query_one("#model-results", Static).update(str(error))
            return
        models = status["models"]
        self.query_one("#model-results", Static).update(
            "\n\n".join(
                f"{item['id']} · {item['status']} · {item['method']} · "
                f"{item['export_format']} · compatible={item['compatible']}\n"
                f"Base: {item['base_model']}\n"
                f"Evaluation: {item['evaluation_metrics']}"
                for item in models
            )
            or "No registered models."
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        try:
            if event.button.id == "model-activate":
                model_id = self.query_one("#model-id", Input).value.strip()
                await request_json(
                    "POST", f"/api/runtime/models/{model_id}/activate"
                )
                self.notify("Model activated.")
            elif event.button.id == "model-rollback":
                await request_json("POST", "/api/runtime/models/rollback")
                self.notify("Model rolled back.")
            else:
                return
        except RuntimeAPIError as error:
            self.notify(str(error), severity="error", timeout=10)
            return
        await self.refresh()
