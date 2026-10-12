from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from nic_compiler.raster_ops import _alpha_over, _bresenham, _stamp_circle, parse_hex_color

CURVE_SAMPLES = 16
ARC_SAMPLE_DEGREES = 12.0
MAX_ARC_SAMPLES = 64

NAMED_COLORS = {
    "black": "#000000",
    "white": "#FFFFFF",
    "red": "#FF0000",
    "green": "#008000",
    "lime": "#00FF00",
    "blue": "#0000FF",
    "yellow": "#FFFF00",
    "cyan": "#00FFFF",
    "magenta": "#FF00FF",
    "gray": "#808080",
    "grey": "#808080",
    "orange": "#FFA500",
    "purple": "#800080",
    "brown": "#A52A2A",
    "pink": "#FFC0CB",
}

_PATH_TOKEN = re.compile(
    r"([MmLlHhVvCcQqSsTtAaZz])|([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)"
)
_ARG_COUNT = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "Q": 4, "S": 4, "T": 2, "A": 7}
_NUMBER = r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"


@dataclass(slots=True, frozen=True)
class SvgShape:
    points: tuple[tuple[float, float], ...]
    closed: bool
    stroke: tuple[int, int, int, int] | None
    fill: tuple[int, int, int, int] | None
    width: float


@dataclass(slots=True, frozen=True)
class SvgContent:
    shapes: tuple[SvgShape, ...]
    unsupported: tuple[str, ...]


def parse_svg(svg_text: str) -> SvgContent:
    root = ET.fromstring(svg_text)
    shapes: list[SvgShape] = []
    unsupported: list[str] = []
    _walk_element(root, {"fill": None, "stroke": None, "width": 1.0}, shapes, unsupported)
    return SvgContent(tuple(shapes), tuple(dict.fromkeys(unsupported)))


def _walk_element(element, style, shapes, unsupported) -> None:
    tag = element.tag.rsplit("}", 1)[-1].lower()
    if element.get("transform"):
        unsupported.append(f"transform:{tag}")
    child_style = {
        "fill": element.get("fill", style["fill"]),
        "stroke": element.get("stroke", style["stroke"]),
        "width": _number_attr(element, "stroke-width", style["width"]),
    }
    if tag in {"g", "svg", "defs"}:
        for child in element:
            _walk_element(child, child_style, shapes, unsupported)
        return
    if tag in {"rect", "circle", "ellipse", "line", "polyline", "polygon"}:
        shape = _shape_from_element(element, tag, child_style)
        if shape is not None:
            shapes.append(shape)
        return
    if tag == "path":
        try:
            subpaths = _parse_path_d(element.get("d", ""))
        except ValueError as exc:
            unsupported.append(f"path:{exc}")
            return
        fill = resolve_fill(child_style, closed=True)
        stroke = resolve_stroke(child_style)
        width = max(0.5, float(child_style["width"]))
        for points, closed in subpaths:
            shapes.append(SvgShape(tuple(points), closed, stroke, fill if closed else None, width))
        return
    unsupported.append(tag)


def resolve_fill(style, closed: bool):
    color = _parse_color(style["fill"])
    if color is not None:
        return color
    return _parse_color("black") if closed and style["fill"] is None else None


def resolve_stroke(style):
    stroke = _parse_color(style["stroke"])
    if stroke is None and style["fill"] is None:
        stroke = _parse_color("black")
    return stroke


def _shape_from_element(element, tag, style) -> SvgShape | None:
    width = max(0.5, float(style["width"]))
    if tag == "rect":
        x = _number_attr(element, "x", 0.0)
        y = _number_attr(element, "y", 0.0)
        w = _number_attr(element, "width", 0.0)
        h = _number_attr(element, "height", 0.0)
        if w <= 0 or h <= 0:
            return None
        points = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        closed = True
    elif tag == "circle":
        cx = _number_attr(element, "cx", 0.0)
        cy = _number_attr(element, "cy", 0.0)
        r = _number_attr(element, "r", 0.0)
        if r <= 0:
            return None
        points = _sample_ellipse(cx, cy, r, r)
        closed = True
    elif tag == "ellipse":
        cx = _number_attr(element, "cx", 0.0)
        cy = _number_attr(element, "cy", 0.0)
        rx = _number_attr(element, "rx", _number_attr(element, "ry", 0.0))
        ry = _number_attr(element, "ry", 0.0)
        if rx <= 0 or ry <= 0:
            return None
        points = _sample_ellipse(cx, cy, rx, ry)
        closed = True
    elif tag == "line":
        points = [
            (_number_attr(element, "x1", 0.0), _number_attr(element, "y1", 0.0)),
            (_number_attr(element, "x2", 0.0), _number_attr(element, "y2", 0.0)),
        ]
        closed = False
    else:
        raw_points = _points_attr(element.get("points", ""))
        if len(raw_points) < 2:
            return None
        points = raw_points
        closed = tag == "polygon"
    return SvgShape(
        tuple(points),
        closed,
        resolve_stroke(style),
        resolve_fill(style, closed),
        width,
    )


