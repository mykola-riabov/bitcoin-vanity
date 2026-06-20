"""Tests for workspace path layout."""

from pathlib import Path

from workspace import (
    CACHE_FILE_NAME,
    FOUND_DIR_NAME,
    GENERATED_DIR_NAME,
    GENERATED_FILE_NAME,
    ensure_workspace,
    workspace_layout,
)


def test_workspace_layout_paths(tmp_path: Path) -> None:
    layout = workspace_layout(tmp_path / "my-wallets")
    assert layout.generated_dir == layout.root / GENERATED_DIR_NAME
    assert layout.generated_file.name == GENERATED_FILE_NAME
    assert layout.found_dir == layout.root / FOUND_DIR_NAME
    assert layout.cache_file == layout.root / CACHE_FILE_NAME


def test_ensure_workspace_creates_dirs(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    layout = ensure_workspace(root)
    assert layout.generated_dir.is_dir()
    assert layout.found_dir.is_dir()
