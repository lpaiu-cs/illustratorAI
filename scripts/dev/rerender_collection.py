from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from nic_agent.executor import ActionExecutor  # noqa: E402
from nic_agent.headless_backend import HeadlessBackend  # noqa: E402
from nic_agent.session_log import read_actions  # noqa: E402
from nic_agent.stage0 import read_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay successful sessions to regenerate exports with the current renderer"
    )
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    args = parser.parse_args()

    replayed = 0
    fingerprint_changes = 0
    for manifest_path in args.manifest:
        for entry in read_manifest(manifest_path):
            if not entry.get("success"):
                continue
            session_log = Path(entry["session_log"])
            session_dir = session_log.parent
            executor = ActionExecutor(HeadlessBackend(output_root=session_dir))
            for action in read_actions(session_log):
                executor.apply(action)
            new_fingerprint = executor.fingerprint()
            replayed += 1
            if new_fingerprint != entry.get("fingerprint"):
                fingerprint_changes += 1

    print(
        f"replayed={replayed} sessions; fingerprint_changed={fingerprint_changes}"
        " (expected after renderer changes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
