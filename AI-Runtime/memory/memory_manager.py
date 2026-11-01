from typing import Any

from ..storage.storage_manager import StorageManager
from .retrieval.retriever import MemoryRetriever


class MemoryManager:
    def __init__(self, storage: StorageManager) -> None:
        self.storage = storage
        self.retriever = MemoryRetriever(storage)

    def retrieve(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.retriever.retrieve(query, limit)

    def remember(
        self, content: str, conversation_id: str | None = None, metadata: Any = None
    ) -> str:
        cleaned = content.strip()
        if not cleaned:
            raise ValueError("Memory content cannot be empty.")
        return self.storage.add_memory(cleaned, conversation_id, metadata)