from collections.abc import Callable
from typing import Protocol


class Tokenizer(Protocol):
    def encode(self, text: str) -> list[int]: ...

    def decode(self, tokens: list[int]) -> str: ...


class ApproximateTokenizer:
    """Conservative fallback for remote servers that do not expose tokenization."""

    def encode(self, text: str) -> list[int]:
        return list(range((len(text.encode("utf-8")) + 3) // 4))

    def decode(self, tokens: list[int]) -> str:
        raise NotImplementedError("Approximate token IDs cannot be decoded.")


class BackendTokenizer:
    def __init__(
        self,
        encode: Callable[[str], list[int]],
        decode: Callable[[list[int]], str],
    ) -> None:
        self._encode = encode
        self._decode = decode

    def encode(self, text: str) -> list[int]:
        return self._encode(text)

    def decode(self, tokens: list[int]) -> str:
        return self._decode(tokens)
