"""Settings pane: appearance toggles and read-only environment info."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Label, Static, Switch

from ..config import DATA_DIR


def _is_dark(app) -> bool:
    return app.theme.endswith("dark")


class SettingsPane(Container):
    def compose(self) -> ComposeResult:
        with Horizontal(id="settings-row"):
            yield Label("Dark mode")
            yield Switch(value=_is_dark(self.app), id="dark-switch")
        yield Static(f"Data directory: {DATA_DIR}", id="data-dir")

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "dark-switch":
            self.app.theme = "textual-dark" if event.value else "textual-light"
