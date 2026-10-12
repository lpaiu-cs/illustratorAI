from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nic_agent.chat import OllamaChatClient  # noqa: E402
from nic_agent.stage0 import (  # noqa: E402
    build_judge_messages,
    normalize_session_path,
    parse_judgement,
    read_manifest,
)


def load_png_on_white(path: Path) -> str:
    from PIL import Image

    image = Image.open(path).convert("RGBA")
    background = Image.new("RGBA", image.size, (255, 255, 255, 255))
    composited = Image.alpha_composite(background, image).convert("RGB")
    buffer = io.BytesIO()
    composited.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def main() -> int:
    default_out = REPO_ROOT / "output" / "sft" / "quality.jsonl"
    parser = argparse.ArgumentParser(description="Screen success sessions with a VLM judge")
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--model", default="qwen3-vl:8b")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--out", type=Path, default=default_out)
    parser.add_argument("--temperature", type=float, default=0.2)
    args = parser.parse_args()

    client = OllamaChatClient(
        base_url=args.base_url,
        model=args.model,
        temperature=args.temperature,
        max_tokens=4096,
    )

    done: set[str] = set()
    if args.out.exists():
        for line in args.out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(normalize_session_path(json.loads(line)["session_log"]))

    total = 0
    matched = 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("a", encoding="utf-8") as stream:
        for manifest_path in args.manifest:
            for entry in read_manifest(manifest_path):
                if not entry.get("success"):
                    continue
                key = normalize_session_path(entry["session_log"])
                if key in done:
                    continue
                session_dir = Path(entry["session_log"]).parent
                png_name = (entry.get("exported_png") or [None])[0]
                png_path = session_dir / png_name if png_name else None
                record = {
                    "manifest": str(manifest_path),
                    "index": entry.get("index"),
                    "goal": entry.get("goal"),
                    "session_log": entry["session_log"],
                    "match": False,
                    "score": 0,
                    "missing": [],
                    "reasoning": "",
                    "error": None,
                }
                if png_path is None or not png_path.exists():
                    record["error"] = "png_missing"
                else:
                    png_b64 = load_png_on_white(png_path)
                    messages = build_judge_messages(entry["goal"], png_b64)
                    started = time.time()
                    try:
                        raw = client.complete(messages)
                        verdict = parse_judgement(raw)
                        if verdict is None:
                            record["error"] = f"unparseable_judgement: {raw[:120]}"
                        else:
                            record.update(verdict)
                    except Exception as exc:  # noqa: BLE001
                        record["error"] = f"judge_failed: {exc}"
                    record["elapsed_s"] = round(time.time() - started, 1)
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                stream.flush()
                total += 1
                if record["match"]:
                    matched += 1
                status = "PASS" if record["match"] else "FAIL"
                print(
                    f"[{entry.get('index')}] {status} score={record['score']}"
                    f" {record['reasoning'] or record['error']}",
                    flush=True,
                )

    print(json.dumps({"judged": total, "matched": matched, "out": str(args.out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
