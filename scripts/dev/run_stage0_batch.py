from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nic_agent.stage0 import load_goals, run_batch, summarize_batch  # noqa: E402


def main() -> int:
    default_root = REPO_ROOT / "output" / "stage0_batch" / time.strftime("run_%Y%m%d_%H%M%S")
    parser = argparse.ArgumentParser(description="Run Stage 0 batch collection (headless)")
    parser.add_argument("--goals-file", type=Path, required=True, help="Text file, one goal per line (# comments allowed)")
    parser.add_argument("--canvas", default="64x64", help="WxH, e.g. 64x64")
    parser.add_argument("--max-blocks", type=int, default=10)
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
    parser.add_argument("--output-root", type=Path, default=default_root)
    parser.add_argument("--limit", type=int, default=None, help="Only run the first N goals")
    parser.add_argument("--no-vision", action="store_true", help="Disable canvas image attachment")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip goals already marked successful in the existing manifest",
    )
    args = parser.parse_args()

    if not args.model:
        parser.error("--model or NIC_LLM_MODEL is required")

    from run_stage0_llm import run_single_session

    goals = load_goals(args.goals_file)
    if not goals:
        parser.error(f"no goals found in {args.goals_file}")
    if args.limit is not None:
        goals = goals[: args.limit]

    width_text, height_text = args.canvas.lower().split("x", 1)
    width, height = int(width_text), int(height_text)

    def runner(index: int, goal: str) -> dict:
        output_dir = args.output_root / f"goal_{index:04d}"
        return run_single_session(
            goal,
            model=args.model,
            client=args.client,
            base_url=args.base_url,
            api_key=args.api_key,
            width=width,
            height=height,
            max_blocks=args.max_blocks,
            output_dir=output_dir,
            attach_vision=not args.no_vision,
        )

    manifest_path = args.output_root / "manifest.jsonl"
    entries = run_batch(goals, runner, manifest_path=manifest_path, resume=args.resume)
    totals = summarize_batch(entries)

    print(
        json.dumps(
            {
                "model": args.model,
                "goals_file": str(args.goals_file),
                "output_root": str(args.output_root),
                "manifest": str(manifest_path),
                **totals,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
