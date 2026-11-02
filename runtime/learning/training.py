from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import inspect
import logging
from pathlib import Path
from collections.abc import Callable
from typing import Any

from .store import LearningStore


logger = logging.getLogger(__name__)


class TrainingCancelled(RuntimeError):
    pass


class TrainingJobManager:
    """Runs explicitly queued Unsloth jobs off the runtime's event loop."""

    def __init__(
        self,
        store: LearningStore,
        *,
        output_directory: str | Path,
        minimum_examples: int = 20,
        max_sequence_length: int = 2048,
        dataset_builder: Callable[[], dict[str, Any]] | None = None,
        automatic_training: bool = False,
        training_interval_hours: int = 168,
        training_base_model: str = "",
    ) -> None:
        self.store = store
        self.output_directory = Path(output_directory).expanduser().resolve()
        self.minimum_examples = minimum_examples
        self.max_sequence_length = max_sequence_length
        self.dataset_builder = dataset_builder
        self.automatic_training = automatic_training
        self.training_interval_hours = training_interval_hours
        self.training_base_model = training_base_model
        self._closed = False
        self._worker: asyncio.Task[None] | None = None

    def queue(
        self, dataset_id: str, base_model: str, config: dict[str, Any] | None = None
    ) -> str:
        dataset = self.store.get_dataset(dataset_id)
        if dataset is None or dataset["status"] != "active":
            raise ValueError("An active, validated dataset version is required.")
        if dataset["sample_count"] < self.minimum_examples:
            raise ValueError(
                f"Training requires at least {self.minimum_examples} approved examples."
            )
        if not base_model.strip() or len(base_model) > 512:
            raise ValueError("Provide a local model path or Hugging Face model ID.")
        options = {
            "max_sequence_length": self.max_sequence_length,
            "epochs": 1,
            "batch_size": 1,
            "gradient_accumulation_steps": 8,
            "learning_rate": 0.0002,
            "export_gguf": False,
        }
        options.update(config or {})
        self._validate_config(options)
        return self.store.create_training_job(dataset_id, base_model.strip(), options)

    @staticmethod
    def _validate_config(config: dict[str, Any]) -> None:
        if not 128 <= int(config["max_sequence_length"]) <= 32768:
            raise ValueError("max_sequence_length must be between 128 and 32768.")
        if not 1 <= int(config["epochs"]) <= 20:
            raise ValueError("epochs must be between 1 and 20.")
        if not 1 <= int(config["batch_size"]) <= 16:
            raise ValueError("batch_size must be between 1 and 16.")
        if not 1 <= int(config["gradient_accumulation_steps"]) <= 128:
            raise ValueError("gradient_accumulation_steps must be between 1 and 128.")
        learning_rate = float(config["learning_rate"])
        if not 1e-6 <= learning_rate <= 1e-2:
            raise ValueError("learning_rate must be between 1e-6 and 1e-2.")
        if not isinstance(config["export_gguf"], bool):
            raise ValueError("export_gguf must be a boolean.")

    def start_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._closed = False
            self._worker = asyncio.create_task(self._run_worker(), name="ardvark-training")

    async def close(self) -> None:
        self._closed = True
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    async def _run_worker(self) -> None:
        while not self._closed:
            try:
                if (
                    self.automatic_training
                    and self.training_base_model
                    and self.dataset_builder is not None
                    and await asyncio.to_thread(
                        self.store.claim_training_schedule,
                        self.training_interval_hours,
                        self.minimum_examples,
                    )
                ):
                    dataset = await asyncio.to_thread(self.dataset_builder)
                    await asyncio.to_thread(
                        self.queue, dataset["id"], self.training_base_model
                    )
                job = await asyncio.to_thread(self.store.claim_training_job)
                if job is None:
                    await asyncio.sleep(0.5)
                    continue
                await asyncio.to_thread(self._execute_job, job)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error("Training worker failed (%s).", type(error).__name__)
                await asyncio.sleep(1)

    def _execute_job(self, job: dict[str, Any]) -> None:
        job_id = job["id"]
        dataset_path = Path(job["dataset_path"]).resolve(strict=True)
        allowed_root = (self.store.database_path.parent / "learning" / "datasets").resolve()
        if allowed_root not in dataset_path.parents or not dataset_path.is_file():
            self.store.finish_training_job(
                job_id, status="failed", error="Training dataset is outside the managed dataset directory."
            )
            return
        output = self.output_directory / job_id
        cancelled = lambda: self._job_cancelled(job_id)
        try:
            result = run_unsloth_finetuning(
                dataset_path,
                job["base_model"],
                output,
                job["config"],
                cancelled=cancelled,
            )
        except TrainingCancelled:
            self.store.finish_training_job(job_id, status="cancelled")
            return
        except Exception as error:
            self.store.finish_training_job(
                job_id, status="failed", error=type(error).__name__
            )
            logger.error("Training job %s failed (%s).", job_id, type(error).__name__)
            return
        if self._job_cancelled(job_id):
            self.store.finish_training_job(job_id, status="cancelled")
            return

        model_id = self.store.add_model(
            base_model=job["base_model"],
            method="Unsloth LoRA/QLoRA",
            artifact_path=result["artifact_path"],
            dataset_id=job["dataset_id"],
            training_config=job["config"],
            evaluation_metrics=result["metrics"],
            export_format=result["export_format"],
            compatible=result["compatible"],
        )
        self.store.finish_training_job(
            job_id,
            status="completed",
            metrics=result["metrics"],
            model_id=model_id,
        )

    def _job_cancelled(self, job_id: str) -> bool:
        return self.store.training_job_status(job_id) != "running"


