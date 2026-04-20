from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class ReportMessage:
    level: str
    code: str
    message: str
    path: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {"level": self.level, "code": self.code, "message": self.message}
        if self.path:
            data["path"] = self.path
        if self.details:
            data["details"] = dict(self.details)
        return data


@dataclass(slots=True)
class SelfCheckItem:
    name: str
    status: str
    message: str
    critical: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "critical": self.critical,
        }
        if self.details:
            data["details"] = dict(self.details)
        return data


@dataclass(slots=True)
class CompileReport:
    run_mode: str = "plugin"
    source_ir_path: str | None = None
    workspace_root: str | None = None
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None
    success: bool = False
    environment: dict[str, Any] = field(default_factory=dict)
    capability: dict[str, Any] = field(default_factory=dict)
    path_resolution: dict[str, Any] = field(default_factory=dict)
    self_check: list[SelfCheckItem] = field(default_factory=list)
    document: dict[str, Any] = field(default_factory=dict)
    compile_summary: dict[str, Any] = field(
        default_factory=lambda: {
            "total_layers": 0,
            "planned_layers": 0,
            "created_layers": 0,
            "unsupported_ops": 0,
            "failed_ops": 0,
        }
    )
    output_files: dict[str, str | None] = field(
        default_factory=lambda: {
            "kra": None,
            "png": None,
            "psd": None,
            "manifest": None,
            "report": None,
        }
    )
    messages: list[ReportMessage] = field(default_factory=list)

    def add_error(
        self,
        code: str,
        message: str,
        path: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.messages.append(
            ReportMessage("error", code, message, path=path, details=details or {})
        )

    def add_warning(
        self,
        code: str,
        message: str,
        path: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.messages.append(
            ReportMessage("warning", code, message, path=path, details=details or {})
        )

    def add_unsupported(
        self,
        code: str,
        message: str,
        path: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.messages.append(
            ReportMessage("unsupported", code, message, path=path, details=details or {})
        )

    def add_self_check(self, item: SelfCheckItem) -> None:
        self.self_check.append(item)

    def add_output(self, kind: str, path: Path) -> None:
        self.output_files[kind] = str(path)

    def finalize(self, success: bool) -> None:
        self.compile_summary["unsupported_ops"] = sum(
            1
            for message in self.messages
            if message.level == "unsupported" and "op" in message.details
        )
        self.compile_summary["failed_ops"] = sum(
            1
            for message in self.messages
            if message.level == "error" and "op" in message.details
        )
        self.success = success
        self.finished_at = utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_mode": self.run_mode,
            "source_ir_path": self.source_ir_path,
            "workspace_root": self.workspace_root,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "success": self.success,
            "environment": self.environment,
            "capability": self.capability,
            "path_resolution": self.path_resolution,
            "self_check": [item.to_dict() for item in self.self_check],
            "document": self.document,
            "compile_summary": self.compile_summary,
            "output_files": self.output_files,
            "messages": [message.to_dict() for message in self.messages],
        }


def write_report(report: CompileReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    report.output_files["report"] = str(path)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
