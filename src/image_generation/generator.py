import logging
from io import BytesIO
from threading import Lock
from typing import Protocol


logger = logging.getLogger(__name__)
MODEL_ID = "stabilityai/sd-turbo"


class ImageGenerator(Protocol):
    @property
    def status(self) -> str: ...

    @property
    def device(self) -> str: ...

    def generate(self, prompt: str, steps: int, seed: int | None) -> bytes: ...


class ImageModelUnavailable(RuntimeError):
    pass


class ImageGenerationError(RuntimeError):
    pass


class LocalImageGenerator:
    def __init__(self) -> None:
        self._pipeline = None
        self._device = "cpu"
        self._status = "not_loaded"
        self._lock = Lock()

    @property
    def status(self) -> str:
        return self._status

    @property
    def device(self) -> str:
        return self._device if self._status == "ready" else "automatic"

    def generate(self, prompt: str, steps: int, seed: int | None) -> bytes:
        with self._lock:
            pipeline = self._load_pipeline()
            try:
                import torch

                generator = None
                if seed is not None:
                    generator = torch.Generator(device=self._device).manual_seed(seed)
                with torch.inference_mode():
                    image = pipeline(
                        prompt=prompt,
                        num_inference_steps=steps,
                        guidance_scale=0.0,
                        width=512,
                        height=512,
                        generator=generator,
                    ).images[0]

                output = BytesIO()
                image.save(output, format="PNG")
                return output.getvalue()
            except Exception as error:
                self._status = "error"
                logger.exception("Local image generation failed.")
                raise ImageGenerationError(
                    "The local image model could not generate this image. "
                    "Check Codespace memory and model compatibility, then try again."
                ) from error

    def _load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline

        self._status = "loading"
        try:
            import torch
            from diffusers import AutoPipelineForText2Image

            if torch.cuda.is_available():
                self._device = "cuda"
                pipeline = AutoPipelineForText2Image.from_pretrained(
                    MODEL_ID,
                    torch_dtype=torch.float16,
                    variant="fp16",
                    use_safetensors=True,
                )
            else:
                self._device = "cpu"
                pipeline = AutoPipelineForText2Image.from_pretrained(
                    MODEL_ID,
                    torch_dtype=torch.float32,
                    use_safetensors=True,
                )
                pipeline.enable_attention_slicing("max")
            pipeline.to(self._device)
        except (ImportError, ModuleNotFoundError) as error:
            self._status = "error"
            raise ImageModelUnavailable(
                "The local image model dependencies are missing. Run "
                "`pip install -r requirements-image-generator.txt` and restart."
            ) from error
        except Exception as error:
            self._status = "error"
            logger.exception("Could not load the local image model.")
            raise ImageModelUnavailable(
                "Could not load SD-Turbo. Check the Codespace internet connection, "
                "available memory, and the model cache, then try again."
            ) from error

        self._pipeline = pipeline
        self._status = "ready"
        logger.info("Loaded local image model %s on %s.", MODEL_ID, self._device)
        return pipeline
