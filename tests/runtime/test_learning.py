import asyncio
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest

from runtime.learning.manager import ConversationLearningManager, HF_DATASET_ID
from runtime.learning.store import LearningStore
from runtime.learning.training import TrainingJobManager
from runtime.storage.storage_manager import StorageManager


def _managers(
    tmp_path: Path, *, minimum_examples: int = 2
) -> tuple[StorageManager, LearningStore, ConversationLearningManager]:
    storage = StorageManager(str(tmp_path / "runtime.sqlite3"))
    store = LearningStore(storage.database_path)
    learning = ConversationLearningManager(
        storage,
        store,
        minimum_training_examples=minimum_examples,
        maximum_dataset_examples=100,
    )
    return storage, store, learning


def test_opt_in_memory_learning_filters_secrets_and_supports_commands(
    tmp_path: Path,
) -> None:
    storage, store, learning = _managers(tmp_path)
    conversation_id = storage.create_conversation()["id"]
    storage.add_message(conversation_id, "user", "I prefer Python for small scripts.")
    storage.add_message(conversation_id, "assistant", "Understood.")
    storage.add_message(
        conversation_id,
        "user",
        "I prefer to use token=super-secret-token for this test.",
    )

    learning.process_conversation(conversation_id, "memory")
    assert storage.search_memories("Python")
    assert not storage.search_memories("super-secret-token")
    assert not store.conversation_learning_enabled(conversation_id)

    answer = learning.handle_command(
        conversation_id, "Remember this: My editor is VS Code."
    )
    assert answer and "remember" in answer.casefold()
    assert storage.search_memories("VS Code")
    assert learning.handle_command(
        conversation_id, "Remember this: email me at user@example.com"
    ).startswith("I didn’t save")
    assert learning.handle_command(
        conversation_id, "Forget this: My editor is VS Code."
    ) == "I forgot that memory."
    assert not storage.search_memories("VS Code")


def test_training_examples_need_review_and_compiled_dataset_traces_sources(
    tmp_path: Path,
) -> None:
    storage, store, learning = _managers(tmp_path)
    conversation_id = storage.create_conversation()["id"]
    store.set_conversation_learning(conversation_id, True)
    for index in range(2):
        storage.add_message(
            conversation_id,
            "user",
            f"Explain a clear engineering concept number {index}.",
        )
        storage.add_message(
            conversation_id,
            "assistant",
            f"This is an accurate explanation for example number {index}.",
        )
    learning.process_conversation(conversation_id, "training_examples")
    candidates = store.list_examples("pending_review")
    assert len(candidates) == 2
    with pytest.raises(ValueError, match="approved"):
        learning.build_dataset()

    for example in candidates:
        assert store.review_example(example["id"], approved=True)
    dataset = learning.build_dataset()
    records = [
        json.loads(line)
        for line in Path(dataset["artifact_path"]).read_text(encoding="utf-8").splitlines()
    ]

    assert dataset["sample_count"] == 2
    assert {item["id"] for item in records} == {item["id"] for item in candidates}
    assert all(item["source"]["conversation_id"] == conversation_id for item in records)
    job_manager = TrainingJobManager(
        store,
        output_directory=tmp_path / "models",
        minimum_examples=2,
    )
    job_id = job_manager.queue(dataset["id"], "org/example-model")
    assert store.list_training_jobs()[0]["id"] == job_id
    assert store.list_training_jobs()[0]["status"] == "queued"


def test_huggingface_import_is_bounded_normalized_and_review_gated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = [
        {
            "messages": [
                {"role": "system", "content": "Answer carefully."},
                {"role": "user", "content": "How do I parse a JSON file?"},
                {"role": "assistant", "content": "Use the standard json module."},
            ],
            "tools": [],
        },
        {
            "messages": [
                {"role": "user", "content": "My password=example-secret is here."},
                {"role": "assistant", "content": "I will not repeat it."},
            ],
            "tools": [],
        },
        {"messages": "invalid"},
    ]
    calls = []
    module = ModuleType("datasets")

    def load_dataset(dataset_id, *, split, streaming):
        calls.append((dataset_id, split, streaming))
        return iter(rows)

    module.load_dataset = load_dataset
    monkeypatch.setitem(sys.modules, "datasets", module)
    _, store, learning = _managers(tmp_path)

    result = asyncio.run(
        learning.import_huggingface_dataset(split="train", max_samples=3)
    )

    assert calls == [(HF_DATASET_ID, "train", True)]
    assert result["processed"] == 3
    assert result["imported"] == 1
    assert result["skipped"] == 2
    imported = store.list_examples("pending_review")
    assert imported[0]["source_kind"] == "huggingface"
    assert imported[0]["source_ref"].startswith(f"hf://{HF_DATASET_ID}/train/")
    assert imported[0]["messages"][0]["role"] == "system"
    assert store.list_examples("approved") == []


def test_external_dataset_normalizer_preserves_tool_calls() -> None:
    messages, tools = ConversationLearningManager._normalize_huggingface_row(
        {
            "messages": [
                {"role": "user", "content": "Read the requested file."},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "filesystem.read", "arguments": "{}"},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "call-1", "content": "file text"},
                {"role": "assistant", "content": "Here is the result."},
            ],
            "tools": [{"type": "function", "function": {"name": "filesystem.read"}}],
        }
    )

    assert messages[1]["tool_calls"][0]["function"]["name"] == "filesystem.read"
    assert tools[0]["function"]["name"] == "filesystem.read"


def test_learning_queue_recovers_running_jobs_and_model_activation_is_gated(
    tmp_path: Path,
) -> None:
    storage, store, _ = _managers(tmp_path, minimum_examples=1)
    conversation_id = storage.create_conversation()["id"]
    store.set_conversation_learning(conversation_id, True)
    queue_id = store.enqueue(conversation_id, "memory")
    with store._connect() as db:
        db.execute("UPDATE learning_queue SET status='running' WHERE id=?", (queue_id,))
    recovered = LearningStore(storage.database_path)
    assert recovered.queued()[0]["id"] == queue_id

    candidate_file = tmp_path / "candidate.gguf"
    candidate_file.write_bytes(b"model")
    dataset = recovered.create_dataset(
        str(tmp_path / "dataset.jsonl"),
        "sha256",
        1,
        {"example_ids": []},
    )
    rejected_model = recovered.add_model(
        base_model="base",
        method="test",
        artifact_path=str(candidate_file),
        dataset_id=dataset["id"],
        training_config={},
        evaluation_metrics={"passed": False, "eval_loss": 2.0},
        export_format="gguf:q4_k_m",
        compatible=True,
    )
    assert not recovered.activate_model(rejected_model)

    first_model = recovered.add_model(
        base_model="base",
        method="test",
        artifact_path=str(candidate_file),
        dataset_id=dataset["id"],
        training_config={},
        evaluation_metrics={"passed": True, "eval_loss": 1.0},
        export_format="gguf:q4_k_m",
        compatible=True,
    )
    second_model = recovered.add_model(
        base_model="base",
        method="test",
        artifact_path=str(candidate_file),
        dataset_id=dataset["id"],
        training_config={},
        evaluation_metrics={"passed": True, "eval_loss": 0.9},
        export_format="gguf:q4_k_m",
        compatible=True,
    )
    assert recovered.activate_model(first_model)
    assert recovered.activate_model(second_model)
    assert recovered.rollback_model_id() == first_model
