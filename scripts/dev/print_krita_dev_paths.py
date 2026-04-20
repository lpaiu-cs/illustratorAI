from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    from nic_compiler.path_resolution import build_project_paths

    project_paths = build_project_paths(repo_root)
    krita_resource_root = Path(
        os.environ.get("KRITA_RESOURCE_ROOT", "~/Library/Application Support/Krita")
    ).expanduser()
    payload = {
        "repo_root": str(project_paths.project_root),
        "src_root": str(project_paths.src_root),
        "examples_root": str(project_paths.examples_root),
        "assets_root": str(project_paths.assets_root),
        "krita_resource_root": str(krita_resource_root),
        "krita_pykrita_dir": str(krita_resource_root / "pykrita"),
        "desktop_source": str(project_paths.pykrita_root / "native_illustration_compiler.desktop"),
        "plugin_source_dir": str(project_paths.pykrita_root / "native_illustration_compiler"),
        "desktop_target": str(
            krita_resource_root / "pykrita" / "native_illustration_compiler.desktop"
        ),
        "plugin_target_dir": str(
            krita_resource_root / "pykrita" / "native_illustration_compiler"
        ),
        "krita_resource_root_exists": krita_resource_root.exists(),
        "pykrita_dir_exists": (krita_resource_root / "pykrita").exists(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
