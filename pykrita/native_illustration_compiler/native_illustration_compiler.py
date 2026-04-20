from __future__ import annotations

from pathlib import Path

from nic_compiler.compiler import NativeIllustrationCompiler
from nic_compiler.krita_session import KritaSession
from nic_compiler.path_resolution import (
    build_project_paths,
    default_output_root,
    ensure_output_root,
    manifest_output_path,
    resolve_demo_path,
)

from .bootstrap import append_bootstrap_log, bootstrap_log_path

try:  # pragma: no cover - exercised only in Krita
    from krita import Extension, Krita
    from PyQt5.QtWidgets import QFileDialog, QInputDialog, QMessageBox
except ImportError:  # pragma: no cover - keep importable outside Krita
    try:
        from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox  # type: ignore
        from krita import Extension, Krita  # type: ignore
    except ImportError:  # pragma: no cover
        Extension = object  # type: ignore
        Krita = None  # type: ignore
        QFileDialog = None  # type: ignore
        QInputDialog = None  # type: ignore
        QMessageBox = None  # type: ignore


class NativeIllustrationCompilerExtension(Extension):  # pragma: no cover - Krita runtime only
    def __init__(self, parent):
        super().__init__(parent)
        self.project_paths = build_project_paths(Path(__file__))

    def setup(self) -> None:
        return None

    def createActions(self, window) -> None:
        compile_action = window.createAction(
            "native_illustration_compile_json",
            "Compile IR JSON to New Document",
            "tools/scripts",
        )
        compile_action.triggered.connect(self.compile_ir_json_to_new_document)

        demo_action = window.createAction(
            "native_illustration_compile_demo",
            "Compile Bundled Demo",
            "tools/scripts",
        )
        demo_action.triggered.connect(self.compile_bundled_demo)

        manifest_action = window.createAction(
            "native_illustration_export_manifest",
            "Export Active Document Manifest",
            "tools/scripts",
        )
        manifest_action.triggered.connect(self.export_active_document_manifest)

    def compile_ir_json_to_new_document(self) -> None:
        if QFileDialog is None:
            return
        json_path, _ = QFileDialog.getOpenFileName(
            None,
            "Select IR JSON",
            str(self.project_paths.examples_root),
            "JSON Files (*.json)",
        )
        if not json_path:
            return
        self._run_compile(Path(json_path))

    def compile_bundled_demo(self) -> None:
        if QInputDialog is None:
            return
        options = ["demo_anime_bust.json", "demo_vector_accessories.json"]
        selected, accepted = QInputDialog.getItem(
            None,
            "Select Bundled Demo",
            "Demo",
            options,
            0,
            False,
        )
        if not accepted:
            return
        self._run_compile(resolve_demo_path(self.project_paths, selected))

    def export_active_document_manifest(self) -> None:
        if QFileDialog is None:
            return
        session = KritaSession(self.project_paths.project_root, krita_app=Krita.instance())
        try:
            manifest = session.snapshot_active_document_manifest()
            document_name = str(manifest.get("document", {}).get("name", "active_document"))
            output_root = self._choose_output_root(
                self.project_paths.project_root / ".nic_dev_build" / "manifests"
            )
            manifest_path = manifest_output_path(output_root, document_name)
            session.write_manifest(manifest_path, manifest)
            self._show_message("Manifest exported", f"Saved manifest to:\n{manifest_path}")
        except Exception as exc:
            append_bootstrap_log("Manifest export failed", exc)
            self._show_message(
                "Manifest export failed",
                f"{exc}\n\nBootstrap log:\n{bootstrap_log_path()}",
            )

    def _run_compile(self, json_path: Path) -> None:
        try:
            output_root = self._choose_output_root(default_output_root(self.project_paths.project_root, json_path))
            compiler = NativeIllustrationCompiler(
                self.project_paths.project_root,
                output_root=output_root,
                run_mode="plugin",
                krita_app=Krita.instance(),
            )
            report, report_path = compiler.compile_json_file(json_path.resolve())
        except Exception as exc:
            append_bootstrap_log("Plugin compile entry failed", exc)
            self._show_message(
                "Compile failed before report generation",
                f"{exc}\n\nBootstrap log:\n{bootstrap_log_path()}",
            )
            return

        outputs = "\n".join(
            f"{kind}: {path}"
            for kind, path in report.output_files.items()
            if path is not None
        ) or "(none)"
        errors = len([message for message in report.messages if message.level == "error"])
        warnings = len([message for message in report.messages if message.level == "warning"])
        unsupported = len([message for message in report.messages if message.level == "unsupported"])
        failed_checks = len([item for item in report.self_check if item.status == "fail"])
        status = "Success" if report.success else "Completed with errors"
        body = (
            f"Input: {json_path}\n"
            f"Output root: {report.path_resolution.get('output_root')}\n"
            f"Report: {report_path}\n"
            f"Outputs:\n{outputs}\n\n"
            f"errors={errors}, warnings={warnings}, unsupported={unsupported}, failed_checks={failed_checks}"
        )
        self._show_message(status, body)

    def _choose_output_root(self, suggested: Path) -> Path:
        if QFileDialog is None:
            return ensure_output_root(suggested)
        selected = QFileDialog.getExistingDirectory(
            None,
            "Select Output Directory (Cancel uses default dev output root)",
            str(suggested),
        )
        return ensure_output_root(Path(selected)) if selected else ensure_output_root(suggested)

    def _show_message(self, title: str, body: str) -> None:
        if QMessageBox is None:
            return
        QMessageBox.information(None, title, body)


if Krita is not None:  # pragma: no cover - Krita runtime only
    Krita.instance().addExtension(NativeIllustrationCompilerExtension(Krita.instance()))
