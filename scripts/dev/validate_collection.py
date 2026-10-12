from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nic_agent.session_log import read_actions  # noqa: E402
from nic_agent.stage0 import (  # noqa: E402
    extract_sft_samples,
    read_manifest,
    replay_fingerprint,
    validate_sft_sample,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate collected sessions and SFT samples")
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument(
        "--include-repair",
        action="store_true",
        help="Include sessions that needed repair rounds in sample validation",
    )
    args = parser.parse_args()

    report = {
        "success_sessions": 0,
        "replays_matched": 0,
        "replays_mismatched": 0,
        "samples": 0,
        "invalid_samples": 0,
        "mismatches": [],
        "sample_issues": [],
    }

    for manifest_path in args.manifest:
        for entry in read_manifest(manifest_path):
            if not entry.get("success"):
                continue
            report["success_sessions"] += 1
            session_log = Path(entry["session_log"])
            actions = read_actions(session_log)
            fingerprint = replay_fingerprint(actions)
            if fingerprint == entry.get("fingerprint"):
                report["replays_matched"] += 1
            else:
                report["replays_mismatched"] += 1
                report["mismatches"].append(
                    {
                        "manifest": str(manifest_path),
                        "index": entry.get("index"),
                        "expected": entry.get("fingerprint"),
                        "replayed": fingerprint,
                    }
                )
            if entry.get("repair_rounds_used") and not args.include_repair:
                continue
            conversation_path = session_log.parent / "conversation.jsonl"
            if not conversation_path.exists():
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
            }
            for sample in extract_sft_samples(conversation, meta):
                report["samples"] += 1
                issues = validate_sft_sample(sample)
                if issues:
                    report["invalid_samples"] += 1
                    report["sample_issues"].append(
                        {"source_index": sample["source_index"], "turn": sample["turn"], "issues": issues}
                    )

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["replays_mismatched"] == 0 and report["invalid_samples"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
