from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from nic_ir.models import DocumentSpec, LayerSpec, MaskSpec, SelectionSpec

try:
    from krita import InfoObject, Krita, ManagedColor, Selection
except ImportError:  # pragma: no cover - exercised only inside Krita
    InfoObject = None
    Krita = None
    ManagedColor = None
    Selection = None


class KritaRuntimeUnavailable(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class RuntimeCapabilities:
    has_krita: bool
    has_selection_api: bool
    has_svg_injection: bool
    has_brush_line: bool
    has_brush_path: bool
    has_view_controls: bool
    supports_transform_payload: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KritaSession:
    def __init__(self, workspace_root: Path, krita_app: Any | None = None) -> None:
        self.workspace_root = workspace_root.resolve()
        self._krita_app = krita_app

    def krita(self) -> Any:
        if self._krita_app is not None:
            return self._krita_app
        if Krita is None:
            raise KritaRuntimeUnavailable(
                "Krita Python runtime is unavailable. Run this compiler inside Krita."
            )
        return Krita.instance()

    def runtime_import_available(self) -> bool:
        return self._krita_app is not None or Krita is not None

    def runtime_version(self) -> str | None:
        if not self.runtime_import_available():
            return None
        try:
            return self.krita().version()
        except Exception:
            return None

    def create_document(self, spec: DocumentSpec) -> Any:
        app = self.krita()
        document = app.createDocument(
            spec.width,
            spec.height,
            spec.file_name,
            spec.color_model,
            spec.color_depth,
            "",
            float(spec.dpi),
        )
        if document is None:
            raise RuntimeError("Krita failed to create the document")
        if hasattr(document, "setBatchmode"):
            document.setBatchmode(True)
        color = self._qcolor_from_hex(spec.background_color)
        if color is not None and hasattr(document, "setBackgroundColor"):
            document.setBackgroundColor(color)
        return document

    def present_document(self, document: Any) -> None:
        try:
            app = self.krita()
        except KritaRuntimeUnavailable:
            return
        window = app.activeWindow() if hasattr(app, "activeWindow") else None
        if window is not None and hasattr(window, "addView"):
            window.addView(document)
        if hasattr(app, "setActiveDocument"):
            app.setActiveDocument(document)

    def detect_capabilities(self, document: Any) -> RuntimeCapabilities:
        try:
            probe_paint = document.createNode("__nic_probe__", "paintlayer")
            probe_vector = document.createVectorLayer("__nic_probe_vector__")
        except Exception:
            return RuntimeCapabilities(
                has_krita=True,
                has_selection_api=Selection is not None,
                has_svg_injection=False,
                has_brush_line=False,
                has_brush_path=False,
                has_view_controls=False,
                supports_transform_payload=False,
            )
        view = self.active_view_for_document(document)
        return RuntimeCapabilities(
            has_krita=True,
            has_selection_api=Selection is not None,
            has_svg_injection=hasattr(probe_vector, "addShapesFromSvg"),
            has_brush_line=hasattr(probe_paint, "paintLine"),
            has_brush_path=hasattr(probe_paint, "paintPath"),
            has_view_controls=view is not None,
            supports_transform_payload=False,
        )

    def probe_runtime_capabilities(self) -> RuntimeCapabilities:
        if not self.runtime_import_available():
            return RuntimeCapabilities(
                has_krita=False,
                has_selection_api=False,
                has_svg_injection=False,
                has_brush_line=False,
                has_brush_path=False,
                has_view_controls=False,
                supports_transform_payload=False,
            )
        document = self.krita().createDocument(4, 4, "__nic_runtime_probe__", "RGBA", "U8", "", 72.0)
        if document is None:
            raise RuntimeError("Failed to create runtime probe document")
        try:
            if hasattr(document, "setBatchmode"):
                document.setBatchmode(True)
            return self.detect_capabilities(document)
        finally:
            if hasattr(document, "close"):
                document.close()

    def active_view_for_document(self, document: Any) -> Any | None:
        try:
            app = self.krita()
        except KritaRuntimeUnavailable:
            return None
        window = app.activeWindow() if hasattr(app, "activeWindow") else None
        if window is None or not hasattr(window, "views"):
            return None
        for view in window.views():
            if hasattr(view, "document") and view.document() == document:
                return view
        return window.activeView() if hasattr(window, "activeView") else None

    def configure_brush(self, document: Any, payload: dict[str, Any]) -> bool:
        view = self.active_view_for_document(document)
        if view is None:
            return False
        preset_name = payload.get("preset")
        if preset_name:
            app = self.krita()
            if hasattr(app, "resources"):
                presets = app.resources("preset")
                preset = presets.get(preset_name)
                if preset is not None and hasattr(view, "setCurrentBrushPreset"):
                    view.setCurrentBrushPreset(preset)
        if "size" in payload and hasattr(view, "setBrushSize"):
            view.setBrushSize(float(payload["size"]))
        if "blend_mode" in payload and hasattr(view, "setCurrentBlendingMode"):
            view.setCurrentBlendingMode(str(payload["blend_mode"]))
        if "opacity" in payload and hasattr(view, "setPaintingOpacity"):
            view.setPaintingOpacity(float(payload["opacity"]))
        if "flow" in payload and hasattr(view, "setPaintingFlow"):
            view.setPaintingFlow(float(payload["flow"]))
        color = payload.get("color")
        if color and ManagedColor is not None and hasattr(view, "setForeGroundColor"):
            managed = ManagedColor("RGBA", "U8", "")
            rgba = _normalized_rgba(color)
            managed.setComponents(list(rgba))
            view.setForeGroundColor(managed)
        return True

    def root_node(self, document: Any) -> Any:
        return document.rootNode()

    def set_child_nodes(self, parent: Any, nodes: Iterable[Any]) -> None:
        nodes = list(nodes)
        if not nodes:
            return
        if hasattr(parent, "setChildNodes"):
            parent.setChildNodes(nodes)
            return
        if hasattr(parent, "addChildNode"):
            for node in nodes:
                parent.addChildNode(node, None)

    def create_layer_node(self, document: Any, layer: LayerSpec) -> Any:
        if layer.type == "group":
            return document.createGroupLayer(layer.name)
        if layer.type == "vector":
            return document.createVectorLayer(layer.name)
        return document.createNode(layer.name, "paintlayer")

    def apply_common_layer_attributes(self, node: Any, layer: LayerSpec) -> None:
        if hasattr(node, "setName"):
            node.setName(layer.name)
        if hasattr(node, "setVisible"):
            node.setVisible(layer.visible)
        if hasattr(node, "setOpacity"):
            node.setOpacity(int(round(layer.opacity * 255)))
        if hasattr(node, "setBlendingMode"):
            node.setBlendingMode(layer.blend_mode)
        if hasattr(node, "setLocked"):
            node.setLocked(layer.locked)
        if hasattr(node, "setAlphaLocked"):
            node.setAlphaLocked(layer.alpha_locked)
        if hasattr(node, "setInheritAlpha"):
            node.setInheritAlpha(layer.inherit_alpha)

    def create_mask_node(self, document: Any, mask: MaskSpec) -> Any:
        if mask.type == "selection_mask":
            return document.createSelectionMask(mask.name)
        if mask.type == "transparency_mask":
            return document.createTransparencyMask(mask.name)
        if mask.type == "transform_mask":
            return document.createTransformMask(mask.name)
        raise ValueError(f"Unsupported mask type: {mask.type}")

    def apply_common_mask_attributes(self, node: Any, mask: MaskSpec) -> None:
        if hasattr(node, "setName"):
            node.setName(mask.name)
        if hasattr(node, "setVisible"):
            node.setVisible(mask.visible)

    def create_selection(self, selection_spec: SelectionSpec) -> Any:
        if Selection is None:
            raise KritaRuntimeUnavailable("Selection API is unavailable in this runtime")
        selection = Selection()
        for rect in selection_spec.rectangles:
            selection.select(rect.x, rect.y, rect.width, rect.height, rect.value)
        if selection_spec.pixel_data is not None:
            selection.setPixelData(
                bytes(selection_spec.pixel_data.values),
                selection_spec.pixel_data.x,
                selection_spec.pixel_data.y,
                selection_spec.pixel_data.width,
                selection_spec.pixel_data.height,
            )
        return selection

    def wait_for_done(self, document: Any) -> None:
        if hasattr(document, "waitForDone"):
            document.waitForDone()
        if hasattr(document, "refreshProjection"):
            document.refreshProjection()

    def save_document(self, document: Any, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if hasattr(document, "setFileName"):
            document.setFileName(str(path))
        self.wait_for_done(document)
        if not document.saveAs(str(path)):
            raise RuntimeError(f"Failed to save document: {path}")

    def export_document(self, document: Any, path: Path) -> None:
        if InfoObject is None:
            raise KritaRuntimeUnavailable("InfoObject is unavailable outside Krita")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.wait_for_done(document)
        export_config = InfoObject()
        if not document.exportImage(str(path), export_config):
            raise RuntimeError(f"Failed to export document: {path}")

    def resolve_workspace_path(self, raw_path: str, allow_create: bool = False) -> Path:
        candidate = Path(raw_path)
        resolved = (
            candidate.resolve()
            if candidate.is_absolute()
            else (self.workspace_root / candidate).resolve()
        )
        if not _is_relative_to(resolved, self.workspace_root):
            raise ValueError(f"path escapes workspace root: {raw_path}")
        if not allow_create and not resolved.exists():
            raise FileNotFoundError(raw_path)
        return resolved

    def read_text_resource(self, raw_path: str) -> str:
        path = self.resolve_workspace_path(raw_path, allow_create=False)
        return path.read_text(encoding="utf-8")

    def load_external_pixels(
        self,
        raw_path: str,
        color_model: str,
        color_depth: str,
        color_profile: str = "",
    ) -> tuple[bytes, int, int]:
        source_path = self.resolve_workspace_path(raw_path, allow_create=False)
        app = self.krita()
        document = app.openDocument(str(source_path))
        if document is None:
            raise RuntimeError(f"Failed to open external image: {source_path}")
        try:
            if hasattr(document, "setBatchmode"):
                document.setBatchmode(True)
            if color_profile and hasattr(document, "setColorSpace"):
                document.setColorSpace(color_model, color_depth, color_profile)
            width = int(document.width())
            height = int(document.height())
            payload = bytes(document.pixelData(0, 0, width, height))
            return payload, width, height
        finally:
            if hasattr(document, "close"):
                document.close()

    def snapshot_active_document_manifest(self) -> dict[str, Any]:
        app = self.krita()
        document = app.activeDocument() if hasattr(app, "activeDocument") else None
        if document is None:
            raise RuntimeError("No active document")
        return {
            "document": {
                "name": document.name(),
                "width": document.width(),
                "height": document.height(),
                "color_model": document.colorModel(),
                "color_depth": document.colorDepth(),
                "resolution": document.resolution(),
            },
            "layers": [_node_manifest(node) for node in document.topLevelNodes()],
        }

    def write_manifest(self, path: Path, manifest: dict[str, Any]) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def _qcolor_from_hex(self, value: str) -> Any | None:
        try:
            from PyQt5.QtGui import QColor  # pragma: no cover - Krita runtime only
        except ImportError:  # pragma: no cover - Krita runtime only
            try:
                from PyQt6.QtGui import QColor  # type: ignore
            except ImportError:
                return None
        color = QColor()
        color.setNamedColor(value)
        if color.isValid():
            return color
        return None


def _node_manifest(node: Any) -> dict[str, Any]:
    return {
        "name": node.name(),
        "type": node.type(),
        "visible": node.visible(),
        "opacity": node.opacity(),
        "blend_mode": node.blendingMode(),
        "inherit_alpha": node.inheritAlpha(),
        "locked": node.locked(),
        "children": [_node_manifest(child) for child in node.childNodes()],
    }


def _normalized_rgba(color: str) -> tuple[float, float, float, float]:
    from nic_compiler.raster_ops import parse_hex_color

    r, g, b, a = parse_hex_color(color)
    return (r / 255.0, g / 255.0, b / 255.0, a / 255.0)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
