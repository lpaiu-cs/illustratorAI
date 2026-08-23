from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class Policy(Protocol):
    def next_action(self, observation: Mapping[str, Any]) -> Mapping[str, Any] | None: ...


@dataclass(slots=True)
class ScriptedPolicy:
    actions: list[Mapping[str, Any]]
    index: int = 0

    def next_action(self, observation: Mapping[str, Any]) -> Mapping[str, Any] | None:
        if self.index >= len(self.actions):
            return None
        action = self.actions[self.index]
        self.index += 1
        return action
