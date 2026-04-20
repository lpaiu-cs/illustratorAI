from __future__ import annotations

from math import ceil
from typing import Any, Iterable, Sequence

from nic_ir.models import DocumentSpec, LayerSpec, OperationSpec

DEFAULT_TILE_SIZE = 256


def parse_hex_color(value: str) -> tuple[int, int, int, int]:
    text = value.strip()
    if text.lower() == "transparent":
        return (0, 0, 0, 0)
    if not text.startswith("#"):
        raise ValueError(f"unsupported color format: {value}")
    hex_value = text[1:]
    if len(hex_value) == 3:
        hex_value = "".join(char * 2 for char in hex_value) + "FF"
    elif len(hex_value) == 4:
        hex_value = "".join(char * 2 for char in hex_value)
    elif len(hex_value) == 6:
        hex_value += "FF"
    elif len(hex_value) != 8:
        raise ValueError(f"unsupported color format: {value}")
    try:
        rgba = tuple(int(hex_value[index : index + 2], 16) for index in range(0, 8, 2))
    except ValueError as exc:
        raise ValueError(f"unsupported color format: {value}") from exc
    return rgba  # type: ignore[return-value]


def rgba_to_native_bytes(rgba: tuple[int, int, int, int]) -> bytes:
    r, g, b, a = rgba
    # Krita's RGBA channels are typically stored as BGRA in memory for U8 nodes.
    return bytes((b, g, r, a))


def ensure_writable_paint_node(node: Any) -> None:
    node_type = node.type() if hasattr(node, "type") else ""
    if node_type and node_type not in {"paintlayer"}:
        raise TypeError(f"setPixelData() target must be a writable paint layer, got {node_type}")


def iter_tiles(x: int, y: int, width: int, height: int, tile_size: int = DEFAULT_TILE_SIZE):
    for tile_y in range(y, y + height, tile_size):
        remaining_h = min(tile_size, y + height - tile_y)
        for tile_x in range(x, x + width, tile_size):
            remaining_w = min(tile_size, x + width - tile_x)
            yield tile_x, tile_y, remaining_w, remaining_h


def apply_raster_ops(
    node: Any,
    layer: LayerSpec,
    document: Any,
    document_spec: DocumentSpec,
    session: Any,
    report: Any,
    layer_path: str,
) -> None:
    for op in layer.ops:
        try:
            if op.type == "fill_solid":
                apply_fill_solid(node, document_spec, op)
            elif op.type == "put_pixels":
                apply_put_pixels(node, op)
            elif op.type == "import_png":
                apply_import_png(node, document, op, session)
            elif op.type == "brush_line":
                apply_brush_line(node, document, op, session, report, layer_path)
            elif op.type == "brush_path":
                apply_brush_path(node, document, op, session, report, layer_path)
            else:
                report.add_unsupported(
                    "unsupported_raster_op",
                    f"Unsupported raster op: {op.type}",
                    path=layer_path,
                    details={"op": op.type},
                )
        except Exception as exc:
            report.add_error(
                "raster_op_failed",
                str(exc),
                path=layer_path,
                details={"op": op.type},
            )


def apply_fill_solid(node: Any, document_spec: DocumentSpec, op: OperationSpec) -> None:
    ensure_writable_paint_node(node)
    color = parse_hex_color(str(op.payload["color"]))
    x = int(op.payload.get("x", 0))
    y = int(op.payload.get("y", 0))
    width = int(op.payload.get("width", document_spec.width))
    height = int(op.payload.get("height", document_spec.height))
    solid_pixel = rgba_to_native_bytes(color)
    for tile_x, tile_y, tile_w, tile_h in iter_tiles(x, y, width, height):
        tile = solid_pixel * (tile_w * tile_h)
        if not node.setPixelData(tile, tile_x, tile_y, tile_w, tile_h):
            raise RuntimeError(
                f"setPixelData failed for fill_solid tile {tile_x},{tile_y},{tile_w},{tile_h}"
            )


def apply_put_pixels(node: Any, op: OperationSpec) -> None:
    ensure_writable_paint_node(node)
    rows = op.payload.get("rows", ())
    width = len(rows[0]) if rows else 0
    height = len(rows)
    payload = bytearray()
    for row in rows:
        for value in row:
            payload.extend(rgba_to_native_bytes(parse_hex_color(str(value))))
    x = int(op.payload.get("x", 0))
    y = int(op.payload.get("y", 0))
    if not node.setPixelData(bytes(payload), x, y, width, height):
        raise RuntimeError(f"setPixelData failed for put_pixels at {x},{y},{width},{height}")


def apply_import_png(node: Any, document: Any, op: OperationSpec, session: Any) -> None:
    ensure_writable_paint_node(node)
    raw_path = _resolve_resource_or_path(op)
    payload, width, height = session.load_external_pixels(
        raw_path,
        document.colorModel(),
        document.colorDepth(),
        document.colorProfile(),
    )
    x = int(op.payload.get("x", 0))
    y = int(op.payload.get("y", 0))
    if not node.setPixelData(payload, x, y, width, height):
        raise RuntimeError(f"setPixelData failed for import_png at {x},{y},{width},{height}")


