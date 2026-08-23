from nic_agent.executor import ActionExecutor
from nic_agent.headless_backend import HeadlessBackend


def build_executor_with_canvas(output_root=None):
    executor = ActionExecutor(HeadlessBackend(output_root=output_root))
    executor.apply(
        {
            "type": "create_document",
            "payload": {"width": 32, "height": 32, "background_color": "#00000000"},
        }
    )
    executor.apply(
        {
            "type": "create_layer",
            "payload": {"layer_id": "base", "name": "Base", "kind": "paint"},
        }
    )
    return executor


def composite_pixel(executor, x, y):
    document = executor.backend.document
    offset = (y * document.width + x) * 4
    blue, green, red, alpha = document.composite_bgra()[offset : offset + 4]
    return (red, green, blue, alpha)


def test_fill_rect_paints_expected_color():
    executor = build_executor_with_canvas()
    result = executor.apply(
        {
            "type": "fill_rect",
            "payload": {"x": 8, "y": 8, "width": 16, "height": 16, "color": "#FF0000"},
        }
    )
    assert result.ok
    assert composite_pixel(executor, 10, 10) == (255, 0, 0, 255)
    assert composite_pixel(executor, 2, 2) == (0, 0, 0, 0)


def test_stroke_draws_between_points():
    executor = build_executor_with_canvas()
    result = executor.apply(
        {
            "type": "stroke",
            "payload": {"points": [[4, 4], [20, 4]], "color": "#00FF00", "size": 3},
        }
    )
    assert result.ok
    assert composite_pixel(executor, 12, 4) == (0, 255, 0, 255)


def test_stroke_opacity_reduces_accumulated_alpha():
    def center_alpha(opacity=None):
        executor = build_executor_with_canvas()
        payload = {"points": [[4, 4], [20, 4]], "color": "#00FF00FF", "size": 3}
        if opacity is not None:
            payload["opacity"] = opacity
        result = executor.apply({"type": "stroke", "payload": payload})
        assert result.ok
        _, _, _, alpha = composite_pixel(executor, 12, 4)
        return alpha

    assert center_alpha() == 255
    assert center_alpha(opacity=0.5) < 255
    assert center_alpha(opacity=0.1) < center_alpha(opacity=0.5)


def test_state_dependent_errors_are_stable_codes():
    executor = ActionExecutor(HeadlessBackend())
    result = executor.apply(
        {"type": "create_layer", "payload": {"layer_id": "a", "name": "A", "kind": "paint"}}
    )
    assert not result.ok and result.error == "no_document"

    executor.apply({"type": "create_document", "payload": {"width": 8, "height": 8}})
    result = executor.apply({"type": "create_document", "payload": {"width": 8, "height": 8}})
    assert not result.ok and result.error == "document_already_exists"

    result = executor.apply({"type": "select_layer", "payload": {"layer_id": "missing"}})
    assert not result.ok and result.error == "unknown_layer"

    result = executor.apply(
        {"type": "fill_rect", "payload": {"x": 0, "y": 0, "width": 2, "height": 2, "color": "#FFFFFF"}}
    )
    assert not result.ok and result.error == "no_active_paint_layer"


def test_export_png_requires_output_root(tmp_path):
    executor = build_executor_with_canvas()
    result = executor.apply({"type": "export_png", "payload": {"file_name": "out.png"}})
    assert not result.ok and result.error == "no_output_root"

    rooted = build_executor_with_canvas(output_root=tmp_path)
    rooted.apply(
        {"type": "fill_rect", "payload": {"x": 0, "y": 0, "width": 32, "height": 32, "color": "#123456"}}
    )
    result = rooted.apply({"type": "export_png", "payload": {"file_name": "out.png"}})
    assert result.ok
    data = (tmp_path / "out.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"

    result = rooted.apply({"type": "export_png", "payload": {"file_name": "sub/dir.png"}})
    assert not result.ok and result.error == "file_name_must_be_simple"


def test_flat_action_from_model_fails_cleanly_without_crash():
    executor = ActionExecutor(HeadlessBackend())
    result = executor.apply(
        {"type": "select_layer", "layer_id": "base"}
    )
    assert not result.ok
    assert "requires a nested payload" in (result.error or "")


def test_add_svg_draws_on_vector_layer():
    executor = build_executor_with_canvas()
    executor.apply(
        {"type": "create_layer", "payload": {"layer_id": "vec", "name": "Vec", "kind": "vector"}}
    )
    result = executor.apply(
        {
            "type": "add_svg",
            "payload": {
                "svg": '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="16" cy="16" r="8" fill="#FF0000"/></svg>'
            },
        }
    )
    assert result.ok
    assert composite_pixel(executor, 16, 16) == (255, 0, 0, 255)


def test_add_svg_requires_active_vector_layer():
    executor = build_executor_with_canvas()
    result = executor.apply({"type": "add_svg", "payload": {"svg": "<svg><rect/></svg>"}})
    assert not result.ok and result.error == "active_layer_not_vector"


def test_group_visibility_cascades_to_children():
    executor = build_executor_with_canvas()
    executor.apply(
        {"type": "create_layer", "payload": {"layer_id": "art", "name": "Art", "kind": "group"}}
    )
    executor.apply(
        {
            "type": "create_layer",
            "payload": {
                "layer_id": "child",
                "name": "Child",
                "kind": "paint",
                "parent_id": "art",
            },
        }
    )
    executor.apply(
        {
            "type": "fill_rect",
            "payload": {"x": 4, "y": 4, "width": 8, "height": 8, "color": "#00FFFF"},
        }
    )
    assert composite_pixel(executor, 6, 6) == (0, 255, 255, 255)
    executor.apply(
        {"type": "set_layer_properties", "payload": {"layer_id": "art", "visible": False}}
    )
    assert composite_pixel(executor, 6, 6) == (0, 0, 0, 0)

    observation = executor.observe()
    child_entry = next(layer for layer in observation["layers"] if layer["id"] == "child")
    assert child_entry["parent_id"] == "art"


def test_observation_surfaces_unsupported_svg_features():
    executor = build_executor_with_canvas()
    executor.apply(
        {"type": "create_layer", "payload": {"layer_id": "vec", "name": "Vec", "kind": "vector"}}
    )
    executor.apply(
        {
            "type": "add_svg",
            "payload": {
                "svg": '<svg xmlns="http://www.w3.org/2000/svg"><rect transform="rotate(45)" x="1" y="1" width="5" height="5" fill="red"/></svg>'
            },
        }
    )
    warnings = executor.observe()["warnings"]
    assert any(item == "svg:transform:rect" for item in warnings)


def test_observation_reports_delta_bbox_and_fingerprint():
    executor = build_executor_with_canvas()
    before = executor.observe()
    assert before["changed_bbox"] is None
    executor.apply(
        {
            "type": "fill_rect",
            "payload": {"x": 4, "y": 4, "width": 8, "height": 8, "color": "#FFFFFF"},
        }
    )
    after = executor.observe()
    assert after["changed_bbox"] == [4, 4, 8, 8]
    assert after["fingerprint"].startswith("crc32:")
    again = executor.observe()
    assert again["changed_bbox"] is None
