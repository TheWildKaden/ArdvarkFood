from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import re
from typing import Any

from runtime.compiler import ArtifactCompiler
from runtime.storage.storage_manager import StorageManager

from .privacy import contains_sensitive_data, redact_sensitive_data
from .store import LearningStore


logger = logging.getLogger(__name__)
HF_DATASET_ID = "MoreThought/Fable-5.1-Max-Reasoning-Filtered-10000x"
_PREFERENCE = re.compile(
    r"(?i)\b(?:i prefer|i usually use|i always use|my preferred (?:language|tool|editor|framework) is)\b"
)
_COMMANDS = (
    "show what you remember",
    "don't learn from this conversation",
    "do not learn from this conversation",
)


class ConversationLearningManager:
    """Runs opt-in memory extraction and keeps training examples review-gated."""

    def __init__(
        self,
        storage: StorageManager,
        store: LearningStore,
        *,
        minimum_training_examples: int = 20,
        maximum_dataset_examples: int = 1000,
        enabled: bool = True,
    ) -> None:
        self.storage = storage
        self.store = store
        self.minimum_training_examples = minimum_training_examples
        self.maximum_dataset_examples = maximum_dataset_examples
        self.enabled = enabled
        self._worker: asyncio.Task[None] | None = None
        self._closed = False

    def start_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._closed = False
            self._worker = asyncio.create_task(self._run_worker(), name="ardvark-learning")

    async def close(self) -> None:
        self._closed = True
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    def set_conversation_learning(self, conversation_id: str, enabled: bool) -> None:
        if enabled and not self.enabled:
            raise PermissionError("Conversation learning is disabled in runtime settings.")
        withdrawn_paths = self.store.set_conversation_learning(conversation_id, enabled)
        if not enabled:
            self.storage.delete_memories_for_conversation(conversation_id)
            self._remove_dataset_artifacts(withdrawn_paths)
        if enabled:
            self.store.enqueue(conversation_id, "memory")

    def queue_training_examples(self, conversation_id: str) -> str:
        return self.store.enqueue(conversation_id, "training_examples")

    def delete_training_example(self, example_id: str) -> bool:
        paths = self.store.delete_example(example_id)
        if paths is None:
            return False
        self._remove_dataset_artifacts(paths)
        return True

    def _remove_dataset_artifacts(self, values: list[str]) -> None:
        root = (self.store.database_path.parent / "learning" / "datasets").resolve()
        for value in values:
            artifact = Path(value).resolve()
            if root not in artifact.parents:
                logger.error("Skipped cleanup of a dataset outside the managed directory.")
                continue
            paths = (
                artifact,
                Path(str(artifact) + ".manifest.json"),
                artifact.with_name(artifact.stem + ".source.jsonl"),
                Path(str(artifact) + ".previous"),
            )
            for path in paths:
                if path.exists() and root in path.resolve().parents:
                    path.unlink()

    def queue_memory(self, conversation_id: str) -> None:
        if self.enabled and self.store.conversation_learning_enabled(conversation_id):
            self.store.enqueue(conversation_id, "memory")

    def handle_command(self, conversation_id: str, content: str) -> str | None:
        text = content.strip()
        lowered = text.casefold()
        if lowered.startswith("remember this:") or lowered.startswith("remember:"):
            memory = text.split(":", 1)[1].strip()
            if not memory:
                return "Tell me what to remember after “Remember this:”."
            if contains_sensitive_data(memory):
                return "I didn’t save that because it appears to contain private or sensitive information."
            memory_id = self.storage.add_memory(
                memory,
                conversation_id,
                {
                    "source": "explicit_user_request",
                    "scope": "user",
                    "importance": 0.8,
                    "confidence": 1.0,
                },
            )
            return f"I’ll remember that. (Memory {memory_id[:8]})"

        if lowered.startswith("forget this:"):
            memory = text.split(":", 1)[1].strip()
            removed = self.storage.delete_memory_by_content(memory)
            return (
                "I forgot that memory."
                if removed
                else "I couldn’t find an exact matching memory to remove."
            )

        if lowered.startswith("correct that memory:"):
            correction = text.split(":", 1)[1]
            old, separator, new = correction.partition("=>")
            old, new = old.strip(), new.strip()
            if not separator or not old or not new:
                return "Use “Correct that memory: old fact => corrected fact”."
            if contains_sensitive_data(new):
                return "I didn’t save that correction because it appears to contain private or sensitive information."
            old_memories = self.storage.search_memories(old, limit=20)
            target = next(
                (
                    item
                    for item in old_memories
                    if " ".join(item["content"].casefold().split())
                    == " ".join(old.casefold().split())
                ),
                None,
            )
            if target is None:
                return "I couldn’t find that exact memory to correct."
            replacement_id = self.storage.add_memory(
                new,
                conversation_id,
                {
                    **target["metadata"],
                    "source": "user_correction",
                    "supersedes": target["id"],
                    "confidence": 1.0,
                },
            )
            self.storage.update_memory(
                target["id"],
                target["content"],
                {**target["metadata"], "superseded_by": replacement_id},
            )
            return "I updated that memory."

        if lowered in _COMMANDS:
            if lowered.startswith("show"):
                memories = self.storage.list_memories(20)
                if not memories:
                    return "I don’t have any saved memories yet."
                return "Here’s what I remember:\n" + "\n".join(
                    f"- {item['content']}" for item in memories
                )
            self.set_conversation_learning(conversation_id, False)
            return "Learning is disabled for this conversation, and its unapproved learning items were removed."

        if lowered == "add this conversation to training":
            if not self.enabled:
                return "Conversation learning is disabled in runtime settings."
            self.set_conversation_learning(conversation_id, True)
            self.queue_training_examples(conversation_id)
            self.start_worker()
            return (
                "I queued this conversation for training-example review. "
                "Nothing will be used for training until you approve the examples."
            )
        return None

    def process_conversation(self, conversation_id: str, kind: str) -> None:
        if not self.enabled or not self.store.conversation_learning_enabled(conversation_id):
            return
        messages = self.storage.get_messages(conversation_id, limit=500)
        if kind == "memory":
            self._extract_memories(conversation_id, messages)
        elif kind == "training_examples":
            self._extract_examples(conversation_id, messages)
        else:
            raise ValueError(f"Unknown learning task: {kind}")

    def _extract_memories(
        self, conversation_id: str, messages: list[dict[str, Any]]
    ) -> None:
        for message in messages:
            if message["role"] != "user" or not isinstance(message["content"], str):
                continue
            content = message["content"].strip()
            if len(content) > 4000 or contains_sensitive_data(content):
                continue
            if not _PREFERENCE.search(content):
                continue
            duplicate = any(
                " ".join(item["content"].casefold().split())
                == " ".join(content.casefold().split())
                for item in self.storage.search_memories(content, 20)
            )
            if duplicate:
                continue
            self.storage.add_memory(
                content,
                conversation_id,
                {
                    "source": "opt_in_conversation",
                    "scope": "user",
                    "importance": 0.7,
                    "confidence": 0.85,
                },
            )

    def _extract_examples(
        self, conversation_id: str, messages: list[dict[str, Any]]
    ) -> None:
        user_message: dict[str, Any] | None = None
        for message in messages:
            if message["role"] == "user":
                user_message = message
                continue
            if message["role"] != "assistant" or user_message is None:
                continue
            prompt = user_message["content"]
            response = message["content"]
            user_item = user_message
            user_message = None
            if not isinstance(prompt, str) or not isinstance(response, str):
                continue
            prompt = redact_sensitive_data(prompt)
            response = redact_sensitive_data(response)
            if len(prompt) < 8 or len(response) < 16 or len(prompt) + len(response) > 24000:
                continue
            if contains_sensitive_data(prompt) or contains_sensitive_data(response):
                continue
            if prompt.casefold().startswith(
                (
                    *_COMMANDS,
                    "remember this:",
                    "remember:",
                    "forget this:",
                    "correct that memory:",
                    "add this conversation to training",
                    "remove this example from training",
                )
            ):
                continue
            example_messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response},
            ]
            digest = hashlib.sha256(
                json.dumps(example_messages, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            self.store.add_example(
                conversation_id,
                [int(user_item["id"]), int(message["id"])],
                example_messages,
                [],
                prompt,
                response,
                digest,
                0.65,
            )

    async def import_huggingface_dataset(
        self,
        *,
        split: str = "train",
        max_samples: int = 100,
    ) -> dict[str, Any]:
        if split not in {"train", "full"}:
            raise ValueError("Dataset split must be 'train' or 'full'.")
        if not 1 <= max_samples <= self.maximum_dataset_examples:
            raise ValueError(
                f"max_samples must be between 1 and {self.maximum_dataset_examples}."
            )
        return await asyncio.to_thread(
            self._import_huggingface_dataset, split, max_samples
        )

    def _import_huggingface_dataset(
        self, split: str, max_samples: int
    ) -> dict[str, Any]:
        try:
            from datasets import load_dataset
        except ImportError as error:
            raise RuntimeError(
                "Hugging Face dataset support is optional. Install "
                "`runtime/requirements-training.txt` to enable it."
            ) from error

        dataset = load_dataset(HF_DATASET_ID, split=split, streaming=True)
        imported = skipped = processed = 0
        for index, row in enumerate(dataset):
            if processed >= max_samples:
                break
            processed += 1
            try:
                messages, tools = self._normalize_huggingface_row(row)
                canonical = json.dumps(
                    {"messages": messages, "tools": tools},
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                if len(canonical) > 512_000 or contains_sensitive_data(canonical):
                    skipped += 1
                    continue
                digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                if self.store.add_external_example(
                    messages=messages,
                    tools=tools,
                    source_ref=f"hf://{HF_DATASET_ID}/{split}/{index}",
                    content_hash=digest,
                    quality_score=0.75,
                ):
                    imported += 1
                else:
                    skipped += 1
            except (TypeError, ValueError, KeyError):
                skipped += 1
        return {
            "dataset": HF_DATASET_ID,
            "split": split,
            "processed": processed,
            "imported": imported,
            "skipped": skipped,
            "status": "pending_review",
            "notice": (
                "Imported records are review-only. This corpus is large (up to 10,000 "
                "traces and about 500 million tokens); this request was capped."
            ),
        }

    @staticmethod
    def _normalize_huggingface_row(
        row: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        raw_messages = row.get("messages")
        if not isinstance(raw_messages, list) or not 2 <= len(raw_messages) <= 100:
            raise ValueError("The row must contain 2-100 chat messages.")
        normalized = []
        seen_roles: set[str] = set()
        for item in raw_messages:
            if not isinstance(item, dict):
                raise ValueError("A chat message is not an object.")
            role = item.get("role")
            if role not in {"system", "user", "assistant", "tool"}:
                raise ValueError("The row uses an unsupported chat role.")
            content = item.get("content")
            if content is not None and not isinstance(content, str):
                raise ValueError("Only text chat content is supported.")
            if content is None and not item.get("tool_calls"):
                raise ValueError("Empty messages need a tool call.")
            message: dict[str, Any] = {"role": role}
            if content is not None:
                message["content"] = content
            for field in ("name", "tool_call_id", "tool_calls"):
                if field in item:
                    if field in {"name", "tool_call_id"} and not isinstance(item[field], str):
                        raise ValueError("Tool metadata must be text.")
                    if field == "tool_calls" and not isinstance(item[field], list):
                        raise ValueError("Tool calls must be a list.")
                    message[field] = item[field]
            normalized.append(message)
            seen_roles.add(role)
        if not {"user", "assistant"}.issubset(seen_roles):
            raise ValueError("The row must include user and assistant messages.")
        tools = row.get("tools", [])
        if not isinstance(tools, list) or len(tools) > 64 or not all(
            isinstance(tool, dict) for tool in tools
        ):
            raise ValueError("Tool schemas must be a list of at most 64 objects.")
        return normalized, tools

    def build_dataset(self) -> dict[str, Any]:
        if not self.enabled:
            raise ValueError("Learning is disabled in runtime settings.")
        examples = self.store.approved_examples()
        if len(examples) < self.minimum_training_examples:
            raise ValueError(
                "Not enough approved training examples: "
                f"{len(examples)} approved, {self.minimum_training_examples} required."
            )
        examples = examples[: self.maximum_dataset_examples]
        dataset_directory = self.store.database_path.parent / "learning" / "datasets"
        dataset_directory.mkdir(parents=True, exist_ok=True)
        dataset_tag = self.store.new_id()
        source = dataset_directory / f"dataset-{dataset_tag}.source.jsonl"
        compiled = dataset_directory / f"dataset-{dataset_tag}.jsonl"
        temporary = source.with_name(source.name + ".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as file:
            for example in examples:
                record = {
                    "id": example["id"],
                    "messages": example["messages"],
                    "tools": example["tools"],
                    "source": {
                        "kind": example["source_kind"],
                        "reference": example["source_ref"],
                        "conversation_id": example["conversation_id"],
                        "message_ids": example["message_ids"],
                    },
                }
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, source)
        compiler = ArtifactCompiler()
        build = compiler.compile(source, compiled, format="jsonl")
        metadata = {
            "example_ids": [example["id"] for example in examples],
            "source_path": source.name,
            "manifest_path": Path(build["manifest_path"]).name,
            "deduplicated": build["deduplicated"],
        }
        return self.store.create_dataset(
            str(compiled),
            build["output_sha256"],
            len(examples),
            metadata,
        )

    async def _run_worker(self) -> None:
        while not self._closed:
            try:
                processed = await asyncio.to_thread(self._process_one)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.error("Conversation learning worker failed (%s).", type(error).__name__)
                processed = False
            if not processed:
                await asyncio.sleep(0.5)

    def _process_one(self) -> bool:
        for job in self.store.queued():
            if not self.store.mark_queue_running(job["id"]):
                continue
            try:
                self.process_conversation(job["conversation_id"], job["kind"])
            except Exception as error:
                self.store.finish_queue(job["id"], type(error).__name__)
                logger.error("Learning task %s failed (%s).", job["id"], type(error).__name__)
            else:
                self.store.finish_queue(job["id"])
            return True
        return False
