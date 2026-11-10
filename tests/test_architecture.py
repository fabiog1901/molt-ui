"""Protect the boundaries that keep process, storage, and frontend code separate."""

import ast
from pathlib import Path


def test_external_io_imports_are_confined_to_their_adapters():
    root = Path(__file__).parents[1] / "src/molt_ui"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            if any(
                module == "subprocess" or module.startswith("subprocess.")
                for module in modules
            ):
                assert path == root / "molt_process.py"
            if any(
                module == "sqlite3" or module.startswith("sqlite3.")
                for module in modules
            ):
                assert path == root / "repo/repo.py"
        if path.is_relative_to(root / "frontends"):
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in {
                    "jobs",
                    "history",
                    "_runs",
                    "_repo",
                    "_process",
                }:
                    assert not (
                        isinstance(node.value, ast.Name) and node.value.id == "service"
                    )
                    assert not (
                        isinstance(node.value, ast.Attribute)
                        and node.value.attr == "service"
                    )
        if path.is_relative_to(root / "core"):
            assert "molt_ui.frontends" not in path.read_text()
