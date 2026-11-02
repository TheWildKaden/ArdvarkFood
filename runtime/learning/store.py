from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4


class LearningStore:
    """Learning tables sharing the runtime's SQLite database and transaction model."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversation_learning (
                    conversation_id TEXT PRIMARY KEY
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS learning_queue (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(conversation_id, kind)
                );
                CREATE INDEX IF NOT EXISTS learning_queue_status_idx
                    ON learning_queue(status, created_at);
                CREATE TABLE IF NOT EXISTS training_examples (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    message_ids TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    response TEXT NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'pending_review',
                    quality_score REAL NOT NULL,
                    review_note TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS training_examples_status_idx
                    ON training_examples(status, created_at);
                CREATE TABLE IF NOT EXISTS dataset_versions (
                    id TEXT PRIMARY KEY,
                    version INTEGER NOT NULL UNIQUE,
                    artifact_path TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS dataset_examples (
                    dataset_id TEXT NOT NULL REFERENCES dataset_versions(id) ON DELETE CASCADE,
                    example_id TEXT NOT NULL REFERENCES training_examples(id) ON DELETE RESTRICT,
                    PRIMARY KEY(dataset_id, example_id)
                );
                CREATE TABLE IF NOT EXISTS training_jobs (
                    id TEXT PRIMARY KEY,
                    dataset_id TEXT NOT NULL REFERENCES dataset_versions(id) ON DELETE RESTRICT,
                    base_model TEXT NOT NULL,
                    config TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    metrics TEXT NOT NULL DEFAULT '{}',
                    model_id TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TEXT,
                    completed_at TEXT
                );
                CREATE INDEX IF NOT EXISTS training_jobs_status_idx
                    ON training_jobs(status, created_at);
                CREATE TABLE IF NOT EXISTS model_registry (
                    id TEXT PRIMARY KEY,
                    base_model TEXT NOT NULL,
                    method TEXT NOT NULL,
                    adapter_path TEXT NOT NULL,
                    dataset_id TEXT REFERENCES dataset_versions(id) ON DELETE SET NULL,
                    training_config TEXT NOT NULL DEFAULT '{}',
                    evaluation_metrics TEXT NOT NULL DEFAULT '{}',
                    export_format TEXT NOT NULL,
                    compatible INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'candidate',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    activated_at TEXT
                );
                CREATE INDEX IF NOT EXISTS model_registry_status_idx
                    ON model_registry(status, created_at);
                """
            )
            db.execute(
                "UPDATE learning_queue SET status='queued', updated_at=CURRENT_TIMESTAMP "
                "WHERE status='running'"
            )
            db.execute(
                "UPDATE training_jobs SET status='interrupted', "
                "error='Training process stopped before completion', "
                "completed_at=CURRENT_TIMESTAMP WHERE status='running'"
            )

    @staticmethod
    def new_id() -> str:
        return uuid4().hex

    def set_conversation_learning(self, conversation_id: str, enabled: bool) -> None:
        with self._connect() as db:
            if not db.execute(
                "SELECT 1 FROM conversations WHERE id=?", (conversation_id,)
            ).fetchone():
                raise KeyError("Conversation not found.")
            db.execute(
                "INSERT INTO conversation_learning(conversation_id, enabled) VALUES(?, ?) "
                "ON CONFLICT(conversation_id) DO UPDATE SET enabled=excluded.enabled, "
                "updated_at=CURRENT_TIMESTAMP",
                (conversation_id, int(enabled)),
            )
            if not enabled:
                db.execute(
                    "UPDATE learning_queue SET status='cancelled', "
                    "updated_at=CURRENT_TIMESTAMP WHERE conversation_id=? "
                    "AND status IN ('queued', 'running')",
                    (conversation_id,),
                )
                db.execute(
                    "DELETE FROM training_examples WHERE conversation_id=? "
                    "AND status != 'approved'",
                    (conversation_id,),
                )

    def conversation_learning_enabled(self, conversation_id: str) -> bool:
        with self._connect() as db:
            row = db.execute(
                "SELECT enabled FROM conversation_learning WHERE conversation_id=?",
                (conversation_id,),
            ).fetchone()
        return bool(row and row["enabled"])

    def enqueue(self, conversation_id: str, kind: str) -> str:
        if kind not in {"memory", "training_examples"}:
            raise ValueError("Unsupported learning task.")
        if not self.conversation_learning_enabled(conversation_id):
            raise PermissionError("Conversation learning is not enabled.")
        job_id = self.new_id()
        with self._connect() as db:
            db.execute(
                "INSERT INTO learning_queue(id, conversation_id, kind) VALUES(?, ?, ?) "
                "ON CONFLICT(conversation_id, kind) DO UPDATE SET "
                "status=CASE WHEN learning_queue.status IN ('failed','cancelled') "
                "THEN 'queued' ELSE learning_queue.status END, "
                "updated_at=CURRENT_TIMESTAMP",
                (job_id, conversation_id, kind),
            )
            row = db.execute(
                "SELECT id FROM learning_queue WHERE conversation_id=? AND kind=?",
                (conversation_id, kind),
            ).fetchone()
        return str(row["id"])

    def queued(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, conversation_id, kind, attempts FROM learning_queue "
                "WHERE status='queued' ORDER BY created_at LIMIT 20"
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_queue_running(self, job_id: str) -> bool:
        with self._connect() as db:
            result = db.execute(
                "UPDATE learning_queue SET status='running', attempts=attempts+1, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='queued'",
                (job_id,),
            )
        return result.rowcount == 1

    def finish_queue(self, job_id: str, error: str | None = None) -> None:
        with self._connect() as db:
            row = db.execute(
                "SELECT attempts FROM learning_queue WHERE id=?", (job_id,)
            ).fetchone()
            status = "processed" if error is None else (
                "queued" if row and row["attempts"] < 3 else "failed"
            )
            db.execute(
                "UPDATE learning_queue SET status=?, error=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE id=?",
                (status, error[:500] if error else None, job_id),
            )

    def list_examples(
        self, status: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT id, conversation_id, message_ids, prompt, response, status, "
            "quality_score, review_note, created_at, updated_at FROM training_examples"
        )
        parameters: list[Any] = []
        if status is not None:
            if status not in {"pending_review", "approved", "rejected"}:
                raise ValueError("Unsupported training example status.")
            query += " WHERE status=?"
            parameters.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        parameters.append(min(max(limit, 1), 500))
        with self._connect() as db:
            rows = db.execute(query, parameters).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["message_ids"] = json.loads(item["message_ids"])
            results.append(item)
        return results

    def add_example(
        self,
        conversation_id: str,
        message_ids: list[int],
        prompt: str,
        response: str,
        content_hash: str,
        quality_score: float,
    ) -> bool:
        with self._connect() as db:
            result = db.execute(
                "INSERT OR IGNORE INTO training_examples"
                "(id, conversation_id, message_ids, prompt, response, content_hash, quality_score) "
                "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    self.new_id(),
                    conversation_id,
                    json.dumps(message_ids),
                    prompt,
                    response,
                    content_hash,
                    quality_score,
                ),
            )
        return result.rowcount == 1

    def review_example(
        self, example_id: str, approved: bool, review_note: str = ""
    ) -> bool:
        with self._connect() as db:
            result = db.execute(
                "UPDATE training_examples SET status=?, review_note=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending_review'",
                (
                    "approved" if approved else "rejected",
                    review_note[:1000],
                    example_id,
                ),
            )
        return result.rowcount == 1

    def delete_example(self, example_id: str) -> bool:
        with self._connect() as db:
            result = db.execute(
                "DELETE FROM training_examples WHERE id=? AND status!='approved'",
                (example_id,),
            )
        return result.rowcount == 1

    def create_dataset(
        self, artifact_path: str, sha256: str, sample_count: int, metadata: dict[str, Any]
    ) -> dict[str, Any]:
        dataset_id = self.new_id()
        with self._connect() as db:
            version = int(
                db.execute("SELECT COALESCE(MAX(version), 0)+1 FROM dataset_versions").fetchone()[0]
            )
            db.execute(
                "INSERT INTO dataset_versions(id, version, artifact_path, sha256, sample_count, metadata) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (
                    dataset_id,
                    version,
                    artifact_path,
                    sha256,
                    sample_count,
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            example_ids = metadata.get("example_ids", [])
            db.executemany(
                "INSERT INTO dataset_examples(dataset_id, example_id) VALUES(?, ?)",
                [(dataset_id, example_id) for example_id in example_ids],
            )
            row = db.execute(
                "SELECT id, version, artifact_path, sha256, sample_count, metadata, created_at "
                "FROM dataset_versions WHERE id=?",
                (dataset_id,),
            ).fetchone()
        result = dict(row)
        result["metadata"] = json.loads(result["metadata"])
        return result

    def list_datasets(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, version, artifact_path, sha256, sample_count, metadata, created_at "
                "FROM dataset_versions ORDER BY version DESC LIMIT ?",
                (min(max(limit, 1), 500),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"])
            result.append(item)
        return result

    def create_training_job(
        self, dataset_id: str, base_model: str, config: dict[str, Any]
    ) -> str:
        job_id = self.new_id()
        with self._connect() as db:
            db.execute(
                "INSERT INTO training_jobs(id, dataset_id, base_model, config) VALUES(?, ?, ?, ?)",
                (job_id, dataset_id, base_model, json.dumps(config, ensure_ascii=False)),
            )
        return job_id

    def list_training_jobs(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, dataset_id, base_model, config, status, metrics, model_id, "
                "error, created_at, started_at, completed_at FROM training_jobs "
                "ORDER BY created_at DESC LIMIT ?",
                (min(max(limit, 1), 500),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["config"] = json.loads(item["config"])
            item["metrics"] = json.loads(item["metrics"])
            result.append(item)
        return result

    def list_models(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, base_model, method, adapter_path, dataset_id, training_config, "
                "evaluation_metrics, export_format, compatible, status, created_at, activated_at "
                "FROM model_registry ORDER BY created_at DESC"
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["training_config"] = json.loads(item["training_config"])
            item["evaluation_metrics"] = json.loads(item["evaluation_metrics"])
            item["compatible"] = bool(item["compatible"])
            result.append(item)
        return result

    def get_status_counts(self) -> dict[str, int]:
        with self._connect() as db:
            queue = db.execute(
                "SELECT status, COUNT(*) AS count FROM learning_queue GROUP BY status"
            ).fetchall()
            examples = db.execute(
                "SELECT status, COUNT(*) AS count FROM training_examples GROUP BY status"
            ).fetchall()
            jobs = db.execute(
                "SELECT status, COUNT(*) AS count FROM training_jobs GROUP BY status"
            ).fetchall()
            processed = db.execute(
                "SELECT COUNT(*) FROM learning_queue WHERE kind='memory' AND status='processed'"
            ).fetchone()[0]
        counts = {
            "queued_learning": 0,
            "processed_conversations": int(processed),
            "candidate_examples": 0,
            "approved_examples": 0,
            "training_jobs": 0,
            "failed_jobs": 0,
        }
        counts["queued_learning"] = sum(
            int(row["count"]) for row in queue if row["status"] in {"queued", "running"}
        )
        for row in examples:
            if row["status"] == "pending_review":
                counts["candidate_examples"] = int(row["count"])
            elif row["status"] == "approved":
                counts["approved_examples"] = int(row["count"])
        for row in jobs:
            counts["training_jobs"] += int(row["count"])
            if row["status"] in {"failed", "interrupted"}:
                counts["failed_jobs"] += int(row["count"])
        return counts
