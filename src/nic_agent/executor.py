from __future__ import annotations

from typing import Any, Mapping

from nic_agent.backend import DocumentBackend
from nic_agent.models import Action, ActionResult, ActionValidationError
from nic_agent.validator import validate_action_payload


class ActionExecutor:
    def __init__(self, backend: DocumentBackend) -> None:
        self.backend = backend

    def apply(self, raw_action: Mapping[str, Any]) -> ActionResult:
        try:
            action = validate_action_payload(raw_action)
        except ActionValidationError as exc:
            return ActionResult(False, str(raw_action.get("type")), error=str(exc))
        if action.type == "finish":
            return ActionResult(True, action.type)
        failure = self._precheck(action)
        if failure is not None:
            return ActionResult(False, action.type, error=failure)
        try:
            getattr(self.backend, f"op_{action.type}")(action.payload)
        except Exception as exc:
            return ActionResult(False, action.type, error=f"{action.type}_failed: {exc}")
        return ActionResult(True, action.type)

    def observe(self) -> dict[str, Any]:
        return self.backend.observe()

    def fingerprint(self) -> str | None:
        return self.backend.fingerprint()

    def _precheck(self, action: Action) -> str | None:
        backend = self.backend
        if action.type == "create_document":
            if backend.has_document():
                return "document_already_exists"
            return None
        if not backend.has_document():
            return "no_document"
        body = action.payload
        if action.type == "create_layer":
            if backend.find_layer_kind(str(body["layer_id"])) is not None:
                return "duplicate_layer_id"
            parent_id = body.get("parent_id")
            if parent_id is not None:
                parent_kind = backend.find_layer_kind(str(parent_id))
                if parent_kind is None:
                    return "unknown_parent_layer"
                if parent_kind != "group":
                    return "parent_not_group"
            return None
        if action.type == "select_layer":
            if backend.find_layer_kind(str(body["layer_id"])) is None:
                return "unknown_layer"
            return None
        if action.type in {"fill_rect", "stroke"}:
            kind = backend.active_node_kind()
            if kind is None:
                return "no_active_paint_layer"
            if kind != "paint":
                return "active_layer_not_paintable"
            return None
        if action.type == "add_svg":
            kind = backend.active_node_kind()
            if kind is None:
                return "no_active_vector_layer"
            if kind != "vector":
                return "active_layer_not_vector"
            return None
        if action.type == "set_layer_properties":
            if backend.find_layer_kind(str(body["layer_id"])) is None:
                return "unknown_layer"
            return None
        if action.type == "export_png":
            if not backend.export_ready():
                return "no_output_root"
            file_name = str(body["file_name"])
            if "/" in file_name or "\\" in file_name or file_name in {".", ".."}:
                return "file_name_must_be_simple"
            return None
        return None
