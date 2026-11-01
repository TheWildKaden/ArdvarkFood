import asyncio
import logging
import queue
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from ...config.settings import ModelSettings
from ..inference import (
    GenerationDelta,
    GenerationResponse,
    ModelMetadata,
    SamplingConfig,
)


logger = logging.getLogger(__name__)
_END = object()


class LlamaCppAdapter:
    def __init__(self, settings: ModelSettings) -> None:
        self.settings = settings
        self._model: Any = None
        self._inference_lock = threading.Lock()
        self.metadata = ModelMetadata(
            name=settings.model_name,
            backend="llama_cpp",
            context_size=settings.context_size,
            capabilities={
                "tools": True,
                "streaming": True,
                "vision": bool(settings.clip_model_path),
                "audio": False,
                "video": False,
            },
            tokenizer="model",
        )

    async def load(self) -> None:
        model_path = Path(self.settings.model_path).expanduser()
        if not model_path.is_file():
            raise FileNotFoundError(
                "Set AI_RUNTIME_MODEL_PATH to an existing local GGUF model file."
            )
        try:
            from llama_cpp import Llama
        except ImportError as error:
            raise RuntimeError(
                "The llama.cpp backend is not installed. Install "
                "`AI-Runtime/requirements.txt` or `llama-cpp-python`."
            ) from error

        kwargs: dict[str, Any] = {
            "model_path": str(model_path.resolve()),
            "n_ctx": self.settings.context_size,
            "n_gpu_layers": self.settings.gpu_layers,
            "verbose": False,
        }
        if self.settings.chat_format:
            kwargs["chat_format"] = self.settings.chat_format
        if self.settings.clip_model_path:
            clip_path = Path(self.settings.clip_model_path).expanduser()
            if not clip_path.is_file():
                raise FileNotFoundError(
                    "The configured multimodal clip model file does not exist."
                )
            kwargs["clip_model_path"] = str(clip_path.resolve())

        self._model = await asyncio.to_thread(Llama, **kwargs)

    async def unload(self) -> None:
        model, self._model = self._model, None
        if model is not None:
            close = getattr(model, "close", None)
            if close is not None:
                await asyncio.to_thread(close)

    def tokenize(self, text: str) -> list[int]:
        model = self._require_model()
        return model.tokenize(text.encode("utf-8"), add_bos=False, special=False)

    async def generate(
        self,
        messages: list[dict[str, Any]],
        sampling: SamplingConfig,
        tools: list[dict[str, Any]],
    ) -> GenerationResponse:
        model = self._require_model()
        params = self._sampling_params(sampling)
        params.update({"messages": messages, "tools": tools or None, "stream": False})
        response = await asyncio.to_thread(self._chat_locked, model, params)
        choice = response["choices"][0]
        message = choice["message"]
        return GenerationResponse(
            content=message.get("content") or "",
            tool_calls=message.get("tool_calls") or [],
            finish_reason=choice.get("finish_reason"),
            usage=response.get("usage") or {},
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
        sampling: SamplingConfig,
        tools: list[dict[str, Any]],
    ) -> AsyncIterator[GenerationDelta]:
        model = self._require_model()
        params = self._sampling_params(sampling)
        params.update({"messages": messages, "tools": tools or None, "stream": True})
        output: queue.Queue[Any] = queue.Queue()
        stop = threading.Event()
        loop = asyncio.get_running_loop()

        def produce() -> None:
            try:
                with self._inference_lock:
                    chunks = model.create_chat_completion(**params)
                    for chunk in chunks:
                        if stop.is_set():
                            close = getattr(chunks, "close", None)
                            if close is not None:
                                close()
                            break
                        loop.call_soon_threadsafe(output.put_nowait, chunk)
            except Exception as error:
                loop.call_soon_threadsafe(output.put_nowait, error)
            finally:
                loop.call_soon_threadsafe(output.put_nowait, _END)

        worker = asyncio.create_task(asyncio.to_thread(produce))
        try:
            while True:
                item = await asyncio.to_thread(output.get)
                if item is _END:
                    break
                if isinstance(item, Exception):
                    raise RuntimeError(f"llama.cpp inference failed: {item}") from item
                choice = item["choices"][0]
                delta = choice.get("delta") or {}
                yield GenerationDelta(
                    content=delta.get("content") or "",
                    tool_calls=delta.get("tool_calls") or [],
                    finish_reason=choice.get("finish_reason"),
                )
            await worker
        finally:
            stop.set()

    def _chat_locked(self, model: Any, params: dict[str, Any]) -> dict[str, Any]:
        with self._inference_lock:
            return model.create_chat_completion(**params)

    def _require_model(self) -> Any:
        if self._model is None:
            raise RuntimeError("The llama.cpp model has not been loaded.")
        return self._model

    @staticmethod
    def _sampling_params(sampling: SamplingConfig) -> dict[str, Any]:
        params: dict[str, Any] = {
            "temperature": sampling.temperature,
            "top_p": sampling.top_p,
            "top_k": sampling.top_k,
            "repeat_penalty": sampling.repetition_penalty,
            "max_tokens": sampling.max_tokens,
        }
        if sampling.stop:
            params["stop"] = sampling.stop
        return params
