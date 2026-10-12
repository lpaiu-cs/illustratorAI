from nic_agent.svg_raster import parse_svg, render_shapes_on_node
from nic_agent.simulator import SimLayerNode


def make_node(size=32):
    return SimLayerNode(
        layer_id="v",
        name="V",
        kind="vector",
        width=size,
        height=size,
        buffer=bytearray(size * size * 4),
    )


def pixel(node, x, y):
    offset = (y * node.width + x) * 4
    blue, green, red, alpha = node.buffer[offset : offset + 4]
    return (red, green, blue, alpha)


SVG_NS = '<svg xmlns="http://www.w3.org/2000/svg">{}</svg>'


def test_rect_outline_strokes_border_only():
    content = parse_svg(SVG_NS.format('<rect x="4" y="4" width="16" height="16" fill="none" stroke="#FF0000"/>'))
    assert not content.unsupported
    node = make_node()
    touched = render_shapes_on_node(node, content)
    assert touched == (3, 3, 18, 18)
    top = pixel(node, 12, 4)
    bottom = pixel(node, 12, 20)
    assert top[0] >= 191 and top[3] >= 128
    assert bottom[0] >= 191 and bottom[3] >= 128
    assert pixel(node, 12, 12) == (0, 0, 0, 0)


def test_filled_circle_covers_center_not_outside():
    content = parse_svg(SVG_NS.format('<circle cx="16" cy="16" r="6" fill="#00FF00" stroke="none"/>'))
    node = make_node()
    render_shapes_on_node(node, content)
    assert pixel(node, 16, 16) == (0, 255, 0, 255)
    assert pixel(node, 2, 2) == (0, 0, 0, 0)


def test_default_fill_is_black_for_closed_shapes():
    content = parse_svg(SVG_NS.format("<rect x='8' y='8' width='8' height='8'/>"))
    node = make_node()
    render_shapes_on_node(node, content)
    assert pixel(node, 10, 10) == (0, 0, 0, 255)


def test_open_line_without_stroke_falls_back_to_black():
    content = parse_svg(SVG_NS.format('<line x1="4" y1="16" x2="28" y2="16"/>'))
    node = make_node()
    render_shapes_on_node(node, content)
    center = pixel(node, 16, 16)
    assert center[3] >= 128 and center[0] == 0


def test_circle_edges_are_antialiased():
    content = parse_svg(SVG_NS.format('<circle cx="16" cy="16" r="8" fill="#FF0000"/>'))
    node = make_node()
    render_shapes_on_node(node, content)
    edge_alphas = [pixel(node, x, 16)[3] for x in range(7, 11)]
    assert any(0 < alpha < 255 for alpha in edge_alphas)
    assert pixel(node, 16, 16) == (255, 0, 0, 255)


def test_cubic_path_produces_ink_along_curve():
    content = parse_svg(
        SVG_NS.format('<path d="M4 28 C 10 10, 22 10, 28 28" fill="none" stroke="#000000" stroke-width="2"/>')
    )
    node = make_node()
    render_shapes_on_node(node, content)
    midline = [pixel(node, x, y)[3] for x in range(13, 20) for y in range(13, 20)]
    assert any(alpha > 0 for alpha in midline)


def test_arc_command_draws_upper_semicircle():
    content = parse_svg(
        SVG_NS.format('<path d="M8 24 A 8 8 0 0 1 24 24" fill="none" stroke="#0000FF" stroke-width="2"/>')
    )
    node = make_node()
    render_shapes_on_node(node, content)
    apex = [pixel(node, 16, y) for y in range(14, 19)]
    assert any(pixel[2] > 200 and pixel[3] > 0 for pixel in apex)


def test_unsupported_features_are_recorded():
    content = parse_svg(
        SVG_NS.format(
            '<g transform="translate(5,5)"><rect x="1" y="1" width="4" height="4"/><path d="M0 0 S 5 5, 10 0"/></g>'
        )
    )
    assert "transform:g" in content.unsupported
    assert any(item.startswith("path:") for item in content.unsupported)


