from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(slots=True, frozen=True)
class ActionValidationIssue:
    severity: str
    path: str
    message: str


class ActionValidationError(ValueError):
    def __init__(self, issues: Iterable[ActionValidationIssue]) -> None:
        self.issues = tuple(issues)
        summary = "; ".join(f"{issue.path}: {issue.message}" for issue in self.issues)
        super().__init__(summary or "action validation failed")


@dataclass(slots=True, frozen=True)
class Action:
    type: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ActionResult:
    ok: bool
    action_type: str
    error: str | None = None
    changed_bbox: tuple[int, int, int, int] | None = None
