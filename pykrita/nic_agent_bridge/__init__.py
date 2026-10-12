from __future__ import annotations

import os
from pathlib import Path

from .bootstrap import append_bootstrap_log, bootstrap_log_path, bootstrap_plugin

try:  # pragma: no cover - exercised only in Krita
    from krita import Extension, Krita
    from PyQt5.QtWidgets import QMessageBox
except ImportError:  # pragma: no cover - keep importable outside Krita
    try:
        from PyQt6.QtWidgets import QMessageBox  # type: ignore
        from krita import Extension, Krita  # type: ignore
    except ImportError:  # pragma: no cover
        Extension = object  # type: ignore
        Krita = None  # type: ignore
        QMessageBox = None  # type: ignore


class NicAgentBridgeExtension(Extension):  # pragma: no cover - Krita runtime only
    def __init__(self, parent):
        super().__init__(parent)
        try:
            self.info = bootstrap_plugin(__file__)
            self.default_port = int(os.environ.get("NIC_AGENT_BRIDGE_PORT", "59420"))
            self.controller = None
        except Exception as exc:
            append_bootstrap_log("Agent bridge bootstrap failed", exc)
            raise

    def setup(self) -> None:
        return None

    def createActions(self, window) -> None:
        start_action = window.createAction(
            "nic_agent_bridge_start",
            "Start Agent Bridge Server",
            "tools/scripts",
        )
        start_action.triggered.connect(self.start_server)

        stop_action = window.createAction(
            "nic_agent_bridge_stop",
            "Stop Agent Bridge Server",
            "tools/scripts",
        )
        stop_action.triggered.connect(self.stop_server)

    def start_server(self) -> None:
        if QMessageBox is not None and self.controller is not None and self.controller.running:
            self._message("Agent Bridge", f"Already listening on port {self.controller.port}")
            return
        try:
            from nic_agent.bridge_core import RequestDispatcher
            from nic_agent.executor import ActionExecutor
            from nic_compiler.krita_session import KritaSession

            from .krita_backend import KritaBackend
            from .server import BridgeController

            session = KritaSession(Path(self.info["project_root"]), krita_app=Krita.instance())
            output_root = Path(self.info["output_root"])
            output_root.mkdir(parents=True, exist_ok=True)

            def executor_factory():
                return ActionExecutor(KritaBackend(session, output_root=output_root))

            dispatcher = RequestDispatcher(executor_factory)
            controller = BridgeController(dispatcher, port=self.default_port)
            port = controller.start()
            self.controller = controller
            append_bootstrap_log(f"Agent bridge listening on 127.0.0.1:{port}")
            self._message(
                "Agent Bridge Started",
                f"Listening on 127.0.0.1:{port}\nExports: {output_root}",
            )
        except Exception as exc:
            append_bootstrap_log("Agent bridge start failed", exc)
            self._message(
                "Agent Bridge Failed to Start",
                f"{exc}\n\nBootstrap log:\n{bootstrap_log_path()}",
            )

    def stop_server(self) -> None:
        if self.controller is None or not self.controller.running:
            self._message("Agent Bridge", "Not running")
            return
        try:
            self.controller.stop()
            append_bootstrap_log("Agent bridge stopped")
            self._message("Agent Bridge Stopped", "Server closed.")
        except Exception as exc:
            append_bootstrap_log("Agent bridge stop failed", exc)
            self._message("Agent Bridge Stop Failed", str(exc))

    def _message(self, title: str, body: str) -> None:
        if QMessageBox is None:
            return
        QMessageBox.information(None, title, body)


if Krita is not None:  # pragma: no cover - Krita runtime only
    Krita.instance().addExtension(NicAgentBridgeExtension(Krita.instance()))