def test_relative_path_commands_match_absolute_geometry():
    absolute = parse_svg(SVG_NS.format('<path d="M8 8 L 24 8 L 24 24 Z" fill="none" stroke="#123456"/>'))
    relative = parse_svg(SVG_NS.format('<path d="M8 8 l 16 0 l 0 16 z" fill="none" stroke="#123456"/>'))
    node_a, node_b = make_node(), make_node()
    box_a = render_shapes_on_node(node_a, absolute)
    box_b = render_shapes_on_node(node_b, relative)
    assert box_a == box_b


def test_fill_crossing_canvas_edges_is_clipped():
    content = parse_svg(
        SVG_NS.format(
            '<rect x="2" y="12" width="10" height="8" fill="#FF0000"/>'
            '<rect x="2" y="-4" width="10" height="8" fill="#00FF00"/>'
        )
    )
    node = make_node(16)
    render_shapes_on_node(node, content)  # must not index past the supersample buffer
    assert pixel(node, 5, 14) == (255, 0, 0, 255)
    assert pixel(node, 5, 2) == (0, 255, 0, 255)
    # Rows above the canvas must not wrap around into other rows.
    assert pixel(node, 5, 6) == (0, 0, 0, 0)


def test_partial_coverage_is_stored_as_straight_alpha():
    # x 4..8.25 covers half of pixel column 8 (2 of 4 supersamples).
    svg = SVG_NS.format('<rect x="4" y="4" width="4.25" height="4" fill="#FF0000" stroke="none"/>')
    node = make_node()
    render_shapes_on_node(node, parse_svg(svg))
    assert pixel(node, 8, 5) == (255, 0, 0, 128)

    # Over a semi-transparent blue pixel: straight-alpha "over" of red at 50%.
    node = make_node()
    offset = (5 * node.width + 8) * 4
    node.buffer[offset : offset + 4] = bytes((255, 0, 0, 128))  # BGRA blue, alpha 128
    render_shapes_on_node(node, parse_svg(svg))
    red, green, blue, alpha = pixel(node, 8, 5)
    assert abs(red - 170) <= 1 and green == 0 and abs(blue - 85) <= 1 and abs(alpha - 192) <= 1


def test_later_shape_covers_earlier_shape_stroke():
    content = parse_svg(
        SVG_NS.format(
            '<rect x="8" y="8" width="8" height="8" fill="none" stroke="#FF0000" stroke-width="2"/>'
            '<rect x="4" y="4" width="16" height="16" fill="#0000FF" stroke="none"/>'
        )
    )
    node = make_node()
    render_shapes_on_node(node, content)
    assert pixel(node, 8, 12) == (0, 0, 255, 255)


def test_rgb_colors_are_opaque_and_rgba_alpha_is_parsed():
    from nic_agent.svg_raster import _parse_color

    assert _parse_color("rgb(255,0,0)") == (255, 0, 0, 255)
    assert _parse_color("rgb(0, 128, 0)") == (0, 128, 0, 255)
    assert _parse_color("rgba(255,0,0,0.5)") == (255, 0, 0, 128)
    assert _parse_color("rgba(0,0,0,.5)") == (0, 0, 0, 128)


def test_open_path_fill_is_implicitly_closed_but_stroke_is_not():
    for d in ("M4 4 L24 4 L14 24", "M4 4 L24 4 L14 24 Z"):
        node = make_node()
        render_shapes_on_node(node, parse_svg(SVG_NS.format(f'<path d="{d}" fill="#FF0000"/>')))
        assert pixel(node, 14, 10) == (255, 0, 0, 255)

    def closing_edge_alpha(d):  # (9, 14) lies on the 14,24 -> 4,4 edge only Z draws
        node = make_node()
        svg = f'<path d="{d}" fill="none" stroke="#000000"/>'
        render_shapes_on_node(node, parse_svg(SVG_NS.format(svg)))
        return pixel(node, 9, 14)[3]

    assert closing_edge_alpha("M4 4 L24 4 L14 24") == 0
    assert closing_edge_alpha("M4 4 L24 4 L14 24 Z") > 0


def test_group_fill_inheritance():
    content = parse_svg(
        SVG_NS.format(
            '<g fill="#FF00FF"><circle cx="16" cy="16" r="5"/><circle cx="16" cy="16" r="2" fill="#00FFFF"/></g>'
        )
    )
    node = make_node()
    render_shapes_on_node(node, content)
    assert pixel(node, 16, 16) == (0, 255, 255, 255)
