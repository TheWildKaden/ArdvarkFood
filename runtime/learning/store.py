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
                    conversation_id TEXT
                        REFERENCES conversations(id) ON DELETE CASCADE,
                    message_ids TEXT NOT NULL DEFAULT '[]',
                    messages TEXT NOT NULL DEFAULT '[]',
                    tools TEXT NOT NULL DEFAULT '[]',
                    prompt TEXT NOT NULL,
                    response TEXT NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    source_kind TEXT NOT NULL DEFAULT 'conversation',
                    source_ref TEXT NOT NULL DEFAULT '',
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
                    status TEXT NOT NULL DEFAULT 'active',
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
            example_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(training_examples)")
            }
            if "messages" not in example_columns:
                db.execute(
                    "ALTER TABLE training_examples ADD COLUMN messages TEXT NOT NULL DEFAULT '[]'"
                )
            if "tools" not in example_columns:
                db.execute(
                    "ALTER TABLE training_examples ADD COLUMN tools TEXT NOT NULL DEFAULT '[]'"
                )
            if "source_kind" not in example_columns:
                db.execute(
                    "ALTER TABLE training_examples ADD COLUMN source_kind TEXT NOT NULL "
                    "DEFAULT 'conversation'"
                )
            if "source_ref" not in example_columns:
                db.execute(
                    "ALTER TABLE training_examples ADD COLUMN source_ref TEXT NOT NULL DEFAULT ''"
                )
            dataset_columns = {
                row["name"] for row in db.execute("PRAGMA table_info(dataset_versions)")
            }
            if "status" not in dataset_columns:
                db.execute(
                    "ALTER TABLE dataset_versions ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
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

    def set_conversation_learning(self, conversation_id: str, enabled: bool) -> list[str]:
        dataset_paths: list[str] = []
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
                affected = db.execute(
                    "SELECT DISTINCT d.id, d.artifact_path FROM dataset_versions d "
                    "JOIN dataset_examples de ON de.dataset_id=d.id "
                    "JOIN training_examples e ON e.id=de.example_id "
                    "WHERE e.conversation_id=?",
                    (conversation_id,),
                ).fetchall()
                dataset_ids = [row["id"] for row in affected]
                dataset_paths = [row["artifact_path"] for row in affected]
                if dataset_ids:
                    placeholders = ",".join("?" for _ in dataset_ids)
                    db.execute(
                        f"UPDATE dataset_versions SET status='withdrawn' WHERE id IN ({placeholders})",
                        dataset_ids,
                    )
                    db.execute(
                        f"UPDATE training_jobs SET status='cancelled', "
                        f"error='Source conversation opted out', "
                        f"completed_at=CURRENT_TIMESTAMP WHERE dataset_id IN ({placeholders}) "
                        "AND status IN ('queued','running')",
                        dataset_ids,
                    )
                    db.execute(
                        f"DELETE FROM dataset_examples WHERE dataset_id IN ({placeholders})",
                        dataset_ids,
                    )
                db.execute(
                    "UPDATE learning_queue SET status='cancelled', "
                    "updated_at=CURRENT_TIMESTAMP WHERE conversation_id=? "
                    "AND status IN ('queued', 'running')",
                    (conversation_id,),
                )
                db.execute(
                    "DELETE FROM training_examples WHERE conversation_id=?",
                    (conversation_id,),
                )
        return dataset_paths

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
            "SELECT id, conversation_id, message_ids, messages, tools, prompt, response, "
            "source_kind, source_ref, status, quality_score, review_note, created_at, "
            "updated_at FROM training_examples"
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
            item["messages"] = json.loads(item["messages"])
            item["tools"] = json.loads(item["tools"])
            results.append(item)
        return results

    def add_example(
        self,
        conversation_id: str | None,
        message_ids: list[int],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        prompt: str,
        response: str,
        content_hash: str,
        quality_score: float,
        *,
        source_kind: str = "conversation",
        source_ref: str = "",
    ) -> bool:
        with self._connect() as db:
            result = db.execute(
                "INSERT OR IGNORE INTO training_examples"
                "(id, conversation_id, message_ids, messages, tools, prompt, response, content_hash, "
                "source_kind, source_ref, quality_score) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.new_id(),
                    conversation_id,
                    json.dumps(message_ids),
                    json.dumps(messages, ensure_ascii=False),
                    json.dumps(tools, ensure_ascii=False),
                    prompt,
                    response,
                    content_hash,
                    source_kind,
                    source_ref,
                    quality_score,
                ),
            )
        return result.rowcount == 1

    def add_external_example(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        source_ref: str,
        content_hash: str,
        quality_score: float,
    ) -> bool:
        serialized = messages
        prompt = next(
            (item["content"] for item in messages if item["role"] == "user"), ""
        )
        response = next(
            (item["content"] for item in reversed(messages) if item["role"] == "assistant"),
            "",
        )
        with self._connect() as db:
            result = db.execute(
                "INSERT OR IGNORE INTO training_examples"
                "(id, message_ids, messages, tools, prompt, response, content_hash, source_kind, "
                "source_ref, status, quality_score) VALUES(?, '[]', ?, ?, ?, ?, "
                "'huggingface', ?, 'pending_review', ?)",
                (
                    self.new_id(),
                    json.dumps(serialized, ensure_ascii=False),
                    json.dumps(tools, ensure_ascii=False),
                    prompt if isinstance(prompt, str) else json.dumps(prompt, ensure_ascii=False),
                    response if isinstance(response, str) else json.dumps(response, ensure_ascii=False),
                    content_hash,
                    source_ref,
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
                "SELECT id, version, artifact_path, sha256, sample_count, metadata, status, created_at "
                "FROM dataset_versions ORDER BY version DESC LIMIT ?",
                (min(max(limit, 1), 500),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"])
            result.append(item)
        return result

    def approved_examples(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, conversation_id, message_ids, messages, source_kind, source_ref "
                "FROM training_examples WHERE status='approved' ORDER BY created_at, id"
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["message_ids"] = json.loads(item["message_ids"])
            item["messages"] = json.loads(item["messages"])
            result.append(item)
        return result

    def get_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT id, version, artifact_path, sha256, sample_count, metadata, status "
                "FROM dataset_versions WHERE id=?",
                (dataset_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["metadata"] = json.loads(result["metadata"])
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

    def claim_training_job(self) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT id, dataset_id, base_model, config FROM training_jobs "
                "WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            result = db.execute(
                "UPDATE training_jobs SET status='running', started_at=CURRENT_TIMESTAMP "
                "WHERE id=? AND status='queued'",
                (row["id"],),
            )
            if result.rowcount != 1:
                return None
            job = dict(row)
            job["config"] = json.loads(job["config"])
            dataset = db.execute(
                "SELECT artifact_path, status, metadata FROM dataset_versions WHERE id=?",
                (job["dataset_id"],),
            ).fetchone()
            if dataset is None or dataset["status"] != "active":
                db.execute(
                    "UPDATE training_jobs SET status='cancelled', "
                    "error='Training dataset is unavailable', "
                    "completed_at=CURRENT_TIMESTAMP WHERE id=?",
                    (job["id"],),
                )
                return None
            job["dataset_path"] = dataset["artifact_path"]
            return job

    def finish_training_job(
        self,
        job_id: str,
        *,
        status: str,
        metrics: dict[str, Any] | None = None,
        model_id: str | None = None,
        error: str | None = None,
    ) -> None:
        if status not in {"completed", "failed", "cancelled"}:
            raise ValueError("Invalid training job final status.")
        with self._connect() as db:
            db.execute(
                "UPDATE training_jobs SET status=?, metrics=?, model_id=?, error=?, "
                "completed_at=CURRENT_TIMESTAMP WHERE id=? AND status='running'",
                (
                    status,
                    json.dumps(metrics or {}, ensure_ascii=False),
                    model_id,
                    error[:500] if error else None,
                    job_id,
                ),
            )

    def add_model(
        self,
        *,
        base_model: str,
        method: str,
        artifact_path: str,
        dataset_id: str,
        training_config: dict[str, Any],
        evaluation_metrics: dict[str, Any],
        export_format: str,
        compatible: bool,
    ) -> str:
        model_id = self.new_id()
        with self._connect() as db:
            db.execute(
                "INSERT INTO model_registry"
                "(id, base_model, method, adapter_path, dataset_id, training_config, "
                "evaluation_metrics, export_format, compatible, status) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate')",
                (
                    model_id,
                    base_model,
                    method,
                    artifact_path,
                    dataset_id,
                    json.dumps(training_config, ensure_ascii=False),
                    json.dumps(evaluation_metrics, ensure_ascii=False),
                    export_format,
                    int(compatible),
                ),
            )
        return model_id

    def activate_model(self, model_id: str) -> bool:
        with self._connect() as db:
            model = db.execute(
                "SELECT compatible, status, evaluation_metrics FROM model_registry WHERE id=?",
                (model_id,),
            ).fetchone()
            if model is None or not model["compatible"]:
                return False
            metrics = json.loads(model["evaluation_metrics"])
            if metrics.get("passed") is not True:
                return False
            db.execute(
                "UPDATE model_registry SET status='previous' WHERE status='active'"
            )
            db.execute(
                "UPDATE model_registry SET status='active', activated_at=CURRENT_TIMESTAMP "
                "WHERE id=?",
                (model_id,),
            )
        return True

    def rollback_model_id(self) -> str | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT id FROM model_registry WHERE status='previous' AND compatible=1 "
                "ORDER BY activated_at DESC LIMIT 1"
            ).fetchone()
        return str(row["id"]) if row else None

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        return next((model for model in self.list_models() if model["id"] == model_id), None)

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