def apply_brush_line(
    node: Any,
    document: Any,
    op: OperationSpec,
    session: Any,
    report: Any,
    layer_path: str,
) -> None:
    if hasattr(node, "paintLine") and session.configure_brush(document, dict(op.payload)):
        try:
            from PyQt5.QtCore import QPointF  # pragma: no cover - Krita runtime only
        except ImportError:  # pragma: no cover - Krita runtime only
            from PyQt6.QtCore import QPointF  # type: ignore
        start = QPointF(float(op.payload["from"][0]), float(op.payload["from"][1]))
        end = QPointF(float(op.payload["to"][0]), float(op.payload["to"][1]))
        node.paintLine(start, end)
        return
    report.add_warning(
        "brush_line_fallback",
        "brush_line API unavailable or view control missing, using pixel fallback",
        path=layer_path,
        details={"op": op.type},
    )
    color = parse_hex_color(str(op.payload["color"]))
    size = float(op.payload.get("size", 1.0))
    draw_polyline_with_fallback(node, [tuple(op.payload["from"]), tuple(op.payload["to"])], color, size)


def apply_brush_path(
    node: Any,
    document: Any,
    op: OperationSpec,
    session: Any,
    report: Any,
    layer_path: str,
) -> None:
    points = [tuple(point) for point in op.payload["points"]]
    if hasattr(node, "paintPath") and session.configure_brush(document, dict(op.payload)):
        report.add_unsupported(
            "brush_path_qpainterpath_missing",
            "paintPath exists but v0 does not construct QPainterPath objects automatically; using pixel fallback",
            path=layer_path,
            details={"op": op.type},
        )
    color = parse_hex_color(str(op.payload["color"]))
    size = float(op.payload.get("size", 1.0))
    draw_polyline_with_fallback(node, points, color, size)


def draw_polyline_with_fallback(
    node: Any,
    points: Sequence[tuple[int, int]],
    color: tuple[int, int, int, int],
    size: float,
) -> None:
    ensure_writable_paint_node(node)
    if len(points) < 2:
        return
    radius = max(1, int(ceil(size / 2.0)))
    xs = [int(point[0]) for point in points]
    ys = [int(point[1]) for point in points]
    left = min(xs) - radius
    top = min(ys) - radius
    width = max(xs) - min(xs) + radius * 2 + 1
    height = max(ys) - min(ys) + radius * 2 + 1
    existing = bytes(node.pixelData(left, top, width, height))
    if len(existing) != width * height * 4:
        existing = b"\x00" * (width * height * 4)
    canvas = bytearray(existing)
    for start, end in zip(points, points[1:]):
        for px, py in _bresenham(int(start[0]), int(start[1]), int(end[0]), int(end[1])):
            _stamp_circle(canvas, width, height, px - left, py - top, radius, color)
    if not node.setPixelData(bytes(canvas), left, top, width, height):
        raise RuntimeError(f"setPixelData failed for fallback stroke at {left},{top},{width},{height}")


def _stamp_circle(
    buffer: bytearray,
    width: int,
    height: int,
    cx: int,
    cy: int,
    radius: int,
    rgba: tuple[int, int, int, int],
) -> None:
    r_sq = radius * radius
    for y in range(max(0, cy - radius), min(height, cy + radius + 1)):
        for x in range(max(0, cx - radius), min(width, cx + radius + 1)):
            dx = x - cx
            dy = y - cy
            if dx * dx + dy * dy > r_sq:
                continue
            offset = (y * width + x) * 4
            _alpha_over(buffer, offset, rgba)


def _alpha_over(buffer: bytearray, offset: int, src_rgba: tuple[int, int, int, int]) -> None:
    src_r, src_g, src_b, src_a = src_rgba
    dst_b = buffer[offset]
    dst_g = buffer[offset + 1]
    dst_r = buffer[offset + 2]
    dst_a = buffer[offset + 3]
    src_alpha = src_a / 255.0
    dst_alpha = dst_a / 255.0
    out_alpha = src_alpha + dst_alpha * (1.0 - src_alpha)
    if out_alpha <= 0.0:
        buffer[offset : offset + 4] = b"\x00\x00\x00\x00"
        return
    out_r = int(round((src_r * src_alpha + dst_r * dst_alpha * (1.0 - src_alpha)) / out_alpha))
    out_g = int(round((src_g * src_alpha + dst_g * dst_alpha * (1.0 - src_alpha)) / out_alpha))
    out_b = int(round((src_b * src_alpha + dst_b * dst_alpha * (1.0 - src_alpha)) / out_alpha))
    out_a = int(round(out_alpha * 255.0))
    buffer[offset : offset + 4] = bytes((out_b, out_g, out_r, out_a))


def _bresenham(x0: int, y0: int, x1: int, y1: int):
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        yield x0, y0
        if x0 == x1 and y0 == y1:
            break
        e2 = err * 2
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _resolve_resource_or_path(op: OperationSpec) -> str:
    if "path" in op.payload:
        return str(op.payload["path"])
    if "resource_path" in op.payload:
        return str(op.payload["resource_path"])
    raise ValueError("operation requires a concrete path")
