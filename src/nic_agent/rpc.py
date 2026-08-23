from __future__ import annotations

import socket
from typing import Any, Mapping

from nic_agent.bridge_core import (
    DEFAULT_BRIDGE_HOST,
    DEFAULT_BRIDGE_PORT,
    decode_message,
    encode_message,
)
from nic_agent.models import ActionResult


class BridgeProtocolError(RuntimeError):
    pass


class KritaRPCExecutor:
    def __init__(
        self,
        host: str = DEFAULT_BRIDGE_HOST,
        port: int = DEFAULT_BRIDGE_PORT,
        timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._reader = None
        self._request_id = 0
        self._cached_observation: dict[str, Any] | None = None

    def connect(self) -> dict[str, Any]:
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._reader = self._sock.makefile("r", encoding="utf-8", newline="\n")
        return self.ping()

    def ping(self) -> dict[str, Any]:
        pong = self._request("ping").get("pong")
        return dict(pong) if isinstance(pong, dict) else {}

    def reset(self) -> None:
        self._request("reset")
        self._cached_observation = None

    def apply(self, raw_action: Mapping[str, Any]) -> ActionResult:
        response = self._request("action", action=dict(raw_action))
        observation = response.get("observation")
        self._cached_observation = observation if isinstance(observation, dict) else None
        result = response.get("result")
        if not isinstance(result, dict):
            raise BridgeProtocolError(f"action response missing result: {response}")
        return ActionResult(
            ok=bool(result.get("ok")),
            action_type=str(result.get("action_type")),
            error=result.get("error"),
        )

    def observe(self) -> dict[str, Any]:
        if self._cached_observation is not None:
            cached, self._cached_observation = self._cached_observation, None
            return cached
        response = self._request("observe")
        observation = response.get("observation")
        return observation if isinstance(observation, dict) else {}

    def fingerprint(self) -> str | None:
        return None

    def shutdown_server(self) -> None:
        try:
            if self._sock is not None:
                self._request("shutdown")
        finally:
            self.close()

    def close(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        self._cached_observation = None

    def _request(self, kind: str, **fields: Any) -> dict[str, Any]:
        if self._sock is None or self._reader is None:
            raise BridgeProtocolError("not connected to the bridge server")
        self._request_id += 1
        request: dict[str, Any] = {"id": self._request_id, "kind": kind, **fields}
        self._sock.sendall(encode_message(request))
        line = self._reader.readline()
        if not line:
            raise BridgeProtocolError("bridge server closed the connection")
        response = decode_message(line)
        if not response.get("ok", False):
            raise BridgeProtocolError(str(response.get("error", "bridge request failed")))
        return response
