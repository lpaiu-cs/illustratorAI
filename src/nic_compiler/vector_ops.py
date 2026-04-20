from __future__ import annotations

from typing import Any

from nic_ir.models import LayerSpec, OperationSpec


def apply_vector_ops(node: Any, layer: LayerSpec, session: Any, report: Any, layer_path: str) -> None:
    for op in layer.ops:
        try:
            if op.type == "add_svg":
                apply_add_svg(node, op, session)
            else:
                report.add_unsupported(
                    "unsupported_vector_op",
                    f"Unsupported vector op: {op.type}",
                    path=layer_path,
                    details={"op": op.type},
                )
        except Exception as exc:
            report.add_error(
                "vector_op_failed",
                str(exc),
                path=layer_path,
                details={"op": op.type},
            )


def apply_add_svg(node: Any, op: OperationSpec, session: Any) -> None:
    if not hasattr(node, "addShapesFromSvg"):
        raise RuntimeError("Vector layer does not support addShapesFromSvg()")
    svg = _load_svg_payload(op, session)
    node.addShapesFromSvg(svg)


def _load_svg_payload(op: OperationSpec, session: Any) -> str:
    if "svg" in op.payload:
        return str(op.payload["svg"])
    if "path" in op.payload:
        return session.read_text_resource(str(op.payload["path"]))
    if "resource_path" in op.payload:
        return session.read_text_resource(str(op.payload["resource_path"]))
    raise ValueError("add_svg requires svg, path, or resource_path")
