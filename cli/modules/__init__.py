"""Module registry.

To add a feature:
  1. Create ``cli/modules/<name>.py`` with a Container subclass (the "pane").
  2. Import it here and append a ``ModuleSpec`` to ``MODULES``.
The app picks it up automatically: sidebar entry, F-key-free navigation, and all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Type

from textual.containers import Container

from .dashboard import DashboardPane
from .compiler import CompilerPane
from .learning import LearningPane
from .memory import MemoryPane
from .models import ModelsPane
from .notes import NotesPane
from .settings import SettingsPane


@dataclass(frozen=True)
class ModuleSpec:
    key: str  # unique id, also the widget id of the pane
    title: str  # label shown in the sidebar
    pane_cls: Type[Container]


MODULES: tuple[ModuleSpec, ...] = (
    ModuleSpec("dashboard", "Dashboard", DashboardPane),
    ModuleSpec("memory", "Memory", MemoryPane),
    ModuleSpec("learning", "Learning", LearningPane),
    ModuleSpec("compiler", "Compiler", CompilerPane),
    ModuleSpec("models", "Models", ModelsPane),
    ModuleSpec("notes", "Notes", NotesPane),
    ModuleSpec("settings", "Settings", SettingsPane),
)


def module_by_key(key: str) -> ModuleSpec | None:
    return next((m for m in MODULES if m.key == key), None)
