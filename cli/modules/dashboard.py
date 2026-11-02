"""Dashboard pane: live clock and basic system information."""

from __future__ import annotations

import platform
from datetime import datetime

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static


class DashboardPane(Container):
    def compose(self) -> ComposeResult:
        yield Static(id="clock")
        yield Static(id="sysinfo")

    def on_mount(self) -> None:
        self._tick()
        self.set_interval(1, self._tick)

    def _tick(self) -> None:
        now = datetime.now()
        self.query_one("#clock", Static).update(now.strftime("%H:%M:%S"))
        self.query_one("#sysinfo", Static).update(
            f"{now:%A, %B %d %Y}  ·  Python {platform.python_version()}  ·  {platform.system()}"
        )
