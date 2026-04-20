from __future__ import annotations

from pathlib import Path

from nic_compiler.path_resolution import export_output_path
from nic_ir.models import IllustrationIR


def export_document(
    ir: IllustrationIR,
    document: object,
    session: object,
    report: object,
    output_root: Path,
) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    session.wait_for_done(document)
    for export in ir.exports:
        if not export.enabled:
            continue
        fallback_name = _default_export_name(ir.document.file_name, export.kind)
        target = export_output_path(output_root, export.file_name, fallback_name)
        if export.kind == "kra":
            session.save_document(document, target)
        elif export.kind in {"png", "psd"}:
            session.export_document(document, target)
        else:
            report.add_unsupported(
                "unsupported_export_kind",
                f"Unsupported export kind: {export.kind}",
                path=export.file_name,
                details={"op": export.kind},
            )
            continue
        report.add_output(export.kind, target)
        outputs[export.kind] = target
    return outputs


def _default_export_name(document_name: str, export_kind: str) -> str:
    if export_kind == "kra":
        return f"{document_name}.kra"
    if export_kind == "png":
        return f"{document_name}_preview.png"
    if export_kind == "psd":
        return f"{document_name}.psd"
    return f"{document_name}.{export_kind}"
