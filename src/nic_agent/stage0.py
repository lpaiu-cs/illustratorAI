from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

Runner = Callable[[int, str], dict[str, Any]]
LogFn = Callable[[str], None]

ACTION_BLOCK_SCHEMA = {
    "type": "object",
    "properties": {
        "thought": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "create_document",
                            "create_layer",
                            "select_layer",
                            "fill_rect",
                            "stroke",
                            "add_svg",
                            "set_layer_properties",
                            "export_png",
                            "finish",
                        ],
                    },
                    "payload": {"type": "object"},
                },
                "required": ["type"],
            },
        },
        "done": {"type": "boolean"},
    },
    "required": ["thought", "actions", "done"],
}

SUMMARY_KEYS = (
    "steps",
    "ok",
    "stop_reason",
    "fingerprint",
    "blocks_used",
    "exported_png",
    "session_log",
    "failure_classes",
    "repair_rounds_used",
)

REPAIR_HINTS = {
    "no_document": "No document exists yet. Your next response must start with create_document.",
    "invalid_response": "Your previous response was not usable. Reply with exactly one JSON object per the format.",
    "export_missing": "No PNG has been exported yet. Call export_png with a simple file_name now.",
    "done_missing": (
        'The image has already been exported. Respond with {"thought": "...", '
        '"actions": [], "done": true}. Do not draw anything more.'
    ),
    "action_failures": "Recent actions kept failing. Read the layer list and fix only the failing step.",
}


def classify_failure(summary: dict[str, Any], observation: dict[str, Any]) -> list[str]:
    if (
        summary.get("ok")
        and summary.get("stop_reason") == "finish"
        and summary.get("exported_png")
    ):
        return []
    if not observation.get("canvas"):
        return ["no_document"]
    classes: list[str] = []
    if not summary.get("ok"):
        classes.append("action_failures")
    if summary.get("last_feedback"):
        classes.append("invalid_response")
    if not summary.get("exported_png"):
        classes.append("export_missing")
    else:
        classes.append("done_missing")
    return classes


def build_repair_message(classes: list[str]) -> str:
    lines = [
        "REPAIR ROUND: your previous run ended before completing the goal."
        " Automated checks found these gaps:"
    ]
    for name in classes:
        lines.append(f"- {name}: {REPAIR_HINTS[name]}")
    lines.append(
        'Close these gaps now. Respond with exactly one JSON block: '
        '{"thought": "...", "actions": [...], "done": false} (or done=true).'
    )
    return "\n".join(lines)


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


def extract_sft_samples(
    conversation: list[dict[str, Any]], meta: dict[str, Any]
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    context: list[dict[str, Any]] = []
    for message in conversation:
        context.append(dict(message))
        if message.get("role") == "assistant":
            samples.append(
                {
                    "goal": meta["goal"],
                    "source_index": meta.get("index"),
                    "used_repair": bool(meta.get("repair_rounds_used")),
                    "turn": len(samples) + 1,
                    "messages": [dict(item) for item in context],
                }
            )
    return samples
