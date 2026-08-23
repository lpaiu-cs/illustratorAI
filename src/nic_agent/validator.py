from __future__ import annotations

from typing import Any, Mapping

from nic_compiler.raster_ops import parse_hex_color

from nic_agent.models import (
    Action,
    ActionValidationError,
    ActionValidationIssue,
)
from nic_agent.schema import (
    MAX_BRUSH_SIZE,
    MAX_CANVAS_DIMENSION,
    MAX_STROKE_POINTS,
    SUPPORTED_ACTION_TYPES,
    SUPPORTED_LAYER_TYPES,
)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_nonempty_str(
    issues: list[ActionValidationIssue], path: str, value: Any
) -> None:
    if not isinstance(value, str) or not value.strip():
        issues.append(ActionValidationIssue("error", path, "must be a non-empty string"))


def _check_int_range(
    issues: list[ActionValidationIssue],
    path: str,
    value: Any,
    minimum: int,
    maximum: int | None = None,
) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        issues.append(ActionValidationIssue("error", path, "must be an integer"))
        return
    if value < minimum or (maximum is not None and value > maximum):
        bound = f">= {minimum}" if maximum is None else f"between {minimum} and {maximum}"
        issues.append(ActionValidationIssue("error", path, f"must be {bound}"))


def _check_number_range(
    issues: list[ActionValidationIssue],
    path: str,
    value: Any,
    minimum: float,
    maximum: float,
) -> None:
    if not _is_number(value):
        issues.append(ActionValidationIssue("error", path, "must be a number"))
        return
    if value < minimum or value > maximum:
        issues.append(
            ActionValidationIssue("error", path, f"must be between {minimum} and {maximum}")
        )


def _check_color(issues: list[ActionValidationIssue], path: str, value: Any) -> None:
    if not isinstance(value, str):
        issues.append(ActionValidationIssue("error", path, "color must be a string"))
        return
    try:
        parse_hex_color(value)
    except ValueError as exc:
        issues.append(ActionValidationIssue("error", path, str(exc)))


def _check_create_document(
    issues: list[ActionValidationIssue], body: Mapping[str, Any]
) -> None:
    _check_int_range(issues, "width", body.get("width"), 1, MAX_CANVAS_DIMENSION)
    _check_int_range(issues, "height", body.get("height"), 1, MAX_CANVAS_DIMENSION)
    if "dpi" in body:
        _check_int_range(issues, "dpi", body["dpi"], 1)
    if "background_color" in body:
        _check_color(issues, "background_color", body["background_color"])
    if "file_name" in body:
        _check_nonempty_str(issues, "file_name", body["file_name"])


def _check_create_layer(
    issues: list[ActionValidationIssue], body: Mapping[str, Any]
) -> None:
    _check_nonempty_str(issues, "layer_id", body.get("layer_id"))
    _check_nonempty_str(issues, "name", body.get("name"))
    layer_kind = body.get("kind")
    if layer_kind not in SUPPORTED_LAYER_TYPES:
        issues.append(
            ActionValidationIssue(
                "error", "kind", f"layer kind must be one of {sorted(SUPPORTED_LAYER_TYPES)}"
            )
        )
    if "parent_id" in body:
        _check_nonempty_str(issues, "parent_id", body["parent_id"])
    if "opacity" in body:
        _check_number_range(issues, "opacity", body["opacity"], 0.0, 1.0)
    if "visible" in body and not isinstance(body["visible"], bool):
        issues.append(ActionValidationIssue("error", "visible", "must be a boolean"))


def _check_select_layer(
    issues: list[ActionValidationIssue], body: Mapping[str, Any]
) -> None:
    _check_nonempty_str(issues, "layer_id", body.get("layer_id"))


def _check_fill_rect(
    issues: list[ActionValidationIssue], body: Mapping[str, Any]
) -> None:
    for key in ("x", "y"):
        _check_int_range(issues, key, body.get(key), 0)
    for key in ("width", "height"):
        _check_int_range(issues, key, body.get(key), 1)
    _check_color(issues, "color", body.get("color"))


