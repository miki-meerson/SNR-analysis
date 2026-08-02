from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import TRACE_TYPES


IGNORED_FOLDER_ITEMS = {".DS_Store", "Thumbs.db"}


def is_experiment_folder(path: Path) -> bool:
    return any((path / trace_type.relative_dir).is_dir() for trace_type in TRACE_TYPES)


def browse_folder(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")
    if not path.is_dir():
        raise ValueError(f"Path is not a folder: {path}")

    children = []
    for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        if child.name in IGNORED_FOLDER_ITEMS or not child.is_dir():
            continue
        children.append(
            {
                "name": child.name,
                "path": str(child),
                "has_traces": is_experiment_folder(child),
            }
        )

    return {
        "path": str(path),
        "parent": str(path.parent) if path.parent != path else None,
        "children": children,
        "is_experiment": is_experiment_folder(path),
    }

