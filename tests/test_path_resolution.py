from __future__ import annotations

from pathlib import Path

from nic_compiler.path_resolution import (
    build_project_paths,
    default_output_root,
    export_output_path,
)


def test_build_project_paths_discovers_repo_layout() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    paths = build_project_paths(repo_root)

    assert paths.project_root == repo_root
    assert paths.src_root == repo_root / "src"
    assert paths.examples_root == repo_root / "examples"
    assert paths.assets_root == repo_root / "examples" / "assets"


def test_default_output_root_is_repo_scoped_dev_build() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source_path = repo_root / "examples" / "demo_anime_bust.json"

    output_root = default_output_root(repo_root, source_path)

    assert output_root == repo_root / ".nic_dev_build" / "demo_anime_bust"


def test_export_output_path_uses_leaf_filename_only(tmp_path: Path) -> None:
    target = export_output_path(tmp_path, "nested/build/demo.kra", "fallback.kra")

    assert target == tmp_path / "demo.kra"

