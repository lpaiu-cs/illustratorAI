from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    parser = argparse.ArgumentParser(description="Run a Stage 0 LLM drawing session (headless)")
    parser.add_argument("--goal", required=True, help="Natural language drawing goal")
    parser.add_argument("--canvas", default="128x128", help="WxH, e.g. 128x128")
    parser.add_argument("--output-dir", type=Path, default=repo_root / "output" / "stage0_llm")
    parser.add_argument("--max-blocks", type=int, default=16)
    parser.add_argument(
        "--client",
        choices=["ollama", "openai"],
        default="ollama",
        help="Chat client backend (default ollama native API)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("NIC_LLM_BASE_URL", "http://127.0.0.1:11434"),
        help="Endpoint base URL (default env NIC_LLM_BASE_URL)",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("NIC_LLM_MODEL", ""),
        help="Model name (default env NIC_LLM_MODEL)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("NIC_LLM_API_KEY", ""),
        help="API key (default env NIC_LLM_API_KEY)",
    )
    parser.add_argument("--no-vision", action="store_true", help="Disable canvas image attachment")
    parser.add_argument("--temperature", type=float, default=None, help="Override sampling temperature (default client value)")
    parser.add_argument(
        "--repair-rounds",
        type=int,
        default=1,
        help="Targeted repair re-requests after a failed session (0 disables)",
    )
    parser.add_argument(
        "--image-history",
        type=int,
        default=None,
        help="Keep only the last N canvas images in context (older ones become text). Default: keep all",
    )
    parser.add_argument(
        "--history-turns",
        type=int,
        default=None,
        help="Trim conversation to the last N user/assistant turn pairs. Default: 12",
    )
    args = parser.parse_args()

    if not args.model:
        parser.error("--model or NIC_LLM_MODEL is required")

    width_text, height_text = args.canvas.lower().split("x", 1)

    summary = run_single_session(
        args.goal,
        model=args.model,
        client=args.client,
        base_url=args.base_url,
        api_key=args.api_key,
        width=int(width_text),
        height=int(height_text),
        max_blocks=args.max_blocks,
        output_dir=args.output_dir,
        attach_vision=not args.no_vision,
        temperature=args.temperature,
        repair_rounds=args.repair_rounds,
        image_history=args.image_history,
        history_turns=args.history_turns,
    )

    print(json.dumps({"goal": args.goal, **summary}, ensure_ascii=False, indent=2))
    if summary["last_feedback"]:
        print("Last feedback:", json.dumps(summary["last_feedback"], ensure_ascii=False))
    return 0 if summary["ok"] else 1


def run_single_session(
    goal: str,
    *,
    model: str,
    client: str = "ollama",
    base_url: str = "http://127.0.0.1:11434",
    api_key: str = "",
    width: int = 128,
    height: int = 128,
    max_blocks: int = 16,
    output_dir: Path,
    attach_vision: bool = True,
    temperature: float | None = None,
    repair_rounds: int = 1,
    repair_extra_blocks: int = 4,
    image_history: int | None = None,
    history_turns: int | None = None,
    structured: bool = True,
) -> dict:
    from nic_agent.chat import OllamaChatClient, OpenAICompatChatClient
    from nic_agent.executor import ActionExecutor
    from nic_agent.headless_backend import HeadlessBackend
    from nic_agent.loop import AgentLoop
    from nic_agent.planner import LLMPolicy
    from nic_agent.session_log import SessionLogger
    from nic_agent.stage0 import ACTION_BLOCK_SCHEMA, build_repair_message, classify_failure

    output_dir.mkdir(parents=True, exist_ok=True)
    client_kwargs = {} if temperature is None else {"temperature": temperature}
    if client == "ollama":
        if structured:
            client_kwargs["format_schema"] = ACTION_BLOCK_SCHEMA
        chat_client = OllamaChatClient(base_url=base_url, model=model, **client_kwargs)
    else:
        resolved_base_url = base_url
        if not resolved_base_url.rstrip("/").endswith("/v1"):
            resolved_base_url = resolved_base_url.rstrip("/") + "/v1"
        chat_client = OpenAICompatChatClient(
            base_url=resolved_base_url,
            model=model,
            api_key=api_key or None,
            **client_kwargs,
        )
    executor = ActionExecutor(HeadlessBackend(output_root=output_dir))
    image_provider = executor.backend.canvas_png_base64 if attach_vision else None
    goal_with_canvas = (
        f"{goal}\nThe first action must be a create_document of exactly {width}x{height}."
    )
    policy_kwargs = {}
    if history_turns is not None:
        policy_kwargs["history_turns"] = history_turns
    policy = LLMPolicy(
        chat_client,
        goal=goal_with_canvas,
        max_blocks=max_blocks,
        image_provider=image_provider,
        suppress_thinking=client == "ollama",
        image_history_limit=image_history,
        **policy_kwargs,
    )
    log_path = output_dir / "session.jsonl"

    def session_exports() -> list[str]:
        # Only this session's exports count: a reused output_dir (e.g. a --resume
        # retry) may still hold PNGs from an earlier attempt.
        return sorted(set(executor.backend.exported))

    total_steps = 0
    repairs: list[dict] = []
    failure_classes: list[str] = []
    with SessionLogger(log_path) as logger:
        loop_summary = AgentLoop(executor, logger).run(policy)
        total_steps += loop_summary.steps
        for round_index in range(max(0, repair_rounds)):
            current = {
                "ok": loop_summary.ok,
                "stop_reason": loop_summary.stop_reason,
                "exported_png": session_exports(),
                "last_feedback": list(policy.last_feedback),
            }
            observation = executor.observe()
            classes = classify_failure(current, observation)
            failure_classes = classes
            if not classes:
                break
            logger.log_repair({"round": round_index + 1, "failure_classes": list(classes)})
            policy.resume_with_repair(
                build_repair_message(classes), extra_blocks=repair_extra_blocks
            )
            loop_summary = AgentLoop(executor, logger).run(policy)
            total_steps += loop_summary.steps
            repairs.append({"round": round_index + 1, "failure_classes": list(classes)})

    exported = session_exports()
    failure_classes = classify_failure(
        {
            "ok": loop_summary.ok,
            "stop_reason": loop_summary.stop_reason,
            "exported_png": exported,
            "last_feedback": list(policy.last_feedback),
        },
        executor.observe(),
    )
    conversation_path = output_dir / "conversation.jsonl"
    with conversation_path.open("w", encoding="utf-8") as stream:
        for message in policy.conversation():
            stream.write(json.dumps(message, ensure_ascii=False) + "\n")
    summary = {
        "steps": total_steps,
        "ok": loop_summary.ok,
        "stop_reason": loop_summary.stop_reason,
        "fingerprint": loop_summary.fingerprint,
        "blocks_used": policy.blocks_used,
        "exported_png": exported,
        "session_log": str(log_path),
        "last_feedback": list(policy.last_feedback),
        "failure_classes": failure_classes,
        "repair_rounds_used": len(repairs),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    raise SystemExit(main())
