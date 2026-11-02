"""Application-wide constants. Edit here to change names or storage locations."""

from pathlib import Path

APP_NAME = "TUI Workbench"

DATA_DIR = Path.home() / ".tuiapp"
NOTES_FILE = DATA_DIR / "notes.json"