def _sample_ellipse(cx, cy, rx, ry, segments: int = 48):
    return [
        (
            cx + rx * math.cos(2 * math.pi * index / segments),
            cy + ry * math.sin(2 * math.pi * index / segments),
        )
        for index in range(segments)
    ]


def _points_attr(raw: str):
    numbers = [float(value) for value in re.findall(_NUMBER, raw or "")]
    return list(zip(numbers[0::2], numbers[1::2]))


def _parse_path_d(d: str):
    tokens: list = []
    for letter, number in _PATH_TOKEN.findall(d):
        tokens.append(letter if letter else float(number))
    subpaths: list[tuple[list, bool]] = []
    points: list[tuple[float, float]] = []
    current = (0.0, 0.0)
    subpath_start: tuple[float, float] | None = None
    command = ""
    relative = False
    index = 0

    def flush(closed: bool) -> None:
        nonlocal points
        if len(points) >= 2:
            subpaths.append((points, closed))
        points = []

    def take(count: int):
        nonlocal index
        values = tokens[index : index + count]
        if len(values) < count or any(isinstance(value, str) for value in values):
            raise ValueError("incomplete arguments")
        index += count
        return values

    while index < len(tokens):
        token = tokens[index]
        if isinstance(token, str):
            letter = token.upper()
            relative = token.islower()
            index += 1
            if letter == "Z":
                if points and subpath_start is not None:
                    points.append(subpath_start)
                    current = subpath_start
                flush(True)
                subpath_start = None
                continue
            if letter in ("S", "T"):
                raise ValueError(f"unsupported path command {letter}")
            command = letter
        if not command:
            raise ValueError("coordinates before command")

        if command == "M":
            x, y = take(2)
            point = (current[0] + x, current[1] + y) if relative else (x, y)
            flush(False)
            points.append(point)
            current = point
            subpath_start = point
            command = "L" if not relative else "l"
        elif command == "L":
            x, y = take(2)
            current = (current[0] + x, current[1] + y) if relative else (x, y)
            points.append(current)
        elif command == "H":
            (value,) = take(1)
            current = (current[0] + value, current[1]) if relative else (value, current[1])
            points.append(current)
        elif command == "V":
            (value,) = take(1)
            current = (current[0], current[1] + value) if relative else (current[0], value)
            points.append(current)
        elif command == "C":
            a, b, c, e, f, g = take(6)
            p1, p2, p3 = ((a, b), (c, e), (f, g))
            if relative:
                p1 = (p1[0] + current[0], p1[1] + current[1])
                p2 = (p2[0] + current[0], p2[1] + current[1])
                p3 = (p3[0] + current[0], p3[1] + current[1])
            points.extend(_cubic_points(current, p1, p2, p3))
            current = p3
        elif command == "Q":
            a, b, c, e = take(4)
            p1, p2 = ((a, b), (c, e))
            if relative:
                p1 = (p1[0] + current[0], p1[1] + current[1])
                p2 = (p2[0] + current[0], p2[1] + current[1])
            points.extend(_quadratic_points(current, p1, p2))
            current = p2
        elif command == "A":
            rx, ry, rotation, large, sweep, x, y = take(7)
            end = (current[0] + x, current[1] + y) if relative else (x, y)
            points.extend(
                _arc_points(current, end, abs(rx), abs(ry), rotation, large != 0, sweep != 0)
            )
            current = end
        else:
            raise ValueError(f"unsupported path command {command}")
    flush(False)
    return subpaths


