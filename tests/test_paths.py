from __future__ import annotations

from app.paths import ensure_runtime_files, is_frozen, user_dir


def test_dev_paths() -> None:
    assert is_frozen() is False
    root = ensure_runtime_files()
    assert root == user_dir()
    assert (root / "config" / "symbols.yaml").exists()
