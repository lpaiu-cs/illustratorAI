from __future__ import annotations

import pytest

from nic_compiler.raster_ops import parse_hex_color


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#ABC", (170, 187, 204, 255)),
        ("#ABCD", (170, 187, 204, 221)),
        ("#112233", (17, 34, 51, 255)),
        ("#11223344", (17, 34, 51, 68)),
        ("transparent", (0, 0, 0, 0)),
    ],
)
def test_parse_hex_color(value: str, expected: tuple[int, int, int, int]) -> None:
    assert parse_hex_color(value) == expected


def test_parse_hex_color_rejects_invalid_value() -> None:
    with pytest.raises(ValueError):
        parse_hex_color("rgba(1,2,3,1)")

