from __future__ import annotations

from pathlib import Path

import pytest

from nic_ir.models import IRValidationError
from nic_ir.validator import validate_ir_payload


def _base_payload(tmp_path: Path) -> dict:
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "face.png").write_bytes(b"png")
    (tmp_path / "assets" / "shape.svg").write_text("<svg/>", encoding="utf-8")
    return {
        "meta": {"schema_version": "0.1.0"},
        "document": {
            "width": 64,
            "height": 64,
            "dpi": 144,
            "color_model": "RGBA",
            "color_depth": "U8",
            "background_color": "#FFFFFFFF",
            "file_name": "demo"
        },
        "resources": [
            {"id": "face", "kind": "png", "path": "assets/face.png"},
            {"id": "shape", "kind": "svg", "path": "assets/shape.svg"}
        ],
        "layers": [
            {
                "id": "base",
                "name": "base",
                "type": "paint",
                "ops": [{"type": "fill_solid", "color": "#112233FF"}]
            },
            {
                "id": "vector",
                "name": "vector",
                "type": "vector",
                "ops": [{"type": "add_svg", "resource_id": "shape"}]
            }
        ],
        "exports": [
            {"kind": "kra", "file_name": "build/demo.kra"},
            {"kind": "png", "file_name": "build/demo.png"}
        ]
    }


def test_validate_ir_payload_accepts_valid_payload(tmp_path: Path) -> None:
    payload = _base_payload(tmp_path)

    ir = validate_ir_payload(payload, workspace_root=tmp_path)

    assert ir.document.file_name == "demo"
    assert [layer.id for layer in ir.layers] == ["base", "vector"]
    assert ir.resources["face"].path == "assets/face.png"


def test_validate_ir_payload_rejects_unknown_resource_reference(tmp_path: Path) -> None:
    payload = _base_payload(tmp_path)
    payload["layers"][1]["ops"][0]["resource_id"] = "missing"

    with pytest.raises(IRValidationError) as exc_info:
        validate_ir_payload(payload, workspace_root=tmp_path)

    assert "unknown resource" in str(exc_info.value)


def test_validate_ir_payload_rejects_unsupported_layer_type(tmp_path: Path) -> None:
    payload = _base_payload(tmp_path)
    payload["layers"][0]["type"] = "text"

    with pytest.raises(IRValidationError) as exc_info:
        validate_ir_payload(payload, workspace_root=tmp_path)

    assert "unsupported layer type" in str(exc_info.value)

