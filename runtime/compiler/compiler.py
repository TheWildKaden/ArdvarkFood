from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any


class CompilationError(ValueError):
    """Raised when an artifact is unsupported or invalid."""


@dataclass(frozen=True)
class DecompilationResult:
    output_path: str
    records: int
    exact_source_recovered: bool
    notes: tuple[str, ...]


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_atomic(path: Path, writer: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            writer(output)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


class ArtifactCompiler:
    """Compile JSON/JSONL to validated compact artifacts without changing sources."""

    SUPPORTED_FORMATS = {"json", "jsonl"}

    def compile(
        self,
        source_path: str | Path,
        output_path: str | Path,
        *,
        format: str | None = None,
        deduplicate: bool = False,
    ) -> dict[str, Any]:
        source = Path(source_path).expanduser().resolve(strict=True)
        output = Path(output_path).expanduser().resolve()
        if not source.is_file():
            raise CompilationError("Source must be a regular file.")
        if source == output:
            raise CompilationError("Compiler output must not overwrite its source.")
        artifact_format = (format or source.suffix.lstrip(".")).lower()
        if artifact_format not in self.SUPPORTED_FORMATS:
            raise CompilationError(f"Unsupported artifact format: {artifact_format}")
        source_hash = _digest_file(source)
        manifest_path = self.manifest_path(output)
        cached = self._cached_build(manifest_path, output, source_hash, artifact_format, deduplicate)
        if cached is not None:
            return cached

        source_size = source.stat().st_size
        mappings: list[dict[str, Any]] = []
        seen: dict[str, int] = {}
        records = 0
        if artifact_format == "json":
            try:
                with source.open(encoding="utf-8") as file:
                    value = json.load(file)
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise CompilationError(f"Invalid JSON source: {error}") from error
            records = 1
            self._publish(
                output,
                manifest_path,
                lambda file: json.dump(
                    value, file, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                ),
                {
                    "format": artifact_format,
                    "records": records,
                    "deduplicated": 0,
                    "source_map": [],
                    "deduplicate": False,
                },
                source,
                source_hash,
                source_size,
            )
        else:
            def write_jsonl(file: Any) -> None:
                nonlocal records
                with source.open(encoding="utf-8") as input_file:
                    for line_number, raw_line in enumerate(input_file, 1):
                        if not raw_line.strip():
                            continue
                        try:
                            record = json.loads(raw_line)
                            serialized = json.dumps(
                                record,
                                ensure_ascii=False,
                                separators=(",", ":"),
                                allow_nan=False,
                            )
                        except (json.JSONDecodeError, ValueError) as error:
                            raise CompilationError(
                                f"Invalid JSONL record at line {line_number}: {error}"
                            ) from error
                        record_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
                        previous = seen.get(record_hash) if deduplicate else None
                        if previous is not None:
                            mappings[previous]["source_lines"].append(line_number)
                            continue
                        if records:
                            file.write("\n")
                        file.write(serialized)
                        mappings.append(
                            {"output_line": records + 1, "source_lines": [line_number]}
                        )
                        if deduplicate:
                            seen[record_hash] = records
                        records += 1

            self._publish(
                output,
                manifest_path,
                write_jsonl,
                {
                    "format": artifact_format,
                    "records": records,
                    "deduplicated": 0,
                    "source_map": mappings,
                    "deduplicate": deduplicate,
                },
                source,
                source_hash,
                source_size,
            )
            # The output and manifest now contain the finalized count and source map.
            with manifest_path.open(encoding="utf-8") as file:
                manifest = json.load(file)
            manifest["records"] = records
            manifest["deduplicated"] = len(mappings) and sum(
                len(item["source_lines"]) - 1 for item in mappings
            ) or 0
            _write_atomic(manifest_path, lambda file: json.dump(manifest, file, indent=2))

        with manifest_path.open(encoding="utf-8") as file:
            result = json.load(file)
        result["output_path"] = str(output)
        result["manifest_path"] = str(manifest_path)
        result["cache_hit"] = False
        return result

    def decompile(
        self,
        compiled_path: str | Path,
        output_path: str | Path,
        *,
        restore_source_order: bool = True,
    ) -> DecompilationResult:
        compiled = Path(compiled_path).expanduser().resolve(strict=True)
        output = Path(output_path).expanduser().resolve()
        if compiled == output:
            raise CompilationError("Decompiler output must not overwrite its source.")
        manifest_path = self.manifest_path(compiled)
        try:
            with manifest_path.open(encoding="utf-8") as file:
                manifest = json.load(file)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CompilationError("A valid compilation manifest is required.") from error
        if manifest.get("output_sha256") != _digest_file(compiled):
            raise CompilationError("Compiled artifact does not match its manifest.")
        artifact_format = manifest.get("format")
        if artifact_format not in self.SUPPORTED_FORMATS:
            raise CompilationError("Manifest has an unsupported artifact format.")

        records = 0
        if artifact_format == "json":
            try:
                with compiled.open(encoding="utf-8") as file:
                    value = json.load(file)
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise CompilationError(f"Invalid compiled JSON: {error}") from error

            def write_json(file: Any) -> None:
                json.dump(value, file, ensure_ascii=False, indent=2, allow_nan=False)
                file.write("\n")

            _write_atomic(output, write_json)
            records = 1
        else:
            offsets: dict[int, int] = {}
            try:
                with compiled.open("rb") as file:
                    output_line = 0
                    while True:
                        offset = file.tell()
                        raw_line = file.readline()
                        if not raw_line:
                            break
                        if raw_line.strip():
                            json.loads(raw_line)
                            output_line += 1
                            offsets[output_line] = offset
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                raise CompilationError(f"Invalid compiled JSONL: {error}") from error
            mappings = manifest.get("source_map", [])
            source_records: list[tuple[int, int]] = []
            if restore_source_order and mappings:
                try:
                    for mapping in mappings:
                        output_line = mapping["output_line"]
                        source_lines = mapping["source_lines"]
                        if (
                            not isinstance(output_line, int)
                            or output_line not in offsets
                            or not isinstance(source_lines, list)
                            or not all(isinstance(line, int) and line > 0 for line in source_lines)
                        ):
                            raise CompilationError("Manifest contains an invalid source map.")
                        source_records.extend(
                            (source_line, output_line) for source_line in source_lines
                        )
                except (KeyError, TypeError) as error:
                    raise CompilationError("Manifest contains an invalid source map.") from error
                source_records.sort(key=lambda item: item[0])
            else:
                source_records = [(line, line) for line in offsets]

            def write_jsonl(file: Any) -> None:
                with compiled.open("rb") as input_file:
                    for index, (_, output_line) in enumerate(source_records):
                        if index:
                            file.write("\n")
                        input_file.seek(offsets[output_line])
                        record = json.loads(input_file.readline())
                        json.dump(
                            record,
                            file,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                if source_records:
                    file.write("\n")

            _write_atomic(output, write_jsonl)
            records = len(source_records)

        notes = ["Whitespace and original line endings are not recoverable."]
        if manifest.get("deduplicated"):
            notes.append("Duplicate records were reconstructed from the source map.")
        return DecompilationResult(
            output_path=str(output),
            records=records,
            exact_source_recovered=False,
            notes=tuple(notes),
        )

    @staticmethod
    def manifest_path(output_path: Path) -> Path:
        return output_path.with_name(output_path.name + ".manifest.json")

    def _cached_build(
        self,
        manifest_path: Path,
        output: Path,
        source_hash: str,
        artifact_format: str,
        deduplicate: bool,
    ) -> dict[str, Any] | None:
        try:
            with manifest_path.open(encoding="utf-8") as file:
                manifest = json.load(file)
            previous = output.with_name(output.name + ".previous")
            if (
                (not output.is_file() or manifest.get("output_sha256") != _digest_file(output))
                and previous.is_file()
                and manifest.get("output_sha256") == _digest_file(previous)
            ):
                shutil.copy2(previous, output)
            if (
                output.is_file()
                and manifest.get("source_sha256") == source_hash
                and manifest.get("format") == artifact_format
                and manifest.get("deduplicate") == deduplicate
                and manifest.get("output_sha256") == _digest_file(output)
            ):
                return {
                    **manifest,
                    "output_path": str(output),
                    "manifest_path": str(manifest_path),
                    "cache_hit": True,
                }
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None
        return None

    def _publish(
        self,
        output: Path,
        manifest_path: Path,
        writer: Any,
        metadata: dict[str, Any],
        source: Path,
        source_hash: str,
        source_size: int,
    ) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            previous = output.with_name(output.name + ".previous")
            shutil.copy2(output, previous)
        _write_atomic(output, writer)
        output_size = output.stat().st_size
        manifest = {
            "version": 1,
            "source": source.name,
            "source_sha256": source_hash,
            "output_sha256": _digest_file(output),
            "source_size_bytes": source_size,
            "output_size_bytes": output_size,
            "size_ratio": output_size / source_size if source_size else 1.0,
            **metadata,
        }
        _write_atomic(
            manifest_path,
            lambda file: json.dump(manifest, file, ensure_ascii=False, indent=2),
        )
