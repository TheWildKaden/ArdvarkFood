import asyncio
import logging
from typing import Any

from ..config.settings import ModelSettings
from .inference import ModelAdapter, ModelNotLoaded


logger = logging.getLogger(__name__)


class ModelManager:
    """Owns the loaded adapter and serializes model replacement and unloading."""

    def __init__(
        self,
        settings: ModelSettings,
        adapter_factories: dict[str, Any] | None = None,
    ) -> None:
        self.settings = settings
        self._adapter_factories = adapter_factories or {}
        self._adapter: ModelAdapter | None = None
        self._load_lock = asyncio.Lock()
        self._status = "unloaded"
        self._last_error: str | None = None

    @property
    def status(self) -> dict[str, Any]:
        metadata = self._adapter.metadata if self._adapter is not None else None
        return {
            "status": self._status,
            "backend": self.settings.backend,
            "model": metadata.name if metadata else self.settings.model_name,
            "context_size": metadata.context_size if metadata else self.settings.context_size,
            "capabilities": metadata.capabilities if metadata else {},
            "tokenizer": metadata.tokenizer if metadata else None,
            "error": self._last_error,
        }

    def get_adapter(self) -> ModelAdapter:
        if self._adapter is None or self._status != "loaded":
            raise ModelNotLoaded(
                "No language model is loaded. Configure a model path and load a model "
                "through POST /models/load."
            )
        return self._adapter

    async def load(self, settings: ModelSettings | None = None) -> dict[str, Any]:
        async with self._load_lock:
            target = settings or self.settings
            current = self._adapter
            if (
                current is not None
                and self._status == "loaded"
                and target == self.settings
            ):
                return self.status

            self._status = "loading"
            self._last_error = None
            if current is not None:
                await current.unload()
                self._adapter = None

            try:
                adapter = self._make_adapter(target)
                await adapter.load()
            except Exception as error:
                self._status = "error"
                self._last_error = str(error)
                logger.exception("Language model failed to load.")
                raise

            self.settings = target
            self._adapter = adapter
            self._status = "loaded"
            logger.info("Loaded model %s using %s.", adapter.metadata.name, target.backend)
            return self.status

    async def unload(self) -> dict[str, Any]:
        async with self._load_lock:
            self._status = "unloading"
            adapter = self._adapter
            self._adapter = None
            try:
                if adapter is not None:
                    await adapter.unload()
            except Exception as error:
                self._status = "error"
                self._last_error = str(error)
                logger.exception("Language model failed to unload.")
                raise
            self._status = "unloaded"
            self._last_error = None
            return self.status

    def _make_adapter(self, settings: ModelSettings) -> ModelAdapter:
        factory = self._adapter_factories.get(settings.backend)
        if factory is None:
            if settings.backend == "llama_cpp":
                from .adapters.llama_cpp import LlamaCppAdapter

                factory = LlamaCppAdapter
            elif settings.backend == "openai_compatible":
                from .adapters.openai_compatible import OpenAICompatibleAdapter

                factory = OpenAICompatibleAdapter
            else:
                raise ValueError(f"Unsupported model backend: {settings.backend}")
        return factory(settings)