from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from nic_compiler.krita_session import KritaSession
from nic_compiler.raster_ops import (
    draw_polyline_with_fallback,
    ensure_writable_paint_node,
    iter_tiles,
    parse_hex_color,
    rgba_to_native_bytes,
)
from nic_agent.simulator import DirtyRect
from nic_agent.svg_raster import parse_svg
from nic_ir.models import DocumentSpec


class KritaBackend:
    def __init__(self, session: KritaSession, output_root: Path | None = None) -> None:
        self.session = session
        self.output_root = output_root
        self.document: Any | None = None
        self._nodes: dict[str, Any] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        self._order: list[str] = []
        self._active_id: str | None = None
        self._dirty = DirtyRect()
        self.warnings: list[str] = []

    def has_document(self) -> bool:
        return self.document is not None

    def find_layer_kind(self, layer_id: str) -> str | None:
        meta = self._meta.get(layer_id)
        return str(meta["kind"]) if meta is not None else None

    def active_node_kind(self) -> str | None:
        if self._active_id is None:
            return None
        return self.find_layer_kind(self._active_id)

    def export_ready(self) -> bool:
        return self.output_root is not None

    def op_create_document(self, body: Mapping[str, Any]) -> None:
        spec = DocumentSpec(
            width=int(body["width"]),
            height=int(body["height"]),
            dpi=int(body.get("dpi", 72)),
            color_model="RGBA",
            color_depth="U8",
            background_color=str(body.get("background_color", "#00000000")),
            file_name=str(body.get("file_name", "agent_session")),
        )
        self.document = self.session.create_document(spec)
        self.session.present_document(self.document)
        self._nodes.clear()
        self._meta.clear()
        self._order.clear()
        self._dirty = DirtyRect()

    def op_create_layer(self, body: Mapping[str, Any]) -> None:
        document = self._require_document()
        name = str(body["name"])
        kind = str(body["kind"])
        if kind == "group":
            node = document.createGroupLayer(name)
        elif kind == "vector":
            node = document.createVectorLayer(name)
        else:
            node = document.createNode(name, "paintlayer")
        if node is None:
            raise RuntimeError(f"Krita failed to create {kind} layer: {name}")
        parent_id = str(body["parent_id"]) if body.get("parent_id") else None
        if parent_id is not None and parent_id not in self._nodes:
            raise RuntimeError(f"unknown_parent_layer: {parent_id}")
        parent = self._nodes[parent_id] if parent_id is not None else document.rootNode()
        if not hasattr(parent, "addChildNode"):
            raise RuntimeError("parent does not support addChildNode")
        parent.addChildNode(node, None)
        if "opacity" in body and hasattr(node, "setOpacity"):
            node.setOpacity(int(round(float(body["opacity"]) * 255)))
        if "visible" in body and hasattr(node, "setVisible"):
            node.setVisible(bool(body["visible"]))
        layer_id = str(body["layer_id"])
        self._nodes[layer_id] = node
        self._meta[layer_id] = {
            "name": name,
            "kind": kind,
            "visible": bool(body.get("visible", True)),
            "opacity": float(body.get("opacity", 1.0)),
            "parent_id": parent_id,
        }
        self._order.append(layer_id)
        self._active_id = layer_id

    def op_add_svg(self, body: Mapping[str, Any]) -> None:
        node = self._require_active_vector_node()
        svg_text = str(body["svg"])
        content = parse_svg(svg_text)
        self.warnings.extend(f"svg:{item}" for item in content.unsupported)
        if not hasattr(node, "addShapesFromSvg"):
            raise RuntimeError("svg_injection_unavailable on this runtime")
        if not node.addShapesFromSvg(svg_text):
            raise RuntimeError("addShapesFromSvg rejected the SVG fragment")
        xs = [point[0] for shape in content.shapes for point in shape.points]
        ys = [point[1] for shape in content.shapes for point in shape.points]
        if xs and ys:
            radius = max((shape.width for shape in content.shapes), default=1.0)
            self._mark_dirty(
                int(min(xs) - radius),
                int(min(ys) - radius),
                int(max(xs) - min(xs)) + int(2 * radius) + 1,
                int(max(ys) - min(ys)) + int(2 * radius) + 1,
            )
        self.session.wait_for_done(self.document)

    def op_select_layer(self, body: Mapping[str, Any]) -> None:
        assert self.document is not None
        layer_id = str(body["layer_id"])
        node = self._require_node(layer_id)
        if hasattr(self.document, "setActiveNode"):
            self.document.setActiveNode(node)
        self._active_id = layer_id

    def op_fill_rect(self, body: Mapping[str, Any]) -> None:
        node = self._require_active_paint_node()
        ensure_writable_paint_node(node)
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
        self._mark_dirty(x, y, width, height)
        self.session.wait_for_done(self.document)

    def op_stroke(self, body: Mapping[str, Any]) -> None:
        node = self._require_active_paint_node()
        color = parse_hex_color(str(body["color"]))
        size = float(body["size"])
        if "opacity" in body:
            r, g, b, a = color
            color = (r, g, b, round(a * float(body["opacity"])))
        points = [(float(point[0]), float(point[1])) for point in body["points"]]
        draw_polyline_with_fallback(node, points, color, size)
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        radius = max(1, int(round(size / 2.0)) + 1)
        left = int(min(xs)) - radius
        top = int(min(ys)) - radius
        width = int(max(xs) - min(xs)) + radius * 2 + 1
        height = int(max(ys) - min(ys)) + radius * 2 + 1
        self._mark_dirty(left, top, width, height)
        self.session.wait_for_done(self.document)

    def op_set_layer_properties(self, body: Mapping[str, Any]) -> None:
        assert self.document is not None
        layer_id = str(body["layer_id"])
        node = self._require_node(layer_id)
        meta = self._meta[layer_id]
        if "visible" in body:
            node.setVisible(bool(body["visible"]))
            meta["visible"] = bool(body["visible"])
        if "opacity" in body:
            value = float(body["opacity"])
            node.setOpacity(int(round(value * 255)))
            meta["opacity"] = value
        if "name" in body:
            name = str(body["name"])
            node.setName(name)
            meta["name"] = name
        self.session.wait_for_done(self.document)

    def op_export_png(self, body: Mapping[str, Any]) -> None:
        document = self._require_document()
        if self.output_root is None:
            raise RuntimeError("no_output_root")
        self.session.export_document(document, Path(self.output_root) / str(body["file_name"]))

    def observe(self) -> dict[str, Any]:
        changed = self._dirty.take()
        warnings = self.warnings
        self.warnings = []
        return {
            "canvas": (
                {"width": self.document.width(), "height": self.document.height()}
                if self.document is not None
                else None
            ),
            "active_layer": self._active_id,
            "layers": [
                {"id": layer_id, **self._meta[layer_id]} for layer_id in self._order
            ],
            "changed_bbox": list(changed) if changed else None,
            "fingerprint": None,
            "warnings": warnings,
        }

    def fingerprint(self) -> str | None:
        return None

    def canvas_png_base64(self) -> str | None:
        document = self._require_document()
        import base64 as _base64
        import tempfile

        handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        handle.close()
        try:
            try:
                self.session.export_document(document, Path(handle.name))
            except RuntimeError:  # export failed: no canvas image this turn
                return None
            return _base64.b64encode(Path(handle.name).read_bytes()).decode("ascii")
        finally:
            Path(handle.name).unlink(missing_ok=True)

    def _require_document(self) -> Any:
        if self.document is None:
            raise RuntimeError("no_document")
        return self.document

    def _require_node(self, layer_id: str) -> Any:
        node = self._nodes.get(layer_id)
        if node is None:
            raise RuntimeError(f"unknown_layer: {layer_id}")
        return node

    def _require_active_paint_node(self) -> Any:
        document = self._require_document()
        if self._active_id is None:
            raise RuntimeError("no_active_paint_layer")
        node = self._nodes[self._active_id]
        if self.active_node_kind() != "paint":
            raise RuntimeError("active_layer_not_paintable")
        ensure_writable_paint_node(node)
        assert document is not None
        return node

    def _require_active_vector_node(self) -> Any:
        document = self._require_document()
        if self._active_id is None:
            raise RuntimeError("no_active_vector_layer")
        node = self._nodes[self._active_id]
        if self.active_node_kind() != "vector":
            raise RuntimeError("active_layer_not_vector")
        assert document is not None
        return node

    def _mark_dirty(self, x: int, y: int, width: int, height: int) -> None:
        canvas_left = max(x, 0)
        canvas_top = max(y, 0)
        canvas_right = min(x + width, self.document.width())
        canvas_bottom = min(y + height, self.document.height())
        if canvas_right > canvas_left and canvas_bottom > canvas_top:
            self._dirty.add(canvas_left, canvas_top, canvas_right - canvas_left, canvas_bottom - canvas_top)
