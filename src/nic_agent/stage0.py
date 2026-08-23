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
            try:
                summary = runner(index, goal)
            except Exception as exc:  # noqa: BLE001
                summary = {
                    "steps": 0,
                    "ok": False,
                    "stop_reason": "runner_error",
                    "fingerprint": None,
                    "blocks_used": 0,
                    "exported_png": [],
                    "session_log": "",
                    "last_feedback": [],
                    "failure_classes": ["runner_error"],
                    "repair_rounds_used": 0,
                    "error": str(exc),
                }
                log(f"[{index:04d}] runner_error: {str(exc)[:120]}")
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


def validate_sft_sample(sample: dict[str, Any]) -> list[str]:
    from nic_agent.planner import extract_json_object

    issues: list[str] = []
    messages = sample.get("messages")
    if not isinstance(messages, list) or not messages:
        return ["missing messages"]
    last = messages[-1]
    if last.get("role") != "assistant":
        issues.append("last message is not assistant")
        return issues
    content = last.get("content")
    if not isinstance(content, str) or not content.strip():
        issues.append("empty assistant content")
        return issues
    try:
        parsed = extract_json_object(content)
    except ValueError as exc:
        issues.append(f"unparseable assistant content: {exc}")
        return issues
    if not isinstance(parsed.get("actions"), list):
        issues.append("actions is not a list")
    if not isinstance(parsed.get("done"), bool):
        issues.append("done is not a boolean")
    return issues


def replay_fingerprint(actions: list[dict[str, Any]]) -> str | None:
    from nic_agent.executor import ActionExecutor
    from nic_agent.headless_backend import HeadlessBackend

    executor = ActionExecutor(HeadlessBackend(output_root=None))
    for action in actions:
        if action.get("type") == "export_png":
            continue
        executor.apply(action)
    return executor.fingerprint()


JUDGE_SYSTEM_PROMPT = (
    "You are a strict art judge for an agentic drawing system."
    " You get a drawing GOAL (text) and a RENDERED CANVAS image."
    " Compare them carefully and respond with exactly one JSON object and nothing else:"
    ' {"match": true or false, "score": integer 0-10,'
    ' "missing": ["elements from the goal absent in the image"],'
    ' "reasoning": "one short sentence"} .'
    " Rules: match=true only if the main subject, its arrangement and colors"
    " clearly satisfy the goal. Minor stylistic imperfections still count as match=true."
)


def normalize_session_path(path: str | Path) -> str:
    return str(Path(path).resolve()).lower()


def load_quality_passes(
    quality_files: list[Path], min_score: int
) -> dict[str, dict[str, Any]]:
    passes: dict[str, dict[str, Any]] = {}
    for quality_path in quality_files:
        if not quality_path.exists():
            continue
        for line in quality_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            key = normalize_session_path(record["session_log"])
            if record.get("match") and int(record.get("score", 0)) >= min_score:
                passes[key] = record
    return passes


def build_judge_messages(goal: str, png_base64: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT + " /no_think"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"GOAL: {goal}\n\nJudge the attached canvas render."},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{png_base64}"},
                },
            ],
        },
    ]


def parse_judgement(text: str) -> dict[str, Any] | None:
    from nic_agent.planner import extract_json_object

    try:
        parsed = extract_json_object(text)
    except ValueError:
        return None
    match = parsed.get("match")
    score = parsed.get("score")
    if not isinstance(match, bool):
        return None
    try:
        score_int = max(0, min(10, int(score)))
    except (TypeError, ValueError):
        return None
    return {
        "match": match,
        "score": score_int,
        "missing": parsed.get("missing") if isinstance(parsed.get("missing"), list) else [],
        "reasoning": str(parsed.get("reasoning", "")),
    }


def _template_token_ids(tokenizer: Any, messages: list[dict[str, Any]], add_generation_prompt: bool) -> list[int]:
    rendered = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=add_generation_prompt
    )
    if hasattr(rendered, "keys") and "input_ids" in rendered:
        rendered = rendered["input_ids"]
    elif hasattr(rendered, "input_ids"):
        rendered = rendered.input_ids
    if rendered and isinstance(rendered[0], (list, tuple)):
        rendered = rendered[0]
    return [int(token) for token in rendered]


def build_sft_training_pair(
    tokenizer: Any,
    messages: list[dict[str, Any]],
    max_len: int = 2048,
) -> dict[str, list[int]]:
    """Tokenize one conversation sample with loss only on the final assistant turn."""
    if not messages or messages[-1].get("role") != "assistant":
        raise ValueError("sample must end with an assistant message")
    prompt_ids = _template_token_ids(tokenizer, messages[:-1], add_generation_prompt=True)
    full_ids = _template_token_ids(tokenizer, messages, add_generation_prompt=False)
    common = 0
    limit = min(len(prompt_ids), len(full_ids))
    while common < limit and prompt_ids[common] == full_ids[common]:
        common += 1
    drop = max(0, len(full_ids) - max_len)
    input_ids = full_ids[drop:]
    kept_common = max(0, common - drop)
    labels = [-100] * kept_common + input_ids[kept_common:]
    return {"input_ids": input_ids, "labels": labels}
