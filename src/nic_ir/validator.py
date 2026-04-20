from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from nic_compiler.raster_ops import parse_hex_color
from nic_ir.models import (
    DocumentSpec,
    ExportSpec,
    IllustrationIR,
    IRValidationError,
    LayerSpec,
    MaskSpec,
    OperationSpec,
    ResourceSpec,
    SelectionPixelData,
    SelectionRectangle,
    SelectionSpec,
    ValidationIssue,
)
from nic_ir.schema import (
    SUPPORTED_DOCUMENT_COLOR_DEPTHS,
    SUPPORTED_DOCUMENT_COLOR_MODELS,
    SUPPORTED_EXPORT_KINDS,
    SUPPORTED_IMPORTED_RASTER_OPS,
    SUPPORTED_LAYER_TYPES,
    SUPPORTED_MASK_TYPES,
    SUPPORTED_PAINT_OPS,
    SUPPORTED_RESOURCE_KINDS,
    SUPPORTED_VECTOR_OPS,
)


def validate_ir_payload(
    payload: Mapping[str, Any],
    workspace_root: Path | None = None,
    source_path: Path | None = None,
) -> IllustrationIR:
    return IRValidator(workspace_root=workspace_root).validate(payload, source_path=source_path)


class IRValidator:
    def __init__(self, workspace_root: Path | None = None) -> None:
        self.workspace_root = workspace_root.resolve() if workspace_root else None
        self.issues: list[ValidationIssue] = []
        self.seen_ids: set[str] = set()

    def validate(
        self,
        payload: Mapping[str, Any],
        source_path: Path | None = None,
    ) -> IllustrationIR:
        if not isinstance(payload, Mapping):
            raise IRValidationError((ValidationIssue("error", "$", "IR root must be an object"),))

        meta = payload.get("meta", {})
        if meta is None:
            meta = {}
        if not isinstance(meta, Mapping):
            self._error("meta", "meta must be an object")
            meta = {}

        document = self._parse_document(payload.get("document"), "document")
        resources = self._parse_resources(payload.get("resources", []), "resources")
        layers = self._parse_layers(payload.get("layers"), "layers")
        exports = self._parse_exports(payload.get("exports", []), document.file_name, "exports")
        self._validate_resource_refs(layers, resources)

        if self.issues:
            raise IRValidationError(self.issues)

        return IllustrationIR(
            meta=dict(meta),
            document=document,
            resources=resources,
            layers=layers,
            exports=exports,
            source_path=source_path.resolve() if source_path else None,
        )

    def _parse_document(self, data: Any, path: str) -> DocumentSpec:
        if not isinstance(data, Mapping):
            self._error(path, "document must be an object")
            return DocumentSpec(1, 1, 72, "RGBA", "U8", "#00000000", "invalid")

        width = self._as_positive_int(data.get("width"), f"{path}.width")
        height = self._as_positive_int(data.get("height"), f"{path}.height")
        dpi = self._as_positive_int(data.get("dpi"), f"{path}.dpi")
        color_model = self._as_string(data.get("color_model"), f"{path}.color_model")
        color_depth = self._as_string(data.get("color_depth"), f"{path}.color_depth")
        background_color = self._as_string(
            data.get("background_color"), f"{path}.background_color"
        )
        file_name = self._as_string(data.get("file_name"), f"{path}.file_name")

        if color_model not in SUPPORTED_DOCUMENT_COLOR_MODELS:
            self._error(
                f"{path}.color_model",
                f"v0 supports only {sorted(SUPPORTED_DOCUMENT_COLOR_MODELS)}",
            )
        if color_depth not in SUPPORTED_DOCUMENT_COLOR_DEPTHS:
            self._error(
                f"{path}.color_depth",
                f"v0 supports only {sorted(SUPPORTED_DOCUMENT_COLOR_DEPTHS)}",
            )
        self._validate_color(background_color, f"{path}.background_color")
        self._validate_file_name(file_name, f"{path}.file_name")
        return DocumentSpec(width, height, dpi, color_model, color_depth, background_color, file_name)

    def _parse_resources(self, data: Any, path: str) -> dict[str, ResourceSpec]:
        entries: Iterable[tuple[str | None, Any]]
        if isinstance(data, Mapping):
            entries = ((str(key), value) for key, value in data.items())
        elif isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
            entries = ((None, value) for value in data)
        else:
            self._error(path, "resources must be an array or object")
            return {}

        resources: dict[str, ResourceSpec] = {}
        for index, (mapped_id, entry) in enumerate(entries):
            entry_path = f"{path}[{index}]"
            if not isinstance(entry, Mapping):
                self._error(entry_path, "resource entry must be an object")
                continue
            resource_id = self._as_string(entry.get("id", mapped_id), f"{entry_path}.id")
            kind = self._as_string(entry.get("kind"), f"{entry_path}.kind")
            resource_path = self._as_string(entry.get("path"), f"{entry_path}.path")
            if kind not in SUPPORTED_RESOURCE_KINDS:
                self._error(f"{entry_path}.kind", f"unsupported resource kind: {kind}")
            self._check_unique_id(resource_id, f"{entry_path}.id")
            self._validate_workspace_path(resource_path, f"{entry_path}.path", must_exist=True)
            resources[resource_id] = ResourceSpec(id=resource_id, kind=kind, path=resource_path)
        return resources

    def _parse_layers(self, data: Any, path: str) -> tuple[LayerSpec, ...]:
        if not isinstance(data, Sequence) or isinstance(data, (str, bytes, bytearray)):
            self._error(path, "layers must be an array")
            return ()
        return tuple(self._parse_layer(item, f"{path}[{index}]") for index, item in enumerate(data))

    def _parse_layer(self, data: Any, path: str) -> LayerSpec:
        if not isinstance(data, Mapping):
            self._error(path, "layer must be an object")
            return LayerSpec(id=f"invalid-{path}", name="invalid", type="paint")

        layer_id = self._as_string(data.get("id"), f"{path}.id")
        name = self._as_string(data.get("name"), f"{path}.name")
        layer_type = self._as_string(data.get("type"), f"{path}.type")
        visible = self._as_bool(data.get("visible", True), f"{path}.visible")
        opacity = self._coerce_opacity(data.get("opacity", 1.0), f"{path}.opacity")
        blend_mode = self._as_string(data.get("blend_mode", "normal"), f"{path}.blend_mode")
        locked = self._as_bool(data.get("locked", False), f"{path}.locked")
        alpha_locked = self._as_bool(data.get("alpha_locked", False), f"{path}.alpha_locked")
        inherit_alpha = self._as_bool(
            data.get("inherit_alpha", False), f"{path}.inherit_alpha"
        )
        tags = self._parse_tags(data.get("tags", ()), f"{path}.tags")
        ops = self._parse_ops(data.get("ops", ()), f"{path}.ops")
        masks = self._parse_masks(data.get("masks", ()), f"{path}.masks")
        children = self._parse_layers(data.get("children", ()), f"{path}.children")

        self._check_unique_id(layer_id, f"{path}.id")
        if layer_type not in SUPPORTED_LAYER_TYPES:
            self._error(f"{path}.type", f"unsupported layer type: {layer_type}")

        if layer_type == "group":
            if ops:
                self._error(f"{path}.ops", "group layers cannot have ops in v0")
        else:
            if children:
                self._error(f"{path}.children", f"{layer_type} layers cannot have children")

        if layer_type in {"paint", "imported_raster"} and any(
            op.type not in (
                SUPPORTED_PAINT_OPS if layer_type == "paint" else SUPPORTED_IMPORTED_RASTER_OPS
            )
            for op in ops
        ):
            self._error(f"{path}.ops", f"layer type {layer_type} has unsupported ops")

        if layer_type == "vector" and any(op.type not in SUPPORTED_VECTOR_OPS for op in ops):
            self._error(f"{path}.ops", "vector layers support only add_svg")

        if layer_type == "imported_raster" and not ops:
            self._error(f"{path}.ops", "imported_raster layer requires at least one import_png op")

        return LayerSpec(
            id=layer_id,
            name=name,
            type=layer_type,
            visible=visible,
            opacity=opacity,
            blend_mode=blend_mode,
            locked=locked,
            alpha_locked=alpha_locked,
            inherit_alpha=inherit_alpha,
            tags=tags,
            ops=ops,
            masks=masks,
            children=children,
        )

    def _parse_ops(self, data: Any, path: str) -> tuple[OperationSpec, ...]:
        if not isinstance(data, Sequence) or isinstance(data, (str, bytes, bytearray)):
            self._error(path, "ops must be an array")
            return ()

        parsed: list[OperationSpec] = []
        for index, item in enumerate(data):
            entry_path = f"{path}[{index}]"
            if not isinstance(item, Mapping):
                self._error(entry_path, "operation must be an object")
                continue
            op_type = self._as_string(item.get("type"), f"{entry_path}.type")
            payload = dict(item)
            payload.pop("type", None)
            self._validate_op_payload(op_type, payload, entry_path)
            parsed.append(OperationSpec(type=op_type, payload=payload))
        return tuple(parsed)

    def _parse_masks(self, data: Any, path: str) -> tuple[MaskSpec, ...]:
        if not isinstance(data, Sequence) or isinstance(data, (str, bytes, bytearray)):
            self._error(path, "masks must be an array")
            return ()

        parsed: list[MaskSpec] = []
        for index, item in enumerate(data):
            entry_path = f"{path}[{index}]"
            if not isinstance(item, Mapping):
                self._error(entry_path, "mask must be an object")
                continue
            mask_id = self._as_string(item.get("id"), f"{entry_path}.id")
            name = self._as_string(item.get("name"), f"{entry_path}.name")
            mask_type = self._as_string(item.get("type"), f"{entry_path}.type")
            visible = self._as_bool(item.get("visible", True), f"{entry_path}.visible")
            tags = self._parse_tags(item.get("tags", ()), f"{entry_path}.tags")
            selection = self._parse_selection(item.get("selection"), f"{entry_path}.selection")
            transform = item.get("transform", {})
            if transform is None:
                transform = {}
            if not isinstance(transform, Mapping):
                self._error(f"{entry_path}.transform", "transform must be an object")
                transform = {}
            self._check_unique_id(mask_id, f"{entry_path}.id")
            if mask_type not in SUPPORTED_MASK_TYPES:
                self._error(f"{entry_path}.type", f"unsupported mask type: {mask_type}")
            parsed.append(
                MaskSpec(
                    id=mask_id,
                    name=name,
                    type=mask_type,
                    visible=visible,
                    selection=selection,
                    transform=dict(transform),
                    tags=tags,
                )
            )
        return tuple(parsed)

    def _parse_selection(self, data: Any, path: str) -> SelectionSpec | None:
        if data is None:
            return None
        if not isinstance(data, Mapping):
            self._error(path, "selection must be an object")
            return None

        rectangles_data = data.get("rectangles", ())
        rectangles: list[SelectionRectangle] = []
        if not isinstance(rectangles_data, Sequence) or isinstance(
            rectangles_data, (str, bytes, bytearray)
        ):
            self._error(f"{path}.rectangles", "rectangles must be an array")
        else:
            for index, item in enumerate(rectangles_data):
                entry_path = f"{path}.rectangles[{index}]"
                if not isinstance(item, Mapping):
                    self._error(entry_path, "rectangle must be an object")
                    continue
                rectangles.append(
                    SelectionRectangle(
                        x=self._as_int(item.get("x"), f"{entry_path}.x"),
                        y=self._as_int(item.get("y"), f"{entry_path}.y"),
                        width=self._as_positive_int(item.get("width"), f"{entry_path}.width"),
                        height=self._as_positive_int(item.get("height"), f"{entry_path}.height"),
                        value=self._as_byte(item.get("value", 255), f"{entry_path}.value"),
                    )
                )

        pixel_data = data.get("pixel_data")
        parsed_pixel_data: SelectionPixelData | None = None
        if pixel_data is not None:
            if not isinstance(pixel_data, Mapping):
                self._error(f"{path}.pixel_data", "pixel_data must be an object")
            else:
                width = self._as_positive_int(pixel_data.get("width"), f"{path}.pixel_data.width")
                height = self._as_positive_int(
                    pixel_data.get("height"), f"{path}.pixel_data.height"
                )
                values_data = pixel_data.get("values")
                if not isinstance(values_data, Sequence) or isinstance(
                    values_data, (str, bytes, bytearray)
                ):
                    self._error(f"{path}.pixel_data.values", "values must be an array")
                    values = ()
                else:
                    values = tuple(
                        self._as_byte(value, f"{path}.pixel_data.values[{index}]")
                        for index, value in enumerate(values_data)
                    )
                if values and len(values) != width * height:
                    self._error(
                        f"{path}.pixel_data.values",
                        "selection pixel_data length must match width * height",
                    )
                parsed_pixel_data = SelectionPixelData(
                    x=self._as_int(pixel_data.get("x"), f"{path}.pixel_data.x"),
                    y=self._as_int(pixel_data.get("y"), f"{path}.pixel_data.y"),
                    width=width,
                    height=height,
                    values=values,
                )

        return SelectionSpec(rectangles=tuple(rectangles), pixel_data=parsed_pixel_data)

    def _parse_exports(self, data: Any, file_name: str, path: str) -> tuple[ExportSpec, ...]:
        if data in (None, (), []):
            data = [
                {"kind": "kra", "file_name": f"{file_name}.kra", "enabled": True},
                {"kind": "png", "file_name": f"{file_name}_preview.png", "enabled": True},
            ]
        if not isinstance(data, Sequence) or isinstance(data, (str, bytes, bytearray)):
            self._error(path, "exports must be an array")
            return ()

        parsed: list[ExportSpec] = []
        for index, item in enumerate(data):
            entry_path = f"{path}[{index}]"
            if not isinstance(item, Mapping):
                self._error(entry_path, "export must be an object")
                continue
            kind = self._as_string(item.get("kind"), f"{entry_path}.kind")
            file_name_value = self._as_string(item.get("file_name"), f"{entry_path}.file_name")
            enabled = self._as_bool(item.get("enabled", True), f"{entry_path}.enabled")
            if kind not in SUPPORTED_EXPORT_KINDS:
                self._error(f"{entry_path}.kind", f"unsupported export kind: {kind}")
            self._validate_workspace_path(file_name_value, f"{entry_path}.file_name", must_exist=False)
            parsed.append(ExportSpec(kind=kind, file_name=file_name_value, enabled=enabled))
        return tuple(parsed)

    def _validate_op_payload(self, op_type: str, payload: Mapping[str, Any], path: str) -> None:
        if op_type in {"fill_solid", "brush_line", "brush_path"}:
            color = payload.get("color")
            if color is not None:
                self._validate_color(str(color), f"{path}.color")
        if op_type == "fill_solid":
            for key in ("x", "y"):
                if key in payload:
                    self._as_int(payload.get(key), f"{path}.{key}")
            for key in ("width", "height"):
                if key in payload:
                    self._as_positive_int(payload.get(key), f"{path}.{key}")
        elif op_type == "put_pixels":
            self._as_int(payload.get("x"), f"{path}.x")
            self._as_int(payload.get("y"), f"{path}.y")
            rows = payload.get("rows")
            if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
                self._error(f"{path}.rows", "put_pixels rows must be an array of rows")
            else:
                width = None
                for row_index, row in enumerate(rows):
                    if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray)):
                        self._error(f"{path}.rows[{row_index}]", "each row must be an array")
                        continue
                    width = len(row) if width is None else width
                    if len(row) != width:
                        self._error(f"{path}.rows[{row_index}]", "all rows must have equal width")
                    for col_index, value in enumerate(row):
                        self._validate_color(str(value), f"{path}.rows[{row_index}][{col_index}]")
        elif op_type == "import_png":
            if "resource_id" not in payload and "path" not in payload:
                self._error(path, "import_png requires resource_id or path")
            if "path" in payload:
                self._validate_workspace_path(str(payload.get("path")), f"{path}.path", must_exist=True)
            for key in ("x", "y"):
                self._as_int(payload.get(key, 0), f"{path}.{key}")
        elif op_type == "add_svg":
            if "resource_id" not in payload and "path" not in payload and "svg" not in payload:
                self._error(path, "add_svg requires resource_id, path, or svg")
            if "path" in payload:
                self._validate_workspace_path(str(payload.get("path")), f"{path}.path", must_exist=True)
        elif op_type == "brush_line":
            self._validate_point(payload.get("from"), f"{path}.from")
            self._validate_point(payload.get("to"), f"{path}.to")
            if "size" in payload:
                self._as_positive_number(payload.get("size"), f"{path}.size")
        elif op_type == "brush_path":
            points = payload.get("points")
            if not isinstance(points, Sequence) or isinstance(points, (str, bytes, bytearray)):
                self._error(f"{path}.points", "brush_path points must be an array")
            else:
                if len(points) < 2:
                    self._error(f"{path}.points", "brush_path requires at least two points")
                for index, point in enumerate(points):
                    self._validate_point(point, f"{path}.points[{index}]")
            if "size" in payload:
                self._as_positive_number(payload.get("size"), f"{path}.size")
        else:
            self._error(path, f"unsupported operation type: {op_type}")

    def _validate_resource_refs(
        self,
        layers: Sequence[LayerSpec],
        resources: Mapping[str, ResourceSpec],
    ) -> None:
        for layer in layers:
            for item in layer.walk():
                for op in item.ops:
                    resource_id = op.payload.get("resource_id")
                    if resource_id is None:
                        continue
                    resource = resources.get(str(resource_id))
                    if resource is None:
                        self._error(
                            f"layer:{item.id}.op:{op.type}.resource_id",
                            f"unknown resource: {resource_id}",
                        )
                        continue
                    if op.type == "import_png" and resource.kind != "png":
                        self._error(
                            f"layer:{item.id}.op:{op.type}.resource_id",
                            "import_png requires a png resource",
                        )
                    if op.type == "add_svg" and resource.kind != "svg":
                        self._error(
                            f"layer:{item.id}.op:{op.type}.resource_id",
                            "add_svg requires an svg resource",
                        )

    def _coerce_opacity(self, value: Any, path: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self._error(path, "opacity must be a number")
            return 1.0
        if 0.0 <= float(value) <= 1.0:
            return float(value)
        if isinstance(value, int) and 0 <= value <= 255:
            return value / 255.0
        self._error(path, "opacity must be between 0.0..1.0 or 0..255")
        return 1.0

    def _parse_tags(self, data: Any, path: str) -> tuple[str, ...]:
        if not isinstance(data, Sequence) or isinstance(data, (str, bytes, bytearray)):
            self._error(path, "tags must be an array")
            return ()
        tags: list[str] = []
        for index, value in enumerate(data):
            if not isinstance(value, str):
                self._error(f"{path}[{index}]", "tag must be a string")
                continue
            tags.append(value)
        return tuple(tags)

    def _validate_point(self, value: Any, path: str) -> None:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
            self._error(path, "point must be a two-item array")
            return
        if len(value) != 2:
            self._error(path, "point must contain exactly two values")
            return
        self._as_int(value[0], f"{path}[0]")
        self._as_int(value[1], f"{path}[1]")

    def _validate_color(self, value: str, path: str) -> None:
        try:
            parse_hex_color(value)
        except ValueError as exc:
            self._error(path, str(exc))

    def _validate_file_name(self, value: str, path: str) -> None:
        if not value.strip():
            self._error(path, "file_name must not be empty")
        if any(sep in value for sep in ("/", "\\")):
            self._error(path, "file_name must be a base name, not a path")

    def _validate_workspace_path(self, value: str, path: str, must_exist: bool) -> None:
        if not value:
            self._error(path, "path must not be empty")
            return
        if self.workspace_root is None:
            return
        candidate = Path(value)
        resolved = candidate.resolve() if candidate.is_absolute() else (self.workspace_root / candidate).resolve()
        if not _is_relative_to(resolved, self.workspace_root):
            self._error(path, f"path escapes workspace root: {value}")
            return
        if must_exist and not resolved.exists():
            self._error(path, f"path does not exist: {value}")

    def _check_unique_id(self, value: str, path: str) -> None:
        if not value:
            return
        if value in self.seen_ids:
            self._error(path, f"duplicate id: {value}")
            return
        self.seen_ids.add(value)

    def _as_string(self, value: Any, path: str) -> str:
        if not isinstance(value, str):
            self._error(path, "must be a string")
            return ""
        return value

    def _as_bool(self, value: Any, path: str) -> bool:
        if not isinstance(value, bool):
            self._error(path, "must be a boolean")
            return False
        return value

    def _as_int(self, value: Any, path: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            self._error(path, "must be an integer")
            return 0
        return value

    def _as_positive_int(self, value: Any, path: str) -> int:
        number = self._as_int(value, path)
        if number < 1:
            self._error(path, "must be >= 1")
            return 1
        return number

    def _as_byte(self, value: Any, path: str) -> int:
        number = self._as_int(value, path)
        if not 0 <= number <= 255:
            self._error(path, "must be between 0 and 255")
            return 255
        return number

    def _as_positive_number(self, value: Any, path: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self._error(path, "must be a number")
            return 1.0
        number = float(value)
        if number <= 0:
            self._error(path, "must be > 0")
            return 1.0
        return number

    def _error(self, path: str, message: str) -> None:
        self.issues.append(ValidationIssue(severity="error", path=path, message=message))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
