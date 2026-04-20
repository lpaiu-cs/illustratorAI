from __future__ import annotations

from typing import Any

from nic_ir.models import MaskSpec


def build_mask_nodes(
    document: Any,
    masks: tuple[MaskSpec, ...],
    session: Any,
    report: Any,
    layer_path: str,
) -> list[Any]:
    nodes: list[Any] = []
    for mask in masks:
        try:
            node = session.create_mask_node(document, mask)
            session.apply_common_mask_attributes(node, mask)
            _apply_mask_payload(node, mask, session, report, layer_path)
            nodes.append(node)
        except Exception as exc:
            report.add_error(
                "mask_build_failed",
                str(exc),
                path=f"{layer_path}/{mask.name}",
                details={"mask_type": mask.type},
            )
    return nodes


def _apply_mask_payload(
    node: Any,
    mask: MaskSpec,
    session: Any,
    report: Any,
    layer_path: str,
) -> None:
    if mask.type in {"selection_mask", "transparency_mask"}:
        if mask.selection is not None:
            selection = session.create_selection(mask.selection)
            if hasattr(node, "setSelection"):
                node.setSelection(selection)
            else:
                report.add_unsupported(
                    "mask_selection_missing_api",
                    f"{mask.type} does not expose setSelection() in this runtime",
                    path=f"{layer_path}/{mask.name}",
                )
    elif mask.type == "transform_mask":
        if mask.transform:
            report.add_unsupported(
                "transform_mask_payload_not_applied",
                "v0 creates transform masks but does not apply transform payload automatically",
                path=f"{layer_path}/{mask.name}",
                details={"transform": dict(mask.transform)},
            )

