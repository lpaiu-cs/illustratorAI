from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from nic_compiler.mask_ops import build_mask_nodes
from nic_compiler.raster_ops import apply_raster_ops
from nic_compiler.vector_ops import apply_vector_ops
from nic_ir.models import IllustrationIR, LayerSpec


@dataclass(slots=True, frozen=True)
class LayerPlanNode:
    layer_id: str
    name: str
    layer_type: str
    parent_id: str | None
    depth: int
    stack_index: int
    path: str
    child_ids: tuple[str, ...]
    mask_ids: tuple[str, ...]
    op_types: tuple[str, ...]


def build_layer_plan(layers: Sequence[LayerSpec]) -> tuple[LayerPlanNode, ...]:
    flattened: list[LayerPlanNode] = []

    def visit(
        layer: LayerSpec,
        *,
        parent_id: str | None,
        depth: int,
        stack_index: int,
        path: str,
    ) -> int:
        flattened.append(
            LayerPlanNode(
                layer_id=layer.id,
                name=layer.name,
                layer_type=layer.type,
                parent_id=parent_id,
                depth=depth,
                stack_index=stack_index,
                path=path,
                child_ids=tuple(child.id for child in layer.children),
                mask_ids=tuple(mask.id for mask in layer.masks),
                op_types=tuple(op.type for op in layer.ops),
            )
        )
        next_index = stack_index + 1
        for child in layer.children:
            next_path = f"{path}/{child.name}"
            next_index = visit(
                child,
                parent_id=layer.id,
                depth=depth + 1,
                stack_index=next_index,
                path=next_path,
            )
        return next_index

    index = 0
    for layer in layers:
        index = visit(layer, parent_id=None, depth=0, stack_index=index, path=layer.name)
    return tuple(flattened)


def compile_layer_tree(
    ir: IllustrationIR,
    document: Any,
    session: Any,
    report: Any,
) -> dict[str, Any]:
    root = session.root_node(document)
    node_map: dict[str, Any] = {}
    deferred_ops: list[tuple[Any, LayerSpec, str]] = []

    def build(layer: LayerSpec, path: str) -> Any:
        node = session.create_layer_node(document, layer)
        session.apply_common_layer_attributes(node, layer)
        node_map[layer.id] = node

        child_nodes = [build(child, f"{path}/{child.name}") for child in layer.children]
        mask_nodes = build_mask_nodes(document, layer.masks, session, report, path)
        if child_nodes or mask_nodes:
            session.set_child_nodes(node, [*child_nodes, *mask_nodes])
        deferred_ops.append((node, layer, path))
        return node

    top_nodes = [build(layer, layer.name) for layer in ir.layers]
    session.set_child_nodes(root, top_nodes)
    for node, layer, path in deferred_ops:
        if layer.type in {"paint", "imported_raster"}:
            apply_raster_ops(node, layer, document, ir.document, session, report, path)
        elif layer.type == "vector":
            apply_vector_ops(node, layer, session, report, path)
    return node_map
