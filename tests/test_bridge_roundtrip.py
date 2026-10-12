import threading
import time

from nic_agent.bridge_core import (
    BRIDGE_PROTOCOL_VERSION,
    BridgeServer,
    QueuedSubmitter,
    RequestDispatcher,
)
from nic_agent.executor import ActionExecutor
from nic_agent.headless_backend import HeadlessBackend
from nic_agent.loop import AgentLoop
from nic_agent.models import ActionResult
from nic_agent.policy import ScriptedPolicy
from nic_agent.rpc import BridgeProtocolError, KritaRPCExecutor
from nic_agent.session_log import SessionLogger, read_actions

DEMO_ACTIONS = [
    {
        "type": "create_document",
        "payload": {"width": 24, "height": 24, "background_color": "#FFFFFFFF"},
    },
    {
        "type": "create_layer",
        "payload": {"layer_id": "base", "name": "Base", "kind": "paint"},
    },
    {
        "type": "stroke",
        "payload": {"points": [[4, 12], [20, 12]], "color": "#333333", "size": 3},
    },
    {"type": "export_png", "payload": {"file_name": "remote.png"}},
    {"type": "finish"},
]


def build_dispatcher(tmp_path):
    output_root = tmp_path / "exports"

    def executor_factory():
        return ActionExecutor(HeadlessBackend(output_root=output_root))

    return RequestDispatcher(executor_factory)


def start_direct_server(tmp_path):
    server = BridgeServer(build_dispatcher(tmp_path), port=0)
    port = server.start()
    return server, port


def start_queued_server(tmp_path):
    dispatcher = build_dispatcher(tmp_path)
    gate = QueuedSubmitter(dispatcher)
    server = BridgeServer(dispatcher, port=0, submit=gate.submit)
    port = server.start()

    def pump():
        while not server.stopped:
            gate.drain(limit=8)
            time.sleep(0.005)

    threading.Thread(target=pump, daemon=True).start()
    return server, port


def test_ping_and_action_roundtrip(tmp_path):
    server, port = start_direct_server(tmp_path)
    client = KritaRPCExecutor(port=port)
    try:
        pong = client.connect()
        assert pong["protocol_version"] == BRIDGE_PROTOCOL_VERSION

        result = client.apply(
            {"type": "create_document", "payload": {"width": 16, "height": 16}}
        )
        assert isinstance(result, ActionResult)
        assert result.ok and result.action_type == "create_document"

        observation = client.observe()
        assert observation["canvas"] == {"width": 16, "height": 16}
        assert observation["active_layer"] is None

        rejected = client.apply({"type": "bogus"})
        assert not rejected.ok and "unknown action type" in rejected.error
    finally:
        client.close()
        server.shutdown()


def test_agent_loop_drives_remote_backend(tmp_path):
    server, port = start_direct_server(tmp_path)
    client = KritaRPCExecutor(port=port)
    try:
        client.connect()
        with SessionLogger(tmp_path / "session.jsonl") as logger:
            summary = AgentLoop(client, logger).run(ScriptedPolicy(list(DEMO_ACTIONS)))
        assert summary.ok and summary.stop_reason == "finish"

        png_a = tmp_path / "a.png"
        png_a.write_bytes((tmp_path / "exports" / "remote.png").read_bytes())

        client.reset()
        first_actions = read_actions(tmp_path / "session.jsonl")
        episode_b_dir = tmp_path / "b"
        episode_b_dir.mkdir()
        with SessionLogger(episode_b_dir / "session.jsonl") as logger:
            second_summary = AgentLoop(client, logger).run(ScriptedPolicy(first_actions))
        assert second_summary.ok
        assert (tmp_path / "exports" / "remote.png").read_bytes() == png_a.read_bytes()
    finally:
        client.close()
        server.shutdown()


def test_queued_gate_behaves_like_direct_dispatch(tmp_path):
    server, port = start_queued_server(tmp_path)
    client = KritaRPCExecutor(port=port)
    try:
        client.connect()
        result = client.apply(
            {"type": "create_document", "payload": {"width": 8, "height": 8}}
        )
        assert result.ok
        assert client.observe()["canvas"] == {"width": 8, "height": 8}
    finally:
        client.close()
        server.shutdown()


def test_unknown_kind_raises_protocol_error(tmp_path):
    server, port = start_direct_server(tmp_path)
    client = KritaRPCExecutor(port=port)
    try:
        client.connect()
        raised = False
        try:
            client._request("exorcise")
        except BridgeProtocolError as exc:
            raised = "unknown request kind" in str(exc)
        assert raised
    finally:
        client.close()
        server.shutdown()


def test_shutdown_request_stops_server(tmp_path):
    server, port = start_direct_server(tmp_path)
    client = KritaRPCExecutor(port=port)
    client.connect()
    client.shutdown_server()
    deadline = time.time() + 2.0
    while time.time() < deadline and not server.stopped:
        time.sleep(0.01)
    assert server.stopped
