from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from typing import Any

from nic_compiler.raster_ops import (
    draw_polyline_with_fallback,
    iter_tiles,
    parse_hex_color,
    rgba_to_native_bytes,
)


@dataclass(slots=True)
class DirtyRect:
    bbox: tuple[int, int, int, int] | None = None

    def add(self, x: int, y: int, width: int, height: int) -> None:
        if self.bbox is None:
            self.bbox = (x, y, width, height)
            return
        left, top, old_width, old_height = self.bbox
        right = max(left + old_width, x + width)
        bottom = max(top + old_height, y + height)
        self.bbox = (min(left, x), min(top, y), right - min(left, x), bottom - min(top, y))

    def take(self) -> tuple[int, int, int, int] | None:
        bbox, self.bbox = self.bbox, None
        return bbox


@dataclass(slots=True)
class SimLayerNode:
    layer_id: str
    name: str
    kind: str
    width: int
    height: int
    buffer: bytearray
    visible: bool = True
    opacity: float = 1.0
    dirty: DirtyRect | None = None
    parent_id: str | None = None

    def type(self) -> str:
        return "paintlayer" if self.kind == "paint" else f"{self.kind}layer"

    def pixelData(self, x: int, y: int, width: int, height: int) -> bytes:
        out = bytearray(width * height * 4)
        left = max(x, 0)
        top = max(y, 0)
        right = min(x + width, self.width)
        bottom = min(y + height, self.height)
        for row in range(top, bottom):
            src_start = (row * self.width + left) * 4
            length = (right - left) * 4
            dst_start = ((row - y) * width + (left - x)) * 4
            out[dst_start : dst_start + length] = self.buffer[src_start : src_start + length]
        return bytes(out)

    def setPixelData(self, data: bytes, x: int, y: int, width: int, height: int) -> bool:
        left = max(x, 0)
        top = max(y, 0)
        right = min(x + width, self.width)
        bottom = min(y + height, self.height)
        if right <= left or bottom <= top:
            return False
        for row in range(top, bottom):
            src_start = ((row - y) * width + (left - x)) * 4
            length = (right - left) * 4
            dst_start = (row * self.width + left) * 4
            self.buffer[dst_start : dst_start + length] = data[src_start : src_start + length]
        if self.dirty is not None:
            self.dirty.add(left, top, right - left, bottom - top)
        return True


@dataclass(slots=True)
class HeadlessDocument:
    width: int
    height: int
    background_rgba: tuple[int, int, int, int]
    file_name: str = "untitled"
    layers: list[SimLayerNode] = field(default_factory=list)
    active_layer_id: str | None = None
    dirty: DirtyRect = field(default_factory=DirtyRect)

    def find_layer(self, layer_id: str) -> SimLayerNode | None:
        return next((layer for layer in self.layers if layer.layer_id == layer_id), None)

    def active_node(self) -> SimLayerNode | None:
        if self.active_layer_id is None:
            return None
        return self.find_layer(self.active_layer_id)

    def composite_bgra(self) -> bytes:
        out = bytearray(rgba_to_native_bytes(self.background_rgba) * (self.width * self.height))
        known_ids = {layer.layer_id for layer in self.layers}
        children: dict[str, list[SimLayerNode]] = {}
        roots: list[SimLayerNode] = []
        for layer in self.layers:
            if layer.parent_id in known_ids:
                children.setdefault(layer.parent_id, []).append(layer)
            else:
                roots.append(layer)

        def paint(layer: SimLayerNode, visible_mult: bool, opacity_mult: float) -> None:
            effective_visible = layer.visible and visible_mult
            effective_opacity = layer.opacity * opacity_mult
            if not effective_visible or effective_opacity <= 0.0:
                return
            if layer.kind != "group":
                self._blend_buffer(out, layer, effective_opacity)
            for child in children.get(layer.layer_id, ()):
                paint(child, effective_visible, effective_opacity)

        for root_layer in roots:
            paint(root_layer, True, 1.0)
        return bytes(out)

    def _blend_buffer(self, out: bytearray, layer: SimLayerNode, alpha_scale: float) -> None:
        buffer = layer.buffer
        for offset in range(0, len(out), 4):
            src_alpha = buffer[offset + 3]
            if src_alpha == 0:
                continue
            sa = (src_alpha / 255.0) * alpha_scale
            dst_alpha = out[offset + 3] / 255.0
            out_alpha = sa + dst_alpha * (1.0 - sa)
            if out_alpha <= 0.0:
                continue
            keep = dst_alpha * (1.0 - sa)
            out[offset] = round((buffer[offset] * sa + out[offset] * keep) / out_alpha)
            out[offset + 1] = round(
                (buffer[offset + 1] * sa + out[offset + 1] * keep) / out_alpha
            )
            out[offset + 2] = round(
                (buffer[offset + 2] * sa + out[offset + 2] * keep) / out_alpha
            )
            out[offset + 3] = round(out_alpha * 255.0)

    def composite_rgba(self) -> bytes:
        bgra = self.composite_bgra()
        rgba = bytearray(bgra)
        rgba[0::4], rgba[2::4] = bgra[2::4], bgra[0::4]
        return bytes(rgba)

    def fingerprint(self) -> str:
        return f"crc32:{zlib.crc32(self.composite_bgra()) & 0xFFFFFFFF:08x}"

    def observe(self) -> dict[str, Any]:
        changed = self.dirty.take()
        return {
            "canvas": {"width": self.width, "height": self.height},
            "active_layer": self.active_layer_id,
            "layers": [
                {
                    "id": layer.layer_id,
                    "name": layer.name,
                    "kind": layer.kind,
                    "visible": layer.visible,
                    "opacity": layer.opacity,
                    "parent_id": layer.parent_id,
                }
                for layer in self.layers
            ],
            "changed_bbox": list(changed) if changed else None,
            "fingerprint": self.fingerprint(),
        }


def encode_png(width: int, height: int, rgba: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    stride = width * 4
    raw = bytearray()
    for row in range(height):
        raw.append(0)
        raw += rgba[row * stride : (row + 1) * stride]
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
