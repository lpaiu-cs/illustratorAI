from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


@dataclass(slots=True, frozen=True)
class ValidationIssue:
    severity: str
    path: str
    message: str


class IRValidationError(ValueError):
    def __init__(self, issues: Iterable[ValidationIssue]) -> None:
        self.issues = tuple(issues)
        summary = "; ".join(f"{issue.path}: {issue.message}" for issue in self.issues)
        super().__init__(summary or "IR validation failed")


@dataclass(slots=True, frozen=True)
class DocumentSpec:
    width: int
    height: int
    dpi: int
    color_model: str
    color_depth: str
    background_color: str
    file_name: str


@dataclass(slots=True, frozen=True)
class ResourceSpec:
    id: str
    kind: str
    path: str


@dataclass(slots=True, frozen=True)
class ExportSpec:
    kind: str
    file_name: str
    enabled: bool = True


@dataclass(slots=True, frozen=True)
class SelectionRectangle:
    x: int
    y: int
    width: int
    height: int
    value: int = 255


@dataclass(slots=True, frozen=True)
class SelectionPixelData:
    x: int
    y: int
    width: int
    height: int
    values: tuple[int, ...]


@dataclass(slots=True, frozen=True)
class SelectionSpec:
    rectangles: tuple[SelectionRectangle, ...] = ()
    pixel_data: SelectionPixelData | None = None


@dataclass(slots=True, frozen=True)
class MaskSpec:
    id: str
    name: str
    type: str
    visible: bool = True
    selection: SelectionSpec | None = None
    transform: Mapping[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()


@dataclass(slots=True, frozen=True)
class OperationSpec:
    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class LayerSpec:
    id: str
    name: str
    type: str
    visible: bool = True
    opacity: float = 1.0
    blend_mode: str = "normal"
    locked: bool = False
    alpha_locked: bool = False
    inherit_alpha: bool = False
    tags: tuple[str, ...] = ()
    ops: tuple[OperationSpec, ...] = ()
    masks: tuple[MaskSpec, ...] = ()
    children: tuple["LayerSpec", ...] = ()

    def walk(self) -> Iterator["LayerSpec"]:
        yield self
        for child in self.children:
            yield from child.walk()


@dataclass(slots=True, frozen=True)
class IllustrationIR:
    meta: Mapping[str, Any]
    document: DocumentSpec
    resources: Mapping[str, ResourceSpec]
    layers: tuple[LayerSpec, ...]
    exports: tuple[ExportSpec, ...]
    source_path: Path | None = None

    def walk_layers(self) -> Iterator[LayerSpec]:
        for layer in self.layers:
            yield from layer.walk()

    def find_layer(self, layer_id: str) -> LayerSpec | None:
        return next((layer for layer in self.walk_layers() if layer.id == layer_id), None)