def _number_attr(element, name, default=None):
    raw = element.get(name)
    if raw is None:
        return default
    match = re.search(_NUMBER, raw)
    return float(match.group(0)) if match else default


def _parse_color(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text == "none":
        return None
    rgb_match = re.match(r"rgba?\(([^)]+)\)", text)
    if rgb_match:
        numbers = [float(number) for number in re.findall(_NUMBER, rgb_match.group(1))]
        if len(numbers) >= 3:
            channels = [
                max(0, min(255, round(channel))) for channel in numbers[:3]
            ] + [255]
            # Only a 4th component is alpha; rgb(r, g, b) stays opaque.
            alpha_match = len(numbers) >= 4 and re.search(
                r"[/,\s]+(\d*\.?\d+)\s*\)?$", rgb_match.group(1)
            )
            if alpha_match:
                alpha_value = float(alpha_match.group(1))
                channels[3] = round(alpha_value * 255 if alpha_value <= 1 else alpha_value)
            return tuple(channels)
        return None
    if text in NAMED_COLORS:
        text = NAMED_COLORS[text]
    try:
        return parse_hex_color(text)
    except ValueError:
        return None


def _cubic_points(p0, p1, p2, p3, samples: int = CURVE_SAMPLES):
    points = []
    for step in range(1, samples + 1):
        t = step / samples
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        points.append((x, y))
    return points


def _quadratic_points(p0, p1, p2, samples: int = CURVE_SAMPLES):
    points = []
    for step in range(1, samples + 1):
        t = step / samples
        u = 1 - t
        x = u**2 * p0[0] + 2 * u * t * p1[0] + t**2 * p2[0]
        y = u**2 * p0[1] + 2 * u * t * p1[1] + t**2 * p2[1]
        points.append((x, y))
    return points


def _arc_points(start, end, rx, ry, rotation_degrees, large_arc, sweep):
    if rx == 0 or ry == 0 or start == end:
        return [end]
    phi = math.radians(rotation_degrees % 360.0)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx = (start[0] - end[0]) / 2.0
    dy = (start[1] - end[1]) / 2.0
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy
    lambda_sum = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if lambda_sum > 1.0:
        scale = math.sqrt(lambda_sum)
        rx *= scale
        ry *= scale
    sign = 1.0 if large_arc != sweep else -1.0
    numerator = rx**2 * ry**2 - rx**2 * y1p**2 - ry**2 * x1p**2
    denominator = rx**2 * y1p**2 + ry**2 * x1p**2
    coefficient = sign * math.sqrt(max(0.0, numerator / denominator)) if denominator else 0.0
    cxp = coefficient * rx * y1p / ry
    cyp = -coefficient * ry * x1p / rx
    center = (
        cos_phi * cxp - sin_phi * cyp + (start[0] + end[0]) / 2.0,
        sin_phi * cxp + cos_phi * cyp + (start[1] + end[1]) / 2.0,
    )
    theta_1 = math.atan2((y1p - cyp) / ry, (x1p - cxp) / rx)
    theta_2 = math.atan2((-y1p - cyp) / ry, (-x1p - cxp) / rx)
    delta = theta_2 - theta_1
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    segments = min(MAX_ARC_SAMPLES, max(4, int(abs(math.degrees(delta)) / ARC_SAMPLE_DEGREES)))
    points = []
    for step in range(1, segments + 1):
        theta = theta_1 + delta * step / segments
        px = cos_phi * rx * math.cos(theta) - sin_phi * ry * math.sin(theta) + center[0]
        py = sin_phi * rx * math.cos(theta) + cos_phi * ry * math.sin(theta) + center[1]
        points.append((px, py))
    return points


SUPERSAMPLE = 4


def render_shapes_on_node(node, content: SvgContent) -> tuple[int, int, int, int] | None:
    if not content.shapes:
        return None
    all_points = [point for shape in content.shapes for point in shape.points]
    radius = max(
        (math.ceil(shape.width / 2.0) for shape in content.shapes if shape.stroke),
        default=1,
    )
    min_x = min(point[0] for point in all_points) - radius
    min_y = min(point[1] for point in all_points) - radius
    max_x = max(point[0] for point in all_points) + radius
    max_y = max(point[1] for point in all_points) + radius
    left = max(int(math.floor(min_x)), 0)
    top = max(int(math.floor(min_y)), 0)
    right = min(int(math.ceil(max_x)), node.width)
    bottom = min(int(math.ceil(max_y)), node.height)
    if right <= left or bottom <= top:
        return None
    block_width = right - left
    block_height = bottom - top
    scale = SUPERSAMPLE
    super_width = block_width * scale
    super_height = block_height * scale
    canvas = bytearray(super_width * super_height * 4)

    def stamp(x: float, y: float, rgba, size: float) -> None:
        ix, iy = int(round(x)), int(round(y))
        radius_int = max(1, int(math.ceil(size / 2.0)))
        _stamp_circle(canvas, super_width, super_height, ix, iy, radius_int, rgba)

    # SVG paint order: each shape's fill then its stroke, before the next shape.
    for shape in content.shapes:
        if shape.fill is not None and shape.closed:
            scaled_points = [
                ((x - left) * scale, (y - top) * scale) for x, y in shape.points
            ]
            for y, span_start, span_end in _polygon_spans(scaled_points):
                row = int(y)
                if not 0 <= row < super_height:  # shape extends past the canvas edge
                    continue
                for x in range(max(span_start, 0), min(span_end + 1, super_width)):
                    offset = (row * super_width + x) * 4
                    _alpha_over(canvas, offset, shape.fill)
        if shape.stroke is None:
            continue
        outline = list(shape.points)
        if shape.closed:
            outline.append(outline[0])
        scaled_outline = [((x - left) * scale, (y - top) * scale) for x, y in outline]
        stroke_width = shape.width * scale
        for start, end in zip(scaled_outline, scaled_outline[1:]):
            steps = max(abs(end[0] - start[0]), abs(end[1] - start[1]))
            count = max(1, int(steps))
            for step_index in range(count + 1):
                ratio = step_index / count
                sx = start[0] + (end[0] - start[0]) * ratio
                sy = start[1] + (end[1] - start[1]) * ratio
                stamp(sx, sy, shape.stroke, stroke_width)

    _downsample_onto_node(
        node,
        canvas,
        super_width,
        left,
        top,
        block_width,
        block_height,
        scale,
    )
    return (left, top, block_width, block_height)


def _downsample_onto_node(node, canvas, super_width, left, top, width, height, scale):
    region = bytearray(node.pixelData(left, top, width, height))
    if len(region) != width * height * 4:
        region = bytearray(width * height * 4)
    denom = scale * scale * 255.0
    for row in range(height):
        for column in range(width):
            total_alpha = 0
            totals = [0, 0, 0]
            for sub_y in range(scale):
                base = ((row * scale + sub_y) * super_width + column * scale) * 4
                for sub_x in range(scale):
                    offset = base + sub_x * 4
                    alpha = canvas[offset + 3]
                    total_alpha += alpha
                    for channel in range(3):
                        totals[channel] += canvas[offset + channel] * alpha
            src_alpha = total_alpha / denom
            if src_alpha <= 0.0:
                continue
            # The averaged supersamples are premultiplied; composite them over the
            # straight-alpha pixel and store straight alpha, like _alpha_over does.
            offset = (row * width + column) * 4
            keep = region[offset + 3] / 255.0 * (1.0 - src_alpha)
            out_alpha = src_alpha + keep
            for channel in range(3):
                premult = totals[channel] / denom
                region[offset + channel] = min(
                    255, round((premult + region[offset + channel] * keep) / out_alpha)
                )
            region[offset + 3] = round(out_alpha * 255.0)
    node.setPixelData(bytes(region), left, top, width, height)


def _polygon_spans(points):
    ys = [point[1] for point in points]
    min_y = int(math.floor(min(ys)))
    max_y = int(math.ceil(max(ys)))
    count = len(points)
    for y in range(min_y, max_y + 1):
        nodes_x: list[float] = []
        for index in range(count):
            x1, y1 = points[index]
            x2, y2 = points[(index + 1) % count]
            if y1 == y2:
                continue
            if min(y1, y2) <= y < max(y1, y2):
                nodes_x.append(x1 + (y - y1) / (y2 - y1) * (x2 - x1))
        nodes_x.sort()
        for start, end in zip(nodes_x[0::2], nodes_x[1::2]):
            yield y, int(math.ceil(start)), int(math.floor(end))
