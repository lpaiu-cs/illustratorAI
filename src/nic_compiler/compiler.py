from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from nic_compiler.export_ops import export_document
from nic_compiler.krita_session import KritaSession
from nic_compiler.layer_builder import build_layer_plan, compile_layer_tree
from nic_compiler.path_resolution import (
    build_project_paths,
    report_output_path,
    resolve_output_root,
)
from nic_compiler.reporting import CompileReport, write_report
from nic_compiler.runtime_self_check import (
    collect_environment_info,
    has_critical_failures,
    run_runtime_self_check,
)
from nic_ir.models import IRValidationError, IllustrationIR
from nic_ir.validator import validate_ir_payload


class NativeIllustrationCompiler:
    def __init__(
        self,
        project_root: Path,
        *,
        output_root: Path | None = None,
        run_mode: str = "plugin",
        krita_app: Any | None = None,
    ) -> None:
        self.project_paths = build_project_paths(project_root, explicit_root=project_root)
        self.explicit_output_root = output_root.resolve() if output_root is not None else None
        self.run_mode = run_mode
        self.krita_app = krita_app

    def compile_json_file(self, source_path: Path) -> tuple[CompileReport, Path]:
        return self._compile(source_path.resolve(), run_mode=self.run_mode)

    def dry_run_json_file(self, source_path: Path) -> tuple[CompileReport, Path]:
        return self._compile(source_path.resolve(), run_mode="dry_run")

    def compile_payload(
        self,
        payload: dict[str, Any],
        *,
        source_name: str = "inline_ir",
    ) -> tuple[CompileReport, Path]:
        temp_source = self.project_paths.project_root / f"{source_name}.json"
        temp_source.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self._compile(temp_source, run_mode=self.run_mode)

    def _compile(self, source_path: Path, run_mode: str) -> tuple[CompileReport, Path]:
        output_root = resolve_output_root(
            self.project_paths.project_root,
            source_path,
            explicit_output_root=self.explicit_output_root,
        )
        report = CompileReport(
            run_mode=run_mode,
            source_ir_path=str(source_path),
            workspace_root=str(source_path.parent),
        )
        report.path_resolution = {
            **self.project_paths.to_dict(),
            "source_workspace": str(source_path.parent),
            "output_root": str(output_root),
        }
        report_path = report_output_path(output_root, source_path.stem)

        session = KritaSession(source_path.parent, krita_app=self.krita_app)
        report.environment = collect_environment_info(session)
        for item in run_runtime_self_check(
            self.project_paths,
            source_path=source_path,
            output_root=output_root,
            session=session,
            require_krita=(run_mode == "plugin"),
        ):
            report.add_self_check(item)

        if has_critical_failures(report.self_check):
            report.add_error("self_check_failed", "Critical self-check failed before compile start")
            report.finalize(success=False)
            write_report(report, report_path)
            return report, report_path

        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
            ir = validate_ir_payload(
                payload,
                workspace_root=source_path.parent,
                source_path=source_path,
            )
            self._resolve_resource_paths(ir)
            layer_plan = build_layer_plan(ir.layers)
            report.document = {
                "file_name": ir.document.file_name,
                "width": ir.document.width,
                "height": ir.document.height,
                "dpi": ir.document.dpi,
                "color_model": ir.document.color_model,
                "color_depth": ir.document.color_depth,
                "layer_plan": [asdict(plan) for plan in layer_plan],
            }
            report.compile_summary["total_layers"] = len(tuple(ir.walk_layers()))
            report.compile_summary["planned_layers"] = len(layer_plan)

            if run_mode == "dry_run":
                report.capability = session.probe_runtime_capabilities().to_dict()
                self._scan_dry_run_risks(ir, report)
            else:
                document = session.create_document(ir.document)
                session.present_document(document)
                report.capability = session.detect_capabilities(document).to_dict()
                node_map = compile_layer_tree(ir, document, session, report)
                report.compile_summary["created_layers"] = len(node_map)
                export_document(ir, document, session, report, output_root)
        except IRValidationError as exc:
            for issue in exc.issues:
                report.add_error("validation_error", issue.message, path=issue.path)
        except Exception as exc:
            report.add_error("compile_exception", str(exc))
        finally:
            success = not any(message.level == "error" for message in report.messages)
            report.finalize(success=success)
            write_report(report, report_path)
        return report, report_path

    def _resolve_resource_paths(self, ir: IllustrationIR) -> None:
        resource_paths = {resource.id: resource.path for resource in ir.resources.values()}
        for layer in ir.walk_layers():
            for op in layer.ops:
                resource_id = op.payload.get("resource_id")
                if resource_id:
                    op.payload.setdefault("resource_path", resource_paths[str(resource_id)])

    def _scan_dry_run_risks(self, ir: IllustrationIR, report: CompileReport) -> None:
        for layer in ir.walk_layers():
            for op in layer.ops:
                if op.type in {"brush_line", "brush_path"}:
                    report.add_warning(
                        "runtime_capability_required",
                        f"{op.type} depends on Krita runtime capabilities and may fall back at runtime",
                        path=layer.id,
                        details={"op": op.type},
                    )
            for mask in layer.masks:
                if mask.type == "transform_mask" and mask.transform:
                    report.add_unsupported(
                        "transform_mask_payload_not_applied",
                        "dry-run detected a transform mask payload that is not implemented in v0",
                        path=f"{layer.id}/{mask.id}",
                        details={"op": "transform_mask"},
                    )
