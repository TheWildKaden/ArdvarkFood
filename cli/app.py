"""Main application shell: sidebar navigation plus a switchable content area.

Modules are discovered from ``cli.modules.MODULES``; this file does not
need to change when a module is added.
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import ContentSwitcher, Footer, Header, Label, ListItem, ListView

from .config import APP_NAME
from .modules import MODULES, module_by_key

NAV_PREFIX = "nav-"


class TUIApp(App):
    TITLE = APP_NAME
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("f1", "show('dashboard')", "Dashboard"),
        Binding("f2", "show('notes')", "Notes"),
        Binding("f3", "show('settings')", "Settings"),
        Binding("f4", "show('memory')", "Memory"),
        Binding("f5", "show('learning')", "Learning"),
        Binding("f6", "show('compiler')", "Compiler"),
        Binding("f7", "show('models')", "Models"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            yield ListView(
                *(
                    ListItem(Label(module.title), id=f"{NAV_PREFIX}{module.key}")
                    for module in MODULES
                ),
                id="sidebar",
            )
            with ContentSwitcher(initial=MODULES[0].key, id="content"):
                for module in MODULES:
                    yield module.pane_cls(id=module.key)
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "sidebar" and event.item.id:
            self.action_show(event.item.id.removeprefix(NAV_PREFIX))

    def action_show(self, key: str) -> None:
        """Switch the content area to the module registered under ``key``."""
        if module_by_key(key) is None:
            return
        self.query_one("#content", ContentSwitcher).current = key