def run_unsloth_finetuning(
    dataset_path: Path,
    base_model: str,
    output_directory: Path,
    config: dict[str, Any],
    *,
    cancelled: Any,
) -> dict[str, Any]:
    """Train and evaluate a LoRA adapter using the optional GPU training stack."""
    try:
        import torch
        from datasets import load_dataset
        from transformers import TrainerCallback
        from unsloth import FastLanguageModel
        from trl import SFTConfig, SFTTrainer
    except ImportError as error:
        raise RuntimeError(
            "Fine-tuning needs the optional training dependencies. Install "
            "`runtime/requirements-training.txt` in a compatible CUDA environment."
        ) from error

    if not torch.cuda.is_available():
        raise RuntimeError(
            "Unsloth fine-tuning requires a CUDA-enabled PyTorch environment."
        )

    dataset = load_dataset("json", data_files=str(dataset_path), split="train")
    if len(dataset) < 2:
        raise ValueError("The training dataset needs at least two examples.")
    split = dataset.train_test_split(test_size=max(1, round(len(dataset) * 0.1)), seed=42)
    max_length = int(config["max_sequence_length"])
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=max_length,
        load_in_4bit=True,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    def format_batch(batch: dict[str, list[Any]]) -> dict[str, list[str]]:
        texts: list[str] = []
        for messages, tools in zip(batch["messages"], batch["tools"], strict=True):
            options: dict[str, Any] = {
                "tokenize": False,
                "add_generation_prompt": False,
            }
            if tools:
                options["tools"] = tools
            try:
                texts.append(tokenizer.apply_chat_template(messages, **options))
            except (TypeError, ValueError) as error:
                raise RuntimeError(
                    "The selected base model's chat template cannot format this dataset."
                ) from error
        return {"text": texts}

    train_dataset = split["train"].map(
        format_batch, batched=True, remove_columns=split["train"].column_names
    )
    eval_dataset = split["test"].map(
        format_batch, batched=True, remove_columns=split["test"].column_names
    )
    output_directory.mkdir(parents=True, exist_ok=True)

    config_parameters = inspect.signature(SFTConfig).parameters
    arguments: dict[str, Any] = {
        "output_dir": str(output_directory / "trainer-state"),
        "num_train_epochs": int(config["epochs"]),
        "per_device_train_batch_size": int(config["batch_size"]),
        "gradient_accumulation_steps": int(config["gradient_accumulation_steps"]),
        "learning_rate": float(config["learning_rate"]),
        "logging_steps": 10,
        "save_strategy": "no",
        "report_to": "none",
        "packing": False,
    }
    if "eval_strategy" in config_parameters:
        arguments["eval_strategy"] = "epoch"
    else:
        arguments["evaluation_strategy"] = "epoch"
    if "max_seq_length" in config_parameters:
        arguments["max_seq_length"] = max_length
    else:
        arguments["max_length"] = max_length
    if "dataset_text_field" in config_parameters:
        arguments["dataset_text_field"] = "text"
    else:
        arguments["dataset_text_field"] = "text"
    training_args = SFTConfig(**arguments)

    class CancellationCallback(TrainerCallback):
        def on_step_begin(self, args: Any, state: Any, control: Any, **kwargs: Any) -> Any:
            if cancelled():
                raise TrainingCancelled("Training job was cancelled.")
            return control

    trainer_parameters = inspect.signature(SFTTrainer).parameters
    trainer_options: dict[str, Any] = {
        "model": model,
        "train_dataset": train_dataset,
        "eval_dataset": eval_dataset,
        "args": training_args,
        "callbacks": [CancellationCallback()],
    }
    if "processing_class" in trainer_parameters:
        trainer_options["processing_class"] = tokenizer
    else:
        trainer_options["tokenizer"] = tokenizer
    if "dataset_text_field" in trainer_parameters:
        trainer_options["dataset_text_field"] = "text"
    if "max_seq_length" in trainer_parameters:
        trainer_options["max_seq_length"] = max_length
    trainer = SFTTrainer(**trainer_options)
    baseline = trainer.evaluate()
    trainer.train()
    evaluated = trainer.evaluate()
    baseline_loss = float(baseline["eval_loss"])
    candidate_loss = float(evaluated["eval_loss"])
    passed = candidate_loss <= baseline_loss
    metrics = {
        "baseline_eval_loss": baseline_loss,
        "candidate_eval_loss": candidate_loss,
        "passed": passed,
        "evaluation": "same held-out split before and after fine-tuning",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
    adapter_directory = output_directory / "adapter"
    trainer.save_model(str(adapter_directory))
    tokenizer.save_pretrained(adapter_directory)
    artifact_path = adapter_directory
    export_format = "peft_adapter"
    compatible = False
    if config["export_gguf"]:
        gguf_directory = output_directory / "gguf"
        model.save_pretrained_gguf(
            str(gguf_directory),
            tokenizer,
            quantization_method="q4_k_m",
        )
        gguf_files = list(gguf_directory.rglob("*.gguf"))
        if len(gguf_files) != 1:
            raise RuntimeError("GGUF export did not produce exactly one model file.")
        artifact_path = gguf_files[0]
        export_format = "gguf:q4_k_m"
        compatible = True
    return {
        "artifact_path": str(artifact_path),
        "export_format": export_format,
        "compatible": compatible,
        "metrics": metrics,
    }
