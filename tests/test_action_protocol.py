from nic_agent.executor import ActionExecutor
from nic_agent.models import ActionValidationError
from nic_agent.schema import ACTION_JSON_SCHEMA, SUPPORTED_ACTION_TYPES
from nic_agent.validator import validate_action_payload


def test_valid_actions_parse_into_frozen_action():
    action = validate_action_payload(
        {
            "type": "stroke",
            "payload": {"points": [[0, 0], [10, 10]], "color": "#FF0000", "size": 3},
        }
    )
    assert action.type == "stroke"
    assert action.payload["size"] == 3


def test_payload_is_optional_for_finish():
    assert validate_action_payload({"type": "finish"}).payload == {}


def test_unknown_action_type_rejected():
    try:
        validate_action_payload({"type": "teleport"})
    except ActionValidationError as exc:
        assert any(issue.path == "type" for issue in exc.issues)
        return
    raise AssertionError("expected ActionValidationError")


def test_create_document_dimension_bounds_enforced():
    for width, height in [(0, 10), (10, 0), (8193, 10), ("big", 10)]:
        try:
            validate_action_payload(
                {
                    "type": "create_document",
                    "payload": {"width": width, "height": height},
                }
            )
        except ActionValidationError:
            continue
        raise AssertionError(f"expected rejection for {width}x{height}")


def test_invalid_color_rejected():
    try:
        validate_action_payload(
            {
                "type": "fill_rect",
                "payload": {"x": 0, "y": 0, "width": 4, "height": 4, "color": "blue"},
            }
        )
    except ActionValidationError as exc:
        assert any("color" in issue.path for issue in exc.issues)
        return
    raise AssertionError("expected ActionValidationError")


def test_stroke_requires_two_points_and_positive_size():
    for stroke_payload in [
        {"points": [[1, 2]], "color": "#000000", "size": 2},
        {"points": [[1, 2], [3, 4]], "color": "#000000", "size": 0},
        {"points": [[1, 2], [3, 4, 5]], "color": "#000000", "size": 2},
        {"points": "curve", "color": "#000000", "size": 2},
    ]:
        try:
            validate_action_payload({"type": "stroke", "payload": stroke_payload})
        except ActionValidationError:
            continue
        raise AssertionError(f"expected rejection for {stroke_payload}")


def test_opacity_must_be_between_zero_and_one():
    try:
        validate_action_payload(
            {
                "type": "stroke",
                "payload": {
                    "points": [[0, 0], [9, 9]],
                    "color": "#000000",
                    "size": 2,
                    "opacity": 1.5,
                },
            }
        )
    except ActionValidationError:
        return
    raise AssertionError("expected ActionValidationError")


def test_set_layer_properties_requires_at_least_one_field():
    try:
        validate_action_payload(
            {"type": "set_layer_properties", "payload": {"layer_id": "a"}}
        )
    except ActionValidationError:
        return
    raise AssertionError("expected ActionValidationError")


def test_flat_format_action_rejected_with_payload_error():
    for flat in [
        {"type": "select_layer", "layer_id": "a"},
        {"type": "stroke", "points": [[0, 0], [5, 5]], "color": "#000000", "size": 2},
    ]:
        try:
            validate_action_payload(flat)
        except ActionValidationError as exc:
            assert any(issue.path == "payload" for issue in exc.issues)
            continue
        raise AssertionError(f"expected rejection for {flat}")


def test_schema_lists_all_supported_types():
    listed = set(ACTION_JSON_SCHEMA["properties"]["type"]["enum"])
    assert listed == set(SUPPORTED_ACTION_TYPES)