def _check_stroke(issues: list[ActionValidationIssue], body: Mapping[str, Any]) -> None:
    points = body.get("points")
    if not isinstance(points, list) or len(points) < 2:
        issues.append(
            ActionValidationIssue("error", "points", "stroke requires at least two [x, y] points")
        )
    elif len(points) > MAX_STROKE_POINTS:
        issues.append(
            ActionValidationIssue(
                "error", "points", f"stroke exceeds {MAX_STROKE_POINTS} points"
            )
        )
    else:
        for index, point in enumerate(points):
            if (
                not isinstance(point, (list, tuple))
                or len(point) != 2
                or not all(_is_number(value) for value in point)
            ):
                issues.append(
                    ActionValidationIssue(
                        "error", f"points[{index}]", "point must be [x, y] numbers"
                    )
                )
                break
    _check_color(issues, "color", body.get("color"))
    size = body.get("size")
    if not _is_number(size) or size <= 0:
        issues.append(ActionValidationIssue("error", "size", "must be a positive number"))
    elif size > MAX_BRUSH_SIZE:
        issues.append(ActionValidationIssue("error", "size", f"must be <= {MAX_BRUSH_SIZE}"))
    if "opacity" in body:
        _check_number_range(issues, "opacity", body["opacity"], 0.0, 1.0)


def _check_set_layer_properties(
    issues: list[ActionValidationIssue], body: Mapping[str, Any]
) -> None:
    _check_nonempty_str(issues, "layer_id", body.get("layer_id"))
    if not {"visible", "opacity", "name"}.intersection(body):
        issues.append(
            ActionValidationIssue(
                "error", "payload", "requires at least one of visible, opacity, name"
            )
        )
    if "visible" in body and not isinstance(body["visible"], bool):
        issues.append(ActionValidationIssue("error", "visible", "must be a boolean"))
    if "opacity" in body:
        _check_number_range(issues, "opacity", body["opacity"], 0.0, 1.0)
    if "name" in body:
        _check_nonempty_str(issues, "name", body["name"])


def _check_export_png(
    issues: list[ActionValidationIssue], body: Mapping[str, Any]
) -> None:
    _check_nonempty_str(issues, "file_name", body.get("file_name"))


def _check_add_svg(
    issues: list[ActionValidationIssue], body: Mapping[str, Any]
) -> None:
    _check_nonempty_str(issues, "svg", body.get("svg"))


_CHECKERS = {
    "create_document": _check_create_document,
    "create_layer": _check_create_layer,
    "select_layer": _check_select_layer,
    "fill_rect": _check_fill_rect,
    "stroke": _check_stroke,
    "add_svg": _check_add_svg,
    "set_layer_properties": _check_set_layer_properties,
    "export_png": _check_export_png,
    "finish": lambda issues, body: None,
}


def validate_action_payload(payload: Mapping[str, Any]) -> Action:
    action_type = payload.get("type")
    if not isinstance(action_type, str) or action_type not in SUPPORTED_ACTION_TYPES:
        raise ActionValidationError(
            [ActionValidationIssue("error", "type", f"unknown action type: {action_type!r}")]
        )
    raw_body = payload.get("payload", {} if action_type == "finish" else None)
    if raw_body is None:
        raise ActionValidationError(
            [
                ActionValidationIssue(
                    "error",
                    "payload",
                    f"action '{action_type}' requires a nested payload object",
                )
            ]
        )
    if not isinstance(raw_body, dict):
        raise ActionValidationError(
            [ActionValidationIssue("error", "payload", "payload must be an object")]
        )
    body = raw_body
    issues: list[ActionValidationIssue] = []
    _CHECKERS[action_type](issues, body)
    if issues:
        raise ActionValidationError(issues)
    return Action(type=action_type, payload=body)
