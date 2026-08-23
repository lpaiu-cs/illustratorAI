from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

Runner = Callable[[int, str], dict[str, Any]]
LogFn = Callable[[str], None]

SUMMARY_KEYS = (
    "steps",
    "ok",
    "stop_reason",
    "fingerprint",
    "blocks_used",
    "exported_png",
    "session_log",
)


def load_goals(path: Path) -> list[str]:
    goals: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        goals.append(line)
    return goals


def is_collection_success(summary: dict[str, Any]) -> bool:
    return bool(
        summary.get("ok")
        and summary.get("stop_reason") == "finish"
        and summary.get("exported_png")
    )


def build_manifest_entry(index: int, goal: str, summary: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "index": index,
        "goal": goal,
        "success": is_collection_success(summary),
    }
    for key in SUMMARY_KEYS:
        entry[key] = summary.get(key)
    return entry


def read_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    if not manifest_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for raw_line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        entries.append(json.loads(line))
    return entries


def run_batch(
    goals: list[str],
    runner: Runner,
    *,
    manifest_path: Path,
    resume: bool = False,
    log: LogFn = print,
) -> list[dict[str, Any]]:
    succeeded: set[int] = {
        entry["index"]
        for entry in read_manifest(manifest_path)
        if entry.get("success")
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as stream:
        for index, goal in enumerate(goals):
            if resume and index in succeeded:
                log(f"[{index:04d}] skip (already succeeded)")
                continue
            summary = runner(index, goal)
            entry = build_manifest_entry(index, goal, summary)
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
            stream.flush()
            status = "ok" if entry["success"] else "FAIL"
            log(
                f"[{index:04d}] {status} steps={entry['steps']} "
                f"stop={entry['stop_reason']} blocks={entry['blocks_used']}"
            )
    return read_manifest(manifest_path)


def summarize_batch(entries: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(entries),
        "succeeded": sum(1 for entry in entries if entry["success"]),
        "failed": sum(1 for entry in entries if not entry["success"]),
    }
