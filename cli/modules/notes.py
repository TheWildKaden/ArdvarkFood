"""Notes pane: create, edit, save and delete plain-text notes."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Input, Label, ListItem, ListView, TextArea

from ..config import NOTES_FILE
from ..services.storage import JsonStore


class NotesPane(Container):
    def __init__(self, store: JsonStore | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.store = store or JsonStore(NOTES_FILE)
        self.notes: list[dict] = []
        self._current: int | None = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="notes-list-col"):
                yield ListView(id="notes-list")
                yield Button("New", id="new-note", variant="primary")
                yield Button("Delete", id="del-note", variant="error")
            with Vertical(id="notes-edit-col"):
                yield Input(placeholder="Title", id="note-title")
                yield TextArea(id="note-body")
                yield Button("Save", id="save-note", variant="success")

    def on_mount(self) -> None:
        self.notes = self.store.load()
        self._refresh_list(select=0 if self.notes else None)

    # -- list and editor state -------------------------------------------------

    def _refresh_list(self, select: int | None) -> None:
        lv = self.query_one("#notes-list", ListView)
        lv.clear()
        lv.extend([ListItem(Label(n.get("title") or "(untitled)")) for n in self.notes])
        if select is not None and self.notes:
            lv.call_after_refresh(setattr, lv, "index", select)
            self._show(select)
        else:
            self._show(None)

    def _show(self, index: int | None) -> None:
        self._current = index
        title = self.query_one("#note-title", Input)
        body = self.query_one("#note-body", TextArea)
        if index is None:
            title.value = ""
            body.load_text("")
            return
        note = self.notes[index]
        title.value = note.get("title", "")
        body.load_text(note.get("body", ""))

    # -- events ----------------------------------------------------------------

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "notes-list" and event.list_view.index is not None:
            self._show(event.list_view.index)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "new-note":
            self.notes.append({"title": "", "body": ""})
            self._refresh_list(select=len(self.notes) - 1)
        elif event.button.id == "save-note":
            self._save_current()
        elif event.button.id == "del-note":
            self._delete_current()

    # -- actions ---------------------------------------------------------------

    def _save_current(self) -> None:
        if self._current is None:
            self.notes.append({})
            self._current = len(self.notes) - 1
        self.notes[self._current] = {
            "title": self.query_one("#note-title", Input).value.strip(),
            "body": self.query_one("#note-body", TextArea).text,
        }
        self.store.save(self.notes)
        self._refresh_list(select=self._current)
        self.app.notify("Note saved")

    def _delete_current(self) -> None:
        if self._current is None:
            return
        del self.notes[self._current]
        self.store.save(self.notes)
        next_index = min(self._current, len(self.notes) - 1) if self.notes else None
        self._refresh_list(select=next_index)
        self.app.notify("Note deleted")
