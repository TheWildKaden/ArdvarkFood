import json
from pathlib import Path

import pytest

from runtime.compiler import ArtifactCompiler, ArtifactWatcher, CompilationError


def test_json_compile_decompile_preserves_structure_without_overwriting_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    output = tmp_path / "build" / "source.min.json"
    original = '{\n  "list": [1, true, null], "text": "a  b"\n}\n'
    source.write_text(original, encoding="utf-8")

    compiler = ArtifactCompiler()
    result = compiler.compile(source, output)
    restored = tmp_path / "restored.json"
    decoded = compiler.decompile(output, restored)

    assert json.loads(output.read_text(encoding="utf-8")) == json.loads(original)
    assert json.loads(restored.read_text(encoding="utf-8")) == json.loads(original)
    assert source.read_text(encoding="utf-8") == original
    assert result["source_size_bytes"] == len(original.encode("utf-8"))
    assert decoded.exact_source_recovered is False
    assert "Whitespace and original line endings are not recoverable." in decoded.notes


def test_jsonl_deduplication_is_traceable_and_incremental(tmp_path: Path) -> None:
    source = tmp_path / "examples.jsonl"
    output = tmp_path / "compiled.jsonl"
    first = {"messages": [{"role": "user", "content": "hello"}]}
    second = {"messages": [{"role": "user", "content": "world"}]}
    source.write_text(
        "\n".join(
            [
                json.dumps(first),
                json.dumps(second),
                json.dumps(first, indent=2).replace("\n", ""),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    compiler = ArtifactCompiler()

    result = compiler.compile(source, output, deduplicate=True)
    again = compiler.compile(source, output, deduplicate=True)
    restored = tmp_path / "restored.jsonl"
    decoded = compiler.decompile(output, restored)
    records = [
        json.loads(line) for line in restored.read_text(encoding="utf-8").splitlines()
    ]

    assert result["records"] == 2
    assert result["deduplicated"] == 1
    assert again["cache_hit"] is True
    assert records == [first, second, first]
    assert decoded.records == 3
    assert decoded.exact_source_recovered is False


def test_invalid_jsonl_keeps_previous_valid_build_and_reports_line(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    output = tmp_path / "output.jsonl"
    source.write_text('{"value":1}\n', encoding="utf-8")
    compiler = ArtifactCompiler()
    compiler.compile(source, output)
    previous = output.read_text(encoding="utf-8")

    source.write_text('{"value":2}\nnot-json\n', encoding="utf-8")
    with pytest.raises(CompilationError, match="line 2"):
        compiler.compile(source, output)

    assert output.read_text(encoding="utf-8") == previous
    assert output.with_name(output.name + ".previous").read_text(
        encoding="utf-8"
    ) == previous


def test_compiler_rejects_source_overwrite_and_detects_tampering(tmp_path: Path) -> None:
    source = tmp_path / "data.json"
    source.write_text('{"value":1}', encoding="utf-8")
    compiler = ArtifactCompiler()

    with pytest.raises(CompilationError, match="must not overwrite"):
        compiler.compile(source, source)

    output = tmp_path / "compiled.json"
    compiler.compile(source, output)
    output.write_text('{"value":2}', encoding="utf-8")
    with pytest.raises(CompilationError, match="does not match"):
        compiler.decompile(output, tmp_path / "restored.json")


def test_watcher_builds_only_changed_files_and_refuses_overlapping_output(
    tmp_path: Path,
) -> None:
    source_directory = tmp_path / "sources"
    output_directory = tmp_path / "output"
    source_directory.mkdir()
    source = source_directory / "small.json"
    source.write_text('{"value":1}', encoding="utf-8")
    watcher = ArtifactWatcher([source_directory], output_directory)

    first = watcher.scan_once()
    second = watcher.scan_once()
    source.write_text('{"value":2}', encoding="utf-8")
    third = watcher.scan_once()

    assert len(first) == 1
    assert second == []
    assert len(third) == 1
    assert json.loads(
        (output_directory / "small.json.min.json").read_text(encoding="utf-8")
    ) == {"value": 2}
    with pytest.raises(ValueError, match="must not overlap"):
        ArtifactWatcher([source_directory], source_directory / "compiled")
