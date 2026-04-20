from __future__ import annotations

from pathlib import Path


def test_example_files_exist() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    expected = [
        repo_root / "examples" / "demo_anime_bust.json",
        repo_root / "examples" / "demo_vector_accessories.json",
        repo_root / "examples" / "assets" / "sparkle.svg",
        repo_root / "examples" / "assets" / "glasses.svg",
        repo_root / "examples" / "assets" / "eye_highlight.png",
        repo_root / "examples" / "assets" / "face_base.png",
    ]
    missing = [path for path in expected if not path.exists()]
    assert missing == []

