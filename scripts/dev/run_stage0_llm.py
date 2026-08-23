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
) -> dict:
    from nic_agent.chat import OllamaChatClient, OpenAICompatChatClient
    from nic_agent.executor import ActionExecutor
    from nic_agent.headless_backend import HeadlessBackend
    from nic_agent.loop import AgentLoop
    from nic_agent.planner import LLMPolicy
    from nic_agent.session_log import SessionLogger

    output_dir.mkdir(parents=True, exist_ok=True)
    if client == "ollama":
        chat_client = OllamaChatClient(base_url=base_url, model=model)
    else:
        resolved_base_url = base_url
        if not resolved_base_url.rstrip("/").endswith("/v1"):
            resolved_base_url = resolved_base_url.rstrip("/") + "/v1"
        chat_client = OpenAICompatChatClient(
            base_url=resolved_base_url,
            model=model,
            api_key=api_key or None,
        )
    executor = ActionExecutor(HeadlessBackend(output_root=output_dir))
    image_provider = executor.backend.canvas_png_base64 if attach_vision else None
    goal_with_canvas = (
        f"{goal}\nThe first action must be a create_document of exactly {width}x{height}."
    )
    policy = LLMPolicy(
        chat_client,
        goal=goal_with_canvas,
        max_blocks=max_blocks,
        image_provider=image_provider,
        suppress_thinking=client == "ollama",
    )
    log_path = output_dir / "session.jsonl"

    with SessionLogger(log_path) as logger:
        loop_summary = AgentLoop(executor, logger).run(policy)

    exported = sorted(path.name for path in output_dir.glob("*.png"))
    summary = {
        "steps": loop_summary.steps,
        "ok": loop_summary.ok,
        "stop_reason": loop_summary.stop_reason,
        "fingerprint": loop_summary.fingerprint,
        "blocks_used": policy.blocks_used,
        "exported_png": exported,
        "session_log": str(log_path),
        "last_feedback": list(policy.last_feedback),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    raise SystemExit(main())
