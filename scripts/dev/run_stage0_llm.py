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

    from nic_agent.chat import OllamaChatClient, OpenAICompatChatClient
    from nic_agent.executor import ActionExecutor
    from nic_agent.headless_backend import HeadlessBackend
    from nic_agent.loop import AgentLoop
    from nic_agent.planner import LLMPolicy
    from nic_agent.session_log import SessionLogger

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
    width, height = int(width_text), int(height_text)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.client == "ollama":
        client = OllamaChatClient(base_url=args.base_url, model=args.model)
    else:
        base_url = args.base_url
        if not base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
        client = OpenAICompatChatClient(
            base_url=base_url,
            model=args.model,
            api_key=args.api_key or None,
        )
    executor = ActionExecutor(HeadlessBackend(output_root=args.output_dir))
    image_provider = None if args.no_vision else lambda: executor.backend.canvas_png_base64()
    goal_with_canvas = (
        f"{args.goal}\nThe first action must be a create_document of exactly {width}x{height}."
    )
    policy = LLMPolicy(
        client,
        goal=goal_with_canvas,
        max_blocks=args.max_blocks,
        image_provider=image_provider,
        suppress_thinking=args.client == "ollama",
    )
    log_path = args.output_dir / "session.jsonl"

    with SessionLogger(log_path) as logger:
        summary = AgentLoop(executor, logger).run(policy)

    exported = sorted(path.name for path in args.output_dir.glob("*.png"))
    print(
        json.dumps(
            {
                "goal": args.goal,
                "steps": summary.steps,
                "ok": summary.ok,
                "stop_reason": summary.stop_reason,
                "fingerprint": summary.fingerprint,
                "blocks_used": policy.blocks_used,
                "exported_png": exported,
                "session_log": str(log_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    feedback = list(policy.last_feedback)
    if feedback:
        print("Last feedback:", json.dumps(feedback, ensure_ascii=False))
    return 0 if summary.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
