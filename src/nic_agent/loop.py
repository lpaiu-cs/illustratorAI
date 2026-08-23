from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from nic_agent.executor import ActionExecutor
from nic_agent.policy import Policy
from nic_agent.schema import ACTION_SCHEMA_VERSION
from nic_agent.session_log import SessionLogger

MAX_CONSECUTIVE_FAILURES = 8


@dataclass(slots=True)
class SessionSummary:
    steps: int
    ok: bool
    stop_reason: str
    fingerprint: str | None = None


class AgentLoop:
    def __init__(
        self,
        executor: ActionExecutor,
        logger: SessionLogger,
        max_steps: int = 256,
    ) -> None:
        self.executor = executor
        self.logger = logger
        self.max_steps = max_steps

    def run(self, policy: Policy) -> SessionSummary:
        self.logger.log_meta(protocol_version=ACTION_SCHEMA_VERSION, max_steps=self.max_steps)
        observation: Mapping[str, Any] = {"step": 0, "note": "session_start"}
        consecutive_failures = 0
        steps = 0
        while steps < self.max_steps:
            raw_action = policy.next_action(observation)
            if raw_action is None:
                return self._summary(steps, True, "policy_exhausted")
            steps += 1
            result = self.executor.apply(raw_action)
            self.logger.log_action(
                dict(raw_action), {"ok": result.ok, "action_type": result.action_type, "error": result.error}
            )
            if not result.ok:
                consecutive_failures += 1
                observation = {"step": steps, "error": result.error, **self.executor.observe()}
                self.logger.log_observation(observation)
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    return self._summary(steps, False, "too_many_failures")
                continue
            consecutive_failures = 0
            observation = {"step": steps, **self.executor.observe()}
            self.logger.log_observation(observation)
            if result.action_type == "finish":
                return self._summary(steps, True, "finish")
        return self._summary(steps, False, "max_steps")

    def _summary(self, steps: int, ok: bool, stop_reason: str) -> SessionSummary:
        return SessionSummary(
            steps=steps,
            ok=ok,
            stop_reason=stop_reason,
            fingerprint=self.executor.fingerprint(),
        )
