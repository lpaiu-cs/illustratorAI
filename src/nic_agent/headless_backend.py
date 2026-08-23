from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Mapping

from nic_compiler.raster_ops import (
    draw_polyline_with_fallback,
    iter_tiles,
    parse_hex_color,
    rgba_to_native_bytes,
)

from nic_agent.simulator import HeadlessDocument, SimLayerNode, encode_png
from nic_agent.svg_raster import parse_svg, render_shapes_on_node


class HeadlessBackend:
    def __init__(self, output_root: Path | None = None) -> None:
        self.output_root = output_root
        self.document: HeadlessDocument | None = None
        self.warnings: list[str] = []

    def has_document(self) -> bool:
        return self.document is not None

    def find_layer_kind(self, layer_id: str) -> str | None:
        if self.document is None:
            return None
        node = self.document.find_layer(layer_id)
        return node.kind if node is not None else None

    def active_node_kind(self) -> str | None:
        if self.document is None:
            return None
        node = self.document.active_node()
        return node.kind if node is not None else None

    def export_ready(self) -> bool:
        return self.output_root is not None

    def op_create_document(self, body: Mapping[str, Any]) -> None:
        background = parse_hex_color(str(body.get("background_color", "#00000000")))
        self.document = HeadlessDocument(
            width=int(body["width"]),
            height=int(body["height"]),
            background_rgba=background,
            file_name=str(body.get("file_name", "untitled")),
        )

    def op_create_layer(self, body: Mapping[str, Any]) -> None:
        document = self._require_document()
        kind = str(body["kind"])
        if kind == "group":
            buffer = bytearray()
        else:
            buffer = bytearray(document.width * document.height * 4)
        node = SimLayerNode(
            layer_id=str(body["layer_id"]),
            name=str(body["name"]),
            kind=kind,
            width=document.width,
            height=document.height,
            buffer=buffer,
            visible=bool(body.get("visible", True)),
            opacity=float(body.get("opacity", 1.0)),
            dirty=document.dirty,
            parent_id=str(body["parent_id"]) if body.get("parent_id") else None,
        )
        document.layers.append(node)
        document.active_layer_id = node.layer_id

    def op_select_layer(self, body: Mapping[str, Any]) -> None:
        assert self.document is not None
        self.document.active_layer_id = str(body["layer_id"])

    def op_fill_rect(self, body: Mapping[str, Any]) -> None:
        node = self._require_active_paint_node()
        color = parse_hex_color(str(body["color"]))
        solid = rgba_to_native_bytes(color)
        x = int(body["x"])
        y = int(body["y"])
        width = int(body["width"])
        height = int(body["height"])
        for tile_x, tile_y, tile_w, tile_h in iter_tiles(x, y, width, height):
            tile = solid * (tile_w * tile_h)
            if not node.setPixelData(tile, tile_x, tile_y, tile_w, tile_h):
                raise RuntimeError(f"fill_rect outside canvas at {tile_x},{tile_y}")

    def op_stroke(self, body: Mapping[str, Any]) -> None:
        node = self._require_active_paint_node()
        color = parse_hex_color(str(body["color"]))
        if "opacity" in body:
            r, g, b, a = color
            color = (r, g, b, round(a * float(body["opacity"])))
        size = float(body["size"])
        points = [(float(point[0]), float(point[1])) for point in body["points"]]
        draw_polyline_with_fallback(node, points, color, size)

    def op_add_svg(self, body: Mapping[str, Any]) -> None:
        node = self._require_active_vector_node()
        content = parse_svg(str(body["svg"]))
        self.warnings.extend(f"svg:{item}" for item in content.unsupported)
        touched = render_shapes_on_node(node, content)
        if touched is not None:
            document = self._require_document()
            document.dirty.add(*touched)

    def op_set_layer_properties(self, body: Mapping[str, Any]) -> None:
        assert self.document is not None
        node = self.document.find_layer(str(body["layer_id"]))
        assert node is not None
        if "visible" in body:
            node.visible = bool(body["visible"])
        if "opacity" in body:
            node.opacity = float(body["opacity"])
        if "name" in body:
            node.name = str(body["name"])

    def op_export_png(self, body: Mapping[str, Any]) -> None:
        document = self._require_document()
        if self.output_root is None:
            raise RuntimeError("no_output_root")
        png = encode_png(document.width, document.height, document.composite_rgba())
        target = self.output_root / str(body["file_name"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(png)

    def observe(self) -> dict[str, Any]:
        if self.document is None:
            warnings = self.warnings
            self.warnings = []
            return {
                "canvas": None,
                "active_layer": None,
                "layers": [],
                "changed_bbox": None,
                "warnings": warnings,
            }
        observation = self.document.observe()
        observation["warnings"] = self.warnings
        self.warnings = []
        return observation

    def fingerprint(self) -> str | None:
        if self.document is None:
            return None
        return self.document.fingerprint()

    def canvas_png_base64(self) -> str | None:
        if self.document is None:
            return None
        png = encode_png(
            self.document.width, self.document.height, self.document.composite_rgba()
        )
        return base64.b64encode(png).decode("ascii")

    def _require_document(self) -> HeadlessDocument:
        if self.document is None:
            raise RuntimeError("no_document")
        return self.document

    def _require_active_paint_node(self) -> SimLayerNode:
        document = self._require_document()
        node = document.active_node()
        if node is None or node.kind != "paint":
            raise RuntimeError("no_active_paint_layer")
        return node

    def _require_active_vector_node(self) -> SimLayerNode:
        document = self._require_document()
        node = document.active_node()
        if node is None or node.kind != "vector":
            raise RuntimeError("no_active_vector_layer")
        return node
