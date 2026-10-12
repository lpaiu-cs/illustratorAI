from __future__ import annotations

import json
import queue
import socket
import threading
from typing import Any, Callable, Mapping

BRIDGE_PROTOCOL_VERSION = "0.1.0"
DEFAULT_BRIDGE_HOST = "127.0.0.1"
DEFAULT_BRIDGE_PORT = 59420


class RequestDispatcher:
    def __init__(self, executor_factory: Callable[[], Any]) -> None:
        self._executor_factory = executor_factory
        self.executor = executor_factory()
        self.stop_requested = False
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self.executor = self._executor_factory()

    def dispatch(self, request: Mapping[str, Any]) -> dict[str, Any]:
        kind = request.get("kind")
        if kind == "ping":
            return {"ok": True, "pong": {"protocol_version": BRIDGE_PROTOCOL_VERSION}}
        if kind == "observe":
            with self._lock:
                return {"ok": True, "observation": self.executor.observe()}
        if kind == "action":
            raw_action = request.get("action")
            if not isinstance(raw_action, dict):
                return {"ok": False, "error": "action must be an object"}
            with self._lock:
                result = self.executor.apply(raw_action)
                observation = self.executor.observe()
            return {
                "ok": True,
                "result": {
                    "ok": result.ok,
                    "action_type": result.action_type,
                    "error": result.error,
                },
                "observation": observation,
            }
        if kind == "reset":
            self.reset()
            return {"ok": True}
        if kind == "shutdown":
            self.stop_requested = True
            return {"ok": True}
        return {"ok": False, "error": f"unknown request kind: {kind!r}"}


def encode_message(message: Mapping[str, Any]) -> bytes:
    return json.dumps(message, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"


def decode_message(line: str) -> dict[str, Any]:
    message = json.loads(line)
    if not isinstance(message, dict):
        raise ValueError("message must be a JSON object")
    return message


class QueuedSubmitter:
    def __init__(self, dispatcher: RequestDispatcher) -> None:
        self.dispatcher = dispatcher
        self._queue: queue.Queue[tuple[dict[str, Any], queue.Queue[dict[str, Any]]]] = queue.Queue()

    def submit(self, request: Mapping[str, Any]) -> dict[str, Any]:
        reply_box: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self._queue.put((dict(request), reply_box))
        return reply_box.get()

    def drain(self, limit: int = 64) -> int:
        handled = 0
        while handled < limit:
            try:
                request, reply_box = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                response = self.dispatcher.dispatch(request)
            except Exception as exc:
                response = {"ok": False, "error": f"dispatch_failed: {exc}"}
            reply_box.put(response)
            handled += 1
        return handled


class BridgeServer:
    def __init__(
        self,
        dispatcher: RequestDispatcher,
        host: str = DEFAULT_BRIDGE_HOST,
        port: int = DEFAULT_BRIDGE_PORT,
        submit: Callable[[Mapping[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.dispatcher = dispatcher
        self._submit = submit if submit is not None else dispatcher.dispatch
        self.host = host
        self.port = port
        self._listener_socket: socket.socket | None = None
        self._stop = threading.Event()
        self._accept_thread: threading.Thread | None = None
        self._connections_lock = threading.Lock()
        self._connections: list[socket.socket] = []

    def start(self) -> int:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))
        self.port = listener.getsockname()[1]
        listener.listen(4)
        self._listener_socket = listener
        self._accept_thread = threading.Thread(
            target=self._accept_loop, name="nic-agent-bridge-accept", daemon=True
        )
        self._accept_thread.start()
        return self.port

    def shutdown(self) -> None:
        self._stop.set()
        if self._listener_socket is not None:
            try:
                self._listener_socket.close()
            except OSError:
                pass
        with self._connections_lock:
            connections = list(self._connections)
            self._connections.clear()
        for conn in connections:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            conn.close()

    @property
    def stopped(self) -> bool:
        return self._stop.is_set() or self.dispatcher.stop_requested

    def _accept_loop(self) -> None:
        listener = self._listener_socket
        assert listener is not None
        listener.settimeout(0.2)
        while not self.stopped:
            try:
                conn, _addr = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with self._connections_lock:
                self._connections.append(conn)
            threading.Thread(
                target=self._serve_connection,
                args=(conn,),
                name="nic-agent-bridge-conn",
                daemon=True,
            ).start()

    def _serve_connection(self, conn: socket.socket) -> None:
        reader = conn.makefile("r", encoding="utf-8", newline="\n")
        try:
            for line in reader:
                line = line.strip()
                if not line:
                    continue
                response = self._handle_line(line)
                conn.sendall(encode_message(response))
                if self.stopped:
                    break
        except OSError:
            pass
        finally:
            reader.close()
            with self._connections_lock:
                if conn in self._connections:
                    self._connections.remove(conn)
            try:
                conn.close()
            except OSError:
                pass

    def _handle_line(self, line: str) -> dict[str, Any]:
        try:
            request = decode_message(line)
        except (ValueError, json.JSONDecodeError) as exc:
            return {"id": None, "ok": False, "error": f"invalid_request: {exc}"}
        request_id = request.get("id")
        try:
            response = self._submit(request)
        except Exception as exc:
            response = {"ok": False, "error": f"dispatch_failed: {exc}"}
        return {"id": request_id, **response}
