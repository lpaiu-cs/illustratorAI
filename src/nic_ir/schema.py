from __future__ import annotations

IR_SCHEMA_VERSION = "0.1.0"

SUPPORTED_DOCUMENT_COLOR_MODELS = frozenset({"RGBA"})
SUPPORTED_DOCUMENT_COLOR_DEPTHS = frozenset({"U8"})
SUPPORTED_RESOURCE_KINDS = frozenset({"png", "svg"})
SUPPORTED_LAYER_TYPES = frozenset({"group", "paint", "vector", "imported_raster"})
SUPPORTED_EXPORT_KINDS = frozenset({"kra", "png", "psd"})
SUPPORTED_MASK_TYPES = frozenset({"selection_mask", "transparency_mask", "transform_mask"})
SUPPORTED_PAINT_OPS = frozenset(
    {"fill_solid", "put_pixels", "import_png", "brush_line", "brush_path"}
)
SUPPORTED_VECTOR_OPS = frozenset({"add_svg"})
SUPPORTED_IMPORTED_RASTER_OPS = frozenset({"import_png"})


def build_ir_json_schema() -> dict:
    layer_properties = {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "type": {"enum": sorted(SUPPORTED_LAYER_TYPES)},
        "visible": {"type": "boolean"},
        "opacity": {"type": ["number", "integer"]},
        "blend_mode": {"type": "string"},
        "locked": {"type": "boolean"},
        "alpha_locked": {"type": "boolean"},
        "inherit_alpha": {"type": "boolean"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "ops": {"type": "array", "items": {"$ref": "#/$defs/operation"}},
        "masks": {"type": "array", "items": {"$ref": "#/$defs/mask"}},
        "children": {"type": "array", "items": {"$ref": "#/$defs/layer"}},
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.local/native-illustration-compiler.schema.json",
        "title": "Native Illustration Compiler IR",
        "type": "object",
        "required": ["document", "layers"],
        "properties": {
            "meta": {"type": "object"},
            "document": {"$ref": "#/$defs/document"},
            "resources": {
                "type": "array",
                "items": {"$ref": "#/$defs/resource"},
            },
            "layers": {
                "type": "array",
                "items": {"$ref": "#/$defs/layer"},
            },
            "exports": {
                "type": "array",
                "items": {"$ref": "#/$defs/export"},
            },
        },
        "$defs": {
            "document": {
                "type": "object",
                "required": [
                    "width",
                    "height",
                    "dpi",
                    "color_model",
                    "color_depth",
                    "background_color",
                    "file_name",
                ],
                "properties": {
                    "width": {"type": "integer", "minimum": 1},
                    "height": {"type": "integer", "minimum": 1},
                    "dpi": {"type": "integer", "minimum": 1},
                    "color_model": {"enum": sorted(SUPPORTED_DOCUMENT_COLOR_MODELS)},
                    "color_depth": {"enum": sorted(SUPPORTED_DOCUMENT_COLOR_DEPTHS)},
                    "background_color": {"type": "string"},
                    "file_name": {"type": "string"},
                },
            },
            "resource": {
                "type": "object",
                "required": ["id", "kind", "path"],
                "properties": {
                    "id": {"type": "string"},
                    "kind": {"enum": sorted(SUPPORTED_RESOURCE_KINDS)},
                    "path": {"type": "string"},
                },
            },
            "export": {
                "type": "object",
                "required": ["kind", "file_name"],
                "properties": {
                    "kind": {"enum": sorted(SUPPORTED_EXPORT_KINDS)},
                    "file_name": {"type": "string"},
                    "enabled": {"type": "boolean"},
                },
            },
            "mask": {
                "type": "object",
                "required": ["id", "name", "type"],
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "type": {"enum": sorted(SUPPORTED_MASK_TYPES)},
                    "visible": {"type": "boolean"},
                    "selection": {"type": "object"},
                    "transform": {"type": "object"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
            },
            "operation": {
                "type": "object",
                "required": ["type"],
                "properties": {
                    "type": {
                        "enum": sorted(
                            SUPPORTED_PAINT_OPS
                            | SUPPORTED_VECTOR_OPS
                            | SUPPORTED_IMPORTED_RASTER_OPS
                        )
                    }
                },
                "additionalProperties": True,
            },
            "layer": {
                "type": "object",
                "required": ["id", "name", "type"],
                "properties": layer_properties,
            },
        },
    }


IR_JSON_SCHEMA = build_ir_json_schema()

