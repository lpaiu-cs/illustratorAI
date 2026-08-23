from __future__ import annotations

ACTION_SCHEMA_VERSION = "0.1.0"

SUPPORTED_ACTION_TYPES = frozenset(
    {
        "create_document",
        "create_layer",
        "select_layer",
        "fill_rect",
        "stroke",
        "add_svg",
        "set_layer_properties",
        "export_png",
        "finish",
    }
)
SUPPORTED_LAYER_TYPES = frozenset({"paint", "group", "vector"})
MAX_CANVAS_DIMENSION = 8192
MAX_STROKE_POINTS = 4096
MAX_BRUSH_SIZE = 512.0


def build_action_json_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.local/nic-agent-action.schema.json",
        "title": "NIC Agent Action Protocol",
        "type": "object",
        "required": ["type"],
        "properties": {
            "type": {"enum": sorted(SUPPORTED_ACTION_TYPES)},
            "payload": {"type": "object"},
        },
    }


ACTION_JSON_SCHEMA = build_action_json_schema()
