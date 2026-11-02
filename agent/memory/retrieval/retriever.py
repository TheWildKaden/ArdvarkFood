from typing import Any

from runtime.storage.storage_manager import StorageManager


class MemoryRetriever:
    def __init__(self, storage: StorageManager) -> None:
        self.storage = storage

    def retrieve(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        return self.storage.search_memories(query, limit)