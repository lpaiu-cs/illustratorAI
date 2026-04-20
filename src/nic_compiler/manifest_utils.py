from __future__ import annotations

from typing import Any


def normalize_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "document": dict(manifest.get("document", {})),
        "layers": [_normalize_node(node) for node in manifest.get("layers", [])],
    }


def compare_manifests(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    normalized_expected = normalize_manifest(expected)
    normalized_actual = normalize_manifest(actual)
    diffs: list[str] = []
    _compare_value(normalized_expected, normalized_actual, "$", diffs)
    return diffs


def _normalize_node(node: dict[str, Any]) -> dict[str, Any]:
    normalized = {key: value for key, value in node.items() if key != "children"}
    children = [_normalize_node(child) for child in node.get("children", [])]
    normalized["children"] = sorted(children, key=lambda item: (item.get("name", ""), item.get("type", "")))
    return normalized


def _compare_value(expected: Any, actual: Any, path: str, diffs: list[str]) -> None:
    if type(expected) is not type(actual):
        diffs.append(f"{path}: type mismatch {type(expected).__name__} != {type(actual).__name__}")
        return
    if isinstance(expected, dict):
        expected_keys = set(expected)
        actual_keys = set(actual)
        for key in sorted(expected_keys - actual_keys):
            diffs.append(f"{path}.{key}: missing in actual")
        for key in sorted(actual_keys - expected_keys):
            diffs.append(f"{path}.{key}: unexpected in actual")
        for key in sorted(expected_keys & actual_keys):
            _compare_value(expected[key], actual[key], f"{path}.{key}", diffs)
        return
    if isinstance(expected, list):
        if len(expected) != len(actual):
            diffs.append(f"{path}: length mismatch {len(expected)} != {len(actual)}")
            return
        for index, (left, right) in enumerate(zip(expected, actual)):
            _compare_value(left, right, f"{path}[{index}]", diffs)
        return
    if expected != actual:
        diffs.append(f"{path}: {expected!r} != {actual!r}")

