from __future__ import annotations

from nic_compiler.manifest_utils import compare_manifests


def test_compare_manifests_returns_no_diffs_for_equivalent_children_order() -> None:
    expected = {
        "document": {"name": "demo"},
        "layers": [
            {
                "name": "group",
                "type": "grouplayer",
                "children": [
                    {"name": "b", "type": "paintlayer", "children": []},
                    {"name": "a", "type": "paintlayer", "children": []},
                ],
            }
        ],
    }
    actual = {
        "document": {"name": "demo"},
        "layers": [
            {
                "name": "group",
                "type": "grouplayer",
                "children": [
                    {"name": "a", "type": "paintlayer", "children": []},
                    {"name": "b", "type": "paintlayer", "children": []},
                ],
            }
        ],
    }

    assert compare_manifests(expected, actual) == []


def test_compare_manifests_reports_differences() -> None:
    expected = {"document": {"name": "left"}, "layers": []}
    actual = {"document": {"name": "right"}, "layers": []}

    diffs = compare_manifests(expected, actual)

    assert diffs == ["$.document.name: 'left' != 'right'"]

