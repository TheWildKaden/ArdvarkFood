import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4


class StorageManager:
    """Durable SQLite storage for conversations, runs, tools, memory, and audit."""

    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS messages_conversation_idx
                    ON messages(conversation_id, id);
                CREATE TABLE IF NOT EXISTS executions (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    status TEXT NOT NULL, state TEXT NOT NULL DEFAULT '{}',
                    error TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS tool_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    execution_id TEXT NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
                    tool_call_id TEXT NOT NULL, tool_name TEXT NOT NULL, permission TEXT NOT NULL,
                    status TEXT NOT NULL, arguments TEXT NOT NULL, result TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, conversation_id TEXT,
                    content TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, execution_id TEXT,
                    action TEXT NOT NULL, details TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT OR IGNORE INTO schema_migrations(version) VALUES(1);
                """
            )
            db.execute(
                "UPDATE executions SET status='interrupted', "
                "error='Process restarted during execution', "
                "updated_at=CURRENT_TIMESTAMP WHERE status='running'"
            )

    @staticmethod
    def new_id() -> str:
        return uuid4().hex

    def create_conversation(self, title: str = "") -> dict[str, Any]:
        conversation_id = self.new_id()
        with self._connect() as db:
            db.execute(
                "INSERT INTO conversations (id, title) VALUES (?, ?)",
                (conversation_id, title[:256]),
            )
        return {"id": conversation_id, "title": title[:256]}

    def list_conversations(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT c.id, c.title, c.created_at, c.updated_at, "
                "(SELECT content FROM messages m WHERE m.conversation_id=c.id "
                "ORDER BY m.id DESC LIMIT 1) AS last_message "
                "FROM conversations c ORDER BY c.updated_at DESC LIMIT ?",
                (min(max(limit, 1), 200),),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._connect() as db:
            result = db.execute(
                "DELETE FROM conversations WHERE id=?", (conversation_id,)
            )
        return result.rowcount > 0

    def add_message(
        self, conversation_id: str, role: str, content: str, metadata: Any = None
    ) -> int:
        with self._connect() as db:
            cursor = db.execute(
                "INSERT INTO messages (conversation_id, role, content, metadata) "
                "VALUES (?, ?, ?, ?)",
                (
                    conversation_id,
                    role,
                    content,
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                ),
            )
            db.execute(
                "UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (conversation_id,),
            )
        return int(cursor.lastrowid)

    def get_messages(self, conversation_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, role, content, metadata, created_at FROM "
                "(SELECT * FROM messages WHERE conversation_id=? "
                "ORDER BY id DESC LIMIT ?) ORDER BY id ASC",
                (conversation_id, min(max(limit, 1), 500)),
            ).fetchall()
        messages = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"])
            messages.append(item)
        return messages

    def conversation_exists(self, conversation_id: str) -> bool:
        with self._connect() as db:
            return db.execute(
                "SELECT 1 FROM conversations WHERE id=?", (conversation_id,)
            ).fetchone() is not None

    def start_execution(self, conversation_id: str) -> str:
        execution_id = self.new_id()
        with self._connect() as db:
            db.execute(
                "INSERT INTO executions (id, conversation_id, status) "
                "VALUES (?, ?, 'running')",
                (execution_id, conversation_id),
            )
        return execution_id

    def update_execution(
        self, execution_id: str, status: str, state: Any = None, error: str | None = None
    ) -> None:
        with self._connect() as db:
            db.execute(
                "UPDATE executions SET status=?, state=?, error=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (
                    status,
                    json.dumps(state or {}, ensure_ascii=False, default=str),
                    error[:2000] if error else None,
                    execution_id,
                ),
            )

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT id, conversation_id, status, state, error, created_at, updated_at "
                "FROM executions WHERE id=?",
                (execution_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["state"] = json.loads(result["state"])
        return result

    def record_tool_event(
        self,
        execution_id: str,
        call_id: str,
        name: str,
        permission: str,
        status: str,
        arguments: Any,
        result: Any = None,
    ) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO tool_events "
                "(execution_id, tool_call_id, tool_name, permission, status, arguments, result) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    execution_id,
                    call_id,
                    name,
                    permission,
                    status,
                    json.dumps(arguments, ensure_ascii=False, default=str),
                    json.dumps(result, ensure_ascii=False, default=str)
                    if result is not None
                    else None,
                ),
            )

    def add_audit(self, execution_id: str | None, action: str, details: Any) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO audit_log (execution_id, action, details) VALUES (?, ?, ?)",
                (execution_id, action, json.dumps(details, ensure_ascii=False, default=str)),
            )

    def add_memory(
        self, content: str, conversation_id: str | None = None, metadata: Any = None
    ) -> str:
        memory_id = self.new_id()
        with self._connect() as db:
            db.execute(
                "INSERT INTO memories (id, conversation_id, content, metadata) "
                "VALUES (?, ?, ?, ?)",
                (
                    memory_id,
                    conversation_id,
                    content,
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                ),
            )
        return memory_id

    def search_memories(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        terms = [term for term in query.split() if len(term) > 2][:6]
        if not terms:
            return []
        where = " OR ".join("content LIKE ?" for _ in terms)
        with self._connect() as db:
            rows = db.execute(
                f"SELECT id, content, metadata FROM memories WHERE {where} "
                "ORDER BY created_at DESC LIMIT ?",
                (*[f"%{term[:64]}%" for term in terms], min(max(limit, 1), 20)),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"])
            if self._memory_is_active(item["metadata"]):
                result.append(item)
        return result

    def list_memories(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, conversation_id, content, metadata, created_at FROM memories "
                "ORDER BY created_at DESC LIMIT ?",
                (min(max(limit, 1), 500),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"])
            if self._memory_is_active(item["metadata"]):
                result.append(item)
        return result

    @staticmethod
    def _memory_is_active(metadata: dict[str, Any]) -> bool:
        if metadata.get("superseded_by"):
            return False
        expires_at = metadata.get("expires_at")
        if not isinstance(expires_at, str) or not expires_at:
            return True
        try:
            from datetime import datetime, timezone

            expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            return expiry > datetime.now(timezone.utc)
        except ValueError:
            return False

    def update_memory(
        self, memory_id: str, content: str, metadata: Any | None = None
    ) -> bool:
        with self._connect() as db:
            row = db.execute(
                "SELECT metadata FROM memories WHERE id=?", (memory_id,)
            ).fetchone()
            if row is None:
                return False
            updated_metadata = (
                json.dumps(metadata, ensure_ascii=False, default=str)
                if metadata is not None
                else row["metadata"]
            )
            result = db.execute(
                "UPDATE memories SET content=?, metadata=? WHERE id=?",
                (content, updated_metadata, memory_id),
            )
        return result.rowcount == 1

    def delete_memory(self, memory_id: str) -> bool:
        with self._connect() as db:
            result = db.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        return result.rowcount == 1

    def delete_memories_for_conversation(self, conversation_id: str) -> int:
        with self._connect() as db:
            result = db.execute(
                "DELETE FROM memories WHERE conversation_id=?", (conversation_id,)
            )
        return result.rowcount

    def delete_memory_by_content(self, content: str) -> int:
        normalized = " ".join(content.casefold().split())
        with self._connect() as db:
            rows = db.execute("SELECT id, content FROM memories").fetchall()
            matched = [
                row["id"]
                for row in rows
                if " ".join(row["content"].casefold().split()) == normalized
            ]
            db.executemany("DELETE FROM memories WHERE id=?", [(item,) for item in matched])
        return len(matched)

    def backup(self, destination: str | Path | None = None) -> Path:
        backup_directory = self.database_path.parent / "backups"
        target = (
            Path(destination).expanduser().resolve()
            if destination is not None
            else backup_directory / f"runtime-{self.new_id()}.sqlite3"
        )
        if target == self.database_path:
            raise ValueError("A database backup cannot overwrite the live database.")
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with sqlite3.connect(self.database_path, timeout=30) as source:
                with sqlite3.connect(temporary, timeout=30) as backup:
                    source.backup(backup)
                    integrity = backup.execute("PRAGMA integrity_check").fetchone()[0]
                    if integrity != "ok":
                        raise sqlite3.DatabaseError(
                            f"Backup integrity check failed: {integrity}"
                        )
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return target

    def restore(self, backup_path: str | Path) -> Path:
        """Restore a verified SQLite snapshot; call only while the runtime is stopped."""
        source = Path(backup_path).expanduser().resolve(strict=True)
        if source == self.database_path or not source.is_file():
            raise ValueError("Restore source must be a separate database file.")
        try:
            with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as backup:
                integrity = backup.execute("PRAGMA integrity_check").fetchone()[0]
                tables = {
                    row[0]
                    for row in backup.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if integrity != "ok" or not {"conversations", "messages", "memories"}.issubset(tables):
                    raise ValueError("Restore source is not a valid Ardvark SQLite backup.")
        except sqlite3.DatabaseError as error:
            raise ValueError("Restore source is not a valid SQLite database.") from error

        backup_of_current = self.backup()
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.database_path.name}.restore.",
            suffix=".tmp",
            dir=self.database_path.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as backup:
                with sqlite3.connect(temporary) as restored:
                    backup.backup(restored)
                    integrity = restored.execute("PRAGMA integrity_check").fetchone()[0]
                    if integrity != "ok":
                        raise sqlite3.DatabaseError(
                            f"Restored database integrity check failed: {integrity}"
                        )
            os.replace(temporary, self.database_path)
            self._initialize()
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return backup_of_current