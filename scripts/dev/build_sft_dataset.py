from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nic_agent.stage0 import (  # noqa: E402
    extract_sft_samples,
    load_quality_passes,
    normalize_session_path,
    read_manifest,
    validate_sft_sample,
)


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
    parser.add_argument(
        "--quality-file",
        type=Path,
        action="append",
        default=None,
        help="quality.jsonl from screen_quality.py; when given, only judged-pass sessions are kept",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=6,
        help="Minimum judge score (0-10) when --quality-file is used (default 6)",
    )
    args = parser.parse_args()

    quality_passes = None
    if args.quality_file:
        quality_passes = load_quality_passes(args.quality_file, args.min_score)

    samples = []
    stats = {
        "sessions": 0,
        "success": 0,
        "skipped_repair": 0,
        "skipped_quality": 0,
        "missing_conversation": 0,
        "raw_samples": 0,
        "dropped_invalid_samples": 0,
    }
    for manifest_path in args.manifest:
        for entry in read_manifest(manifest_path):
            stats["sessions"] += 1
            if not entry.get("success"):
                continue
            stats["success"] += 1
            if entry.get("repair_rounds_used") and not args.include_repair:
                stats["skipped_repair"] += 1
                continue
            if quality_passes is not None and (
                normalize_session_path(entry["session_log"]) not in quality_passes
            ):
                stats["skipped_quality"] += 1
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
            for sample in extract_sft_samples(conversation, meta):
                stats["raw_samples"] += 1
                if validate_sft_sample(sample):
                    stats["dropped_invalid_samples"] += 1
                    continue
                samples.append(sample)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as stream:
        for sample in samples:
            stream.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print(json.dumps({"out": str(args.out), "samples": len(samples), **stats}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
