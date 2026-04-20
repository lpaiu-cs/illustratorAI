from __future__ import annotations

from nic_compiler.layer_builder import build_layer_plan
from nic_ir.models import LayerSpec, MaskSpec, OperationSpec


def test_build_layer_plan_preserves_bottom_to_top_order() -> None:
    layers = (
        LayerSpec(
            id="background",
            name="background",
            type="paint",
            ops=(OperationSpec(type="fill_solid", payload={"color": "#FFFFFFFF"}),),
        ),
        LayerSpec(
            id="character",
            name="character",
            type="group",
            masks=(MaskSpec(id="clip", name="clip", type="selection_mask"),),
            children=(
                LayerSpec(id="sketch", name="sketch", type="paint"),
                LayerSpec(id="lineart", name="lineart", type="paint"),
            ),
        ),
    )

    plan = build_layer_plan(layers)

    assert [node.layer_id for node in plan] == ["background", "character", "sketch", "lineart"]
    assert plan[1].mask_ids == ("clip",)
    assert plan[2].path == "character/sketch"
    assert plan[3].stack_index == 3


def test_build_layer_plan_records_child_ids() -> None:
    layers = (
        LayerSpec(
            id="group",
            name="group",
            type="group",
            children=(
                LayerSpec(id="a", name="a", type="paint"),
                LayerSpec(id="b", name="b", type="vector"),
            ),
        ),
    )

    plan = build_layer_plan(layers)

    assert plan[0].child_ids == ("a", "b")

