"""Review learning examples and explicitly manage dataset/training jobs."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from ..services.runtime_api import RuntimeAPIError, request_json


class LearningPane(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("Conversation learning is opt-in. Training always requires review.")
        with Horizontal():
            yield Button("Refresh", id="learning-refresh")
            yield Button("Import Fable dataset (100)", id="learning-import")
            yield Button("Build approved dataset", id="learning-build")
        yield Static("Runtime learning status unavailable.", id="learning-status")
        with Horizontal():
            yield Input(placeholder="Example ID", id="example-id")
            yield Button("Approve", id="example-approve", variant="success")
            yield Button("Reject", id="example-reject", variant="error")
            yield Button("Remove", id="example-delete")
        yield Static("Pending examples appear here after opt-in.", id="learning-examples")
        with Horizontal():
            yield Input(placeholder="Dataset ID", id="training-dataset")
            yield Input(placeholder="HF model ID or local model path", id="training-base")
            yield Button("Queue fine-tuning", id="training-start", variant="primary")
        yield Static("Training job status appears above.", id="training-notice")

    def on_mount(self) -> None:
        self.run_worker(self.refresh(), exclusive=True)

    async def refresh(self) -> None:
        try:
            status = await request_json("GET", "/api/runtime/learning/status")
            examples = await request_json(
                "GET",
                "/api/runtime/learning/examples",
                params={"status": "pending_review", "limit": 50},
            )
        except RuntimeAPIError as error:
            self.query_one("#learning-status", Static).update(str(error))
            return
        summary = (
            f"Learning queue: {status['queued_learning']} · "
            f"Processed conversations: {status['processed_conversations']} · "
            f"Pending review: {status['candidate_examples']} · "
            f"Approved: {status['approved_examples']} · "
            f"Training jobs: {status['training_jobs']} · "
            f"Failures: {status['failed_jobs']}\n"
            f"Minimum approved examples: {status['minimum_training_examples']}\n"
            f"Models: {len(status['models'])} · Datasets: {len(status['datasets'])}"
        )
        self.query_one("#learning-status", Static).update(summary)
        self.query_one("#training-notice", Static).update(
            "\n".join(
                f"{job['id'][:8]} · {job['status']} · {job['base_model']}"
                for job in status["training_jobs"][:10]
            )
            or "No training jobs."
        )
        self.query_one("#learning-examples", Static).update(
            "\n\n".join(
                f"{item['id']} · {item['source_kind']} {item['source_ref']}\n"
                f"User: {item['prompt'][:300]}\n"
                f"Assistant: {item['response'][:500]}"
                for item in examples
            )
            or "No pending examples."
        )

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        example_id = self.query_one("#example-id", Input).value.strip()
        try:
            if event.button.id == "learning-refresh":
                await self.refresh()
                return
            if event.button.id == "learning-import":
                result = await request_json(
                    "POST",
                    "/api/runtime/learning/import/huggingface",
                    payload={"split": "train", "max_samples": 100},
                )
                self.notify(
                    f"Imported {result['imported']} records; {result['skipped']} skipped. "
                    "All need review."
                )
            elif event.button.id == "learning-build":
                result = await request_json("POST", "/api/runtime/learning/datasets")
                self.query_one("#training-dataset", Input).value = result["id"]
                self.notify(f"Built dataset v{result['version']} with {result['sample_count']} examples.")
            elif event.button.id in {"example-approve", "example-reject"}:
                approved = event.button.id == "example-approve"
                await request_json(
                    "PATCH",
                    f"/api/runtime/learning/examples/{example_id}",
                    payload={"approved": approved},
                )
                self.notify("Example reviewed.")
            elif event.button.id == "example-delete":
                await request_json(
                    "DELETE", f"/api/runtime/learning/examples/{example_id}"
                )
                self.notify("Example removed.")
            elif event.button.id == "training-start":
                dataset_id = self.query_one("#training-dataset", Input).value.strip()
                base_model = self.query_one("#training-base", Input).value.strip()
                result = await request_json(
                    "POST",
                    "/api/runtime/learning/training",
                    payload={"dataset_id": dataset_id, "base_model": base_model},
                )
                self.notify(f"Training job {result['job_id'][:8]} queued.")
            else:
                return
        except RuntimeAPIError as error:
            self.notify(str(error), severity="error", timeout=10)
            return
        await self.refresh()
