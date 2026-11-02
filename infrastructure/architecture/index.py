from __future__ import annotations

import ast
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


IGNORED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
}
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".mjs", ".ts", ".tsx"}


@dataclass
class PythonModule:
    path: Path
    tree: ast.Module
    imports: list[str] = field(default_factory=list)


@dataclass
class SourceIndex:
    root: Path
    python_modules: dict[Path, PythonModule]
    javascript_modules: list[dict[str, Any]]
    parse_errors: list[str]

    @classmethod
    def build(cls, root: Path) -> "SourceIndex":
        python_modules: dict[Path, PythonModule] = {}
        javascript_paths: list[Path] = []
        parse_errors: list[str] = []
        for current, directories, filenames in os.walk(root):
            current_path = Path(current)
            relative_directory = current_path.relative_to(root)
            directories.sort()
            directories[:] = [
                directory
                for directory in directories
                if directory not in IGNORED_PARTS
            ]
            for filename in sorted(filenames):
                path = current_path / filename
                if path.suffix not in SOURCE_SUFFIXES:
                    continue
                relative = path.relative_to(root)
                if "tests" in relative.parts or path.name.startswith("test_"):
                    continue
                if path.suffix == ".py":
                    try:
                        text = path.read_text(encoding="utf-8")
                        python_modules[path] = PythonModule(
                            path,
                            ast.parse(text, filename=str(path)),
                        )
                    except (OSError, UnicodeError, SyntaxError) as error:
                        parse_errors.append(f"{relative}: {error}")
                else:
                    javascript_paths.append(path)
        javascript_paths.sort()

        js_indexer = root / "infrastructure" / "architecture" / "js_indexer.mjs"
        javascript_modules: list[dict[str, Any]] = []
        if javascript_paths:
            try:
                result = subprocess.run(
                    ["node", str(js_indexer)],
                    input=json.dumps([str(path) for path in javascript_paths]),
                    text=True,
                    capture_output=True,
                    check=True,
                    cwd=root,
                )
                javascript_modules = json.loads(result.stdout)
                parse_errors.extend(
                    f"{Path(item['path']).relative_to(root)}: {item['error']}"
                    for item in javascript_modules
                    if "error" in item
                )
                javascript_modules = [
                    item for item in javascript_modules if "error" not in item
                ]
            except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
                detail = getattr(error, "stderr", None) or str(error)
                parse_errors.append(f"JavaScript parser failed: {detail}")

        if parse_errors:
            details = "\n".join(f"- {item}" for item in parse_errors)
            raise ValueError(f"Source analysis could not parse all source files:\n{details}")
        return cls(root, python_modules, javascript_modules, parse_errors)

    def relative(self, path: Path | str) -> str:
        return Path(path).resolve().relative_to(self.root.resolve()).as_posix()

    def python_symbols(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        functions: list[dict[str, Any]] = []
        classes: list[dict[str, Any]] = []
        for path, module in self.python_modules.items():
            module_name = self.module_name(path)
            class_attributes: dict[str, dict[str, str]] = {}
            for node in ast.walk(module.tree):
                if isinstance(node, ast.ClassDef):
                    class_attributes[node.name] = {}
                    for child in ast.walk(node):
                        if not isinstance(child, (ast.Assign, ast.AnnAssign)):
                            continue
                        targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                        value = child.value
                        if not isinstance(value, ast.Call):
                            class_name = None
                        else:
                            class_name = (
                                value.func.id
                                if isinstance(value.func, ast.Name)
                                else None
                            )
                        for target in targets:
                            if (
                                isinstance(target, ast.Attribute)
                                and isinstance(target.value, ast.Name)
                                and target.value.id == "self"
                            ):
                                if class_name:
                                    class_attributes[node.name][target.attr] = class_name
                                elif isinstance(child, ast.AnnAssign):
                                    annotation = child.annotation
                                    if isinstance(annotation, ast.Name):
                                        class_attributes[node.name][target.attr] = annotation.id
                    init = next(
                        (
                            item
                            for item in node.body
                            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                            and item.name == "__init__"
                        ),
                        None,
                    )
                    if init:
                        for argument in init.args.args:
                            if argument.arg == "self" or argument.annotation is None:
                                continue
                            if isinstance(argument.annotation, ast.Name):
                                class_attributes[node.name][argument.arg] = (
                                    argument.annotation.id
                                )
                    classes.append(
                        {
                            "name": node.name,
                            "qualname": f"{module_name}.{node.name}",
                            "path": self.relative(path),
                            "line": node.lineno,
                            "bases": [self._name(base) for base in node.bases],
                            "language": "Python",
                            "confidence": "detected (Python AST)",
                        }
                    )

            for node in ast.walk(module.tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                owner = self._enclosing_class(module.tree, node)
                calls = []
                for call in (item for item in ast.walk(node) if isinstance(item, ast.Call)):
                    expression = ast.unparse(call.func)
                    target = self._resolve_self_call(
                        expression,
                        owner,
                        class_attributes.get(owner or "", {}),
                    )
                    calls.append(
                        {
                            "expression": expression,
                            "name": self._name(call.func),
                            "line": call.lineno,
                            "target": target,
                        }
                    )
                functions.append(
                    {
                        "name": node.name,
                        "qualname": (
                            f"{module_name}.{owner}.{node.name}"
                            if owner
                            else f"{module_name}.{node.name}"
                        ),
                        "owner": owner,
                        "path": self.relative(path),
                        "line": node.lineno,
                        "calls": calls,
                        "language": "Python",
                        "confidence": "detected (Python AST)",
                    }
                )
        return functions, classes

    def module_name(self, path: Path) -> str:
        parts = list(path.relative_to(self.root).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts)

    @staticmethod
    def _name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return SourceIndex._name(node.value) + "." + node.attr
        if isinstance(node, ast.Call):
            return SourceIndex._name(node.func)
        if isinstance(node, ast.Subscript):
            return SourceIndex._name(node.value)
        if isinstance(node, ast.Constant):
            return str(node.value)
        return ast.unparse(node)

    @staticmethod
    def _enclosing_class(tree: ast.Module, target: ast.AST) -> str | None:
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and target in node.body:
                return node.name
            if isinstance(node, ast.ClassDef) and any(
                child is target for child in ast.walk(node)
            ):
                return node.name
        return None

    @staticmethod
    def _resolve_self_call(
        expression: str,
        owner: str | None,
        class_attributes: dict[str, str],
    ) -> str | None:
        if not owner or not expression.startswith("self."):
            return None
        parts = expression.split(".")
        if len(parts) == 2:
            return f"{owner}.{parts[1]}"
        if len(parts) == 3 and parts[1] in class_attributes:
            return f"{class_attributes[parts[1]]}.{parts[2]}"
        return None
