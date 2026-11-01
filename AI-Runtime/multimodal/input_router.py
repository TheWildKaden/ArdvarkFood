import base64
import mimetypes
from typing import Any


class UnsupportedModality(ValueError):
    pass


class InputRouter:
    """Validates multimodal attachments and normalizes supported text/image inputs."""

    supported = {"text/plain", "image/png", "image/jpeg", "image/webp"}

    def process(self, attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for item in attachments:
            name = item.get("name")
            mime_type = item.get("mime_type")
            content = item.get("content")
            if (
                not isinstance(name, str)
                or not isinstance(mime_type, str)
                or not isinstance(content, str)
            ):
                raise ValueError("Each attachment requires name, mime_type, and content.")
            if len(content) > 8_000_000:
                raise ValueError("Attachment exceeds the 6 MB encoded-size limit.")
            if mime_type not in self.supported:
                guessed, _ = mimetypes.guess_type(name)
                mime_type = guessed or mime_type
            if mime_type == "text/plain":
                normalized.append(
                    {"name": name[:256], "mime_type": mime_type, "text": content[:100_000]}
                )
            elif mime_type.startswith("image/"):
                try:
                    image_bytes = base64.b64decode(content, validate=True)
                except ValueError as error:
                    raise ValueError(f"Image attachment {name!r} is not valid base64.") from error
                if len(image_bytes) > 6_000_000:
                    raise ValueError("Decoded image exceeds the 6 MB limit.")
                normalized.append(
                    {
                        "name": name[:256],
                        "mime_type": mime_type,
                        "data": base64.b64encode(image_bytes).decode("ascii"),
                    }
                )
            else:
                raise UnsupportedModality(f"Unsupported attachment type: {mime_type}")
        return normalized