from __future__ import annotations

import os

from nic_agent.bridge_core import DEFAULT_BRIDGE_PORT, BridgeServer, QueuedSubmitter, RequestDispatcher

try:  # pragma: no cover - exercised only in Krita
    from PyQt5.QtCore import QTimer
except ImportError:  # pragma: no cover - keep importable outside Krita
    try:
        from PyQt6.QtCore import QTimer  # type: ignore
    except ImportError:
        QTimer = None  # type: ignore


class BridgeController:
    def __init__(
        self,
        dispatcher: RequestDispatcher,
        port: int | None = None,
        pump_interval_ms: int = 40,
    ) -> None:
        if QTimer is None:
            raise RuntimeError("Qt timer unavailable; bridge requires a Krita runtime")
        self.gate = QueuedSubmitter(dispatcher)
        self.server = BridgeServer(
            dispatcher,
            port=int(port if port is not None else os.environ.get("NIC_AGENT_BRIDGE_PORT", DEFAULT_BRIDGE_PORT)),
            submit=self.gate.submit,
        )
        self._timer = QTimer()
        self._timer.setInterval(pump_interval_ms)
        self._timer.timeout.connect(self._pump)

    def start(self) -> int:
        port = self.server.start()
        self.port = port
        self._timer.start()
        return port

    def stop(self) -> None:
        self._timer.stop()
        self.server.shutdown()

    @property
    def running(self) -> bool:
        return self._timer.isActive()

    def _pump(self) -> None:
        self.gate.drain(limit=32)
