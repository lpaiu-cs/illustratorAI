from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nic_agent.stage0 import extract_sft_samples, read_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Stage 1 SFT dataset from batch manifests")
    parser.add_argument(
        "--manifest",
        type=Path,
        action="append",
        required=True,
        help="Path to manifest.jsonl (repeatable)",
    )
    parser.add_argument("--out", type=Path, required=True, help="Output dataset jsonl path")
    parser.add_argument(
        "--include-repair",
        action="store_true",
        help="Keep sessions that needed repair rounds (default: clean sessions only)",
    )
    args = parser.parse_args()

    samples = []
    stats = {"sessions": 0, "success": 0, "skipped_repair": 0, "missing_conversation": 0}
    for manifest_path in args.manifest:
        for entry in read_manifest(manifest_path):
            stats["sessions"] += 1
            if not entry.get("success"):
                continue
            stats["success"] += 1
            if entry.get("repair_rounds_used") and not args.include_repair:
                stats["skipped_repair"] += 1
                continue
            session_log = Path(entry["session_log"])
            conversation_path = session_log.parent / "conversation.jsonl"
            if not conversation_path.exists():
                stats["missing_conversation"] += 1
                continue
            conversation = [
                json.loads(line)
                for line in conversation_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            meta = {
                "index": entry.get("index"),
                "goal": entry.get("goal"),
                "repair_rounds_used": entry.get("repair_rounds_used") or 0,
                "manifest": str(manifest_path),
            }
            samples.extend(extract_sft_samples(conversation, meta))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as stream:
        for sample in samples:
            stream.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print(json.dumps({"out": str(args.out), "samples": len(samples), **stats}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
