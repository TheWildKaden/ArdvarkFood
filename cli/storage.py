"""Compatibility exports for the CLI's JSON-backed storage service."""

from .services.storage import JsonStore

__all__ = ["JsonStore"]
