from __future__ import annotations

import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path


PLUGIN_NAME = "native_illustration_compiler"


def bootstrap_plugin(entry_file: str | Path) -> dict[str, str]:
    entry_path = Path(entry_file).resolve()
    project_root = _discover_project_root(entry_path)
    src_root = project_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    return {
        "entry_file": str(entry_path),
        "project_root": str(project_root),
        "src_root": str(src_root),
        "examples_root": str(project_root / "examples"),
        "assets_root": str(project_root / "examples" / "assets"),
        "bootstrap_log": str(bootstrap_log_path()),
    }


def bootstrap_log_path() -> Path:
    return Path(tempfile.gettempdir()) / PLUGIN_NAME / "bootstrap.log"


def append_bootstrap_log(message: str, exc: BaseException | None = None) -> Path:
    log_path = bootstrap_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    chunks = [f"[{timestamp}] {message}\n"]
    if exc is not None:
        chunks.append("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        chunks.append("\n")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write("".join(chunks))
    return log_path


def _discover_project_root(entry_path: Path) -> Path:
    current = entry_path.parent
    for candidate in [current, *current.parents]:
        if _looks_like_project_root(candidate):
            return candidate
    raise RuntimeError(f"Could not find project root for {entry_path}")


def _looks_like_project_root(candidate: Path) -> bool:
    return (
        (candidate / "pyproject.toml").is_file()
        and (candidate / "src" / "nic_compiler").is_dir()
        and (candidate / "src" / "nic_ir").is_dir()
        and (candidate / "examples").is_dir()
        and (candidate / "pykrita" / PLUGIN_NAME).is_dir()
    )

