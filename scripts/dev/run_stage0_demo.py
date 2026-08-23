from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    from nic_agent.executor import ActionExecutor
    from nic_agent.headless_backend import HeadlessBackend
    from nic_agent.loop import AgentLoop
    from nic_agent.policy import ScriptedPolicy
    from nic_agent.session_log import SessionLogger

    parser = argparse.ArgumentParser(description="Run the Stage 0 scripted closed-loop demo")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "output" / "stage0",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    executor = ActionExecutor(HeadlessBackend(output_root=args.output_dir))
    log_path = args.output_dir / "session.jsonl"
    with SessionLogger(log_path) as logger:
        loop = AgentLoop(executor, logger)
        summary = loop.run(ScriptedPolicy(build_demo_actions()))

    png_path = args.output_dir / "stage0_demo.png"
    print(
        json.dumps(
            {
                "steps": summary.steps,
                "ok": summary.ok,
                "stop_reason": summary.stop_reason,
                "fingerprint": summary.fingerprint,
                "session_log": str(log_path),
                "png": str(png_path) if png_path.exists() else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if summary.ok else 1


def circle_points(
    cx: float, cy: float, radius: float, segments: int = 48
) -> list[list[int]]:
    return [
        [
            int(round(cx + radius * math.cos(2 * math.pi * index / segments))),
            int(round(cy + radius * math.sin(2 * math.pi * index / segments))),
        ]
        for index in range(segments + 1)
    ]


def arc_points(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    start_degrees: float,
    end_degrees: float,
    segments: int = 24,
) -> list[list[int]]:
    return [
        [
            int(round(cx + rx * math.cos(math.radians(start_degrees + step)))),
            int(round(cy + ry * math.sin(math.radians(start_degrees + step)))),
        ]
        for step in [
            (end_degrees - start_degrees) * index / segments for index in range(segments + 1)
        ]
    ]


def build_demo_actions() -> list[dict[str, object]]:
    return [
        {
            "type": "create_document",
            "payload": {
                "width": 256,
                "height": 256,
                "background_color": "#FFFFFFFF",
                "file_name": "stage0_demo",
            },
        },
        {
            "type": "create_layer",
            "payload": {"layer_id": "face", "name": "Face", "kind": "paint"},
        },
        {
            "type": "stroke",
            "payload": {
                "points": circle_points(128, 128, 80),
                "color": "#202020FF",
                "size": 6,
            },
        },
        {
            "type": "stroke",
            "payload": {"points": [[98, 104], [112, 118]], "color": "#202020FF", "size": 5},
        },
        {
            "type": "stroke",
            "payload": {"points": [[158, 104], [144, 118]], "color": "#202020FF", "size": 5},
        },
        {
            "type": "stroke",
            "payload": {
                "points": arc_points(128, 132, 46, 32, 25, 155),
                "color": "#202020FF",
                "size": 5,
            },
        },
        {"type": "export_png", "payload": {"file_name": "stage0_demo.png"}},
        {"type": "finish"},
    ]


if __name__ == "__main__":
    raise SystemExit(main())
