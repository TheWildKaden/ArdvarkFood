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
        total_size = 0
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
                raise ValueError("Attachment exceeds the 8 MB encoded-size limit.")
            total_size += len(content)
            if total_size > 8_000_000:
                raise ValueError("Combined attachments exceed the request size limit.")
            if mime_type not in self.supported:
                guessed, _ = mimetypes.guess_type(name)
                if guessed in self.supported:
                    mime_type = guessed
            if mime_type == "text/plain":
                normalized.append(
                    {"name": name[:256], "mime_type": mime_type, "text": content[:100_000]}
                )
            elif mime_type in {"image/png", "image/jpeg", "image/webp"}:
                try:
                    image_bytes = base64.b64decode(content, validate=True)
                except ValueError as error:
                    raise ValueError(f"Image attachment {name!r} is not valid base64.") from error
                if len(image_bytes) > 6_000_000:
                    raise ValueError("Decoded image exceeds the 6 MB limit.")
                valid_signature = (
                    image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
                    if mime_type == "image/png"
                    else image_bytes.startswith(b"\xff\xd8\xff")
                    if mime_type == "image/jpeg"
                    else image_bytes.startswith(b"RIFF")
                    and image_bytes[8:12] == b"WEBP"
                )
                if not valid_signature:
                    raise ValueError(
                        f"Image attachment {name!r} does not match its declared type."
                    )
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