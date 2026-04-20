from __future__ import annotations

from pathlib import Path

from nic_compiler.compiler import NativeIllustrationCompiler


def test_dry_run_generates_report_without_krita(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source_path = repo_root / "examples" / "demo_anime_bust.json"
    output_root = tmp_path / "dry_run_output"

    compiler = NativeIllustrationCompiler(
        repo_root,
        output_root=output_root,
        run_mode="dry_run",
    )
    report, report_path = compiler.dry_run_json_file(source_path)

    assert report.run_mode == "dry_run"
    assert report.success is True
    assert report.compile_summary["total_layers"] == 12
    assert report.compile_summary["planned_layers"] == 12
    assert report.compile_summary["created_layers"] == 0
    assert report.path_resolution["output_root"] == str(output_root.resolve())
    assert report.output_files["report"] == str(report_path)
    assert report_path.exists()
    assert any(item.name == "krita_api_import" for item in report.self_check)
