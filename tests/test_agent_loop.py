from nic_agent.executor import ActionExecutor
from nic_agent.headless_backend import HeadlessBackend
from nic_agent.loop import AgentLoop
from nic_agent.policy import ScriptedPolicy
from nic_agent.session_log import SessionLogger, read_actions, read_events

DEMO_ACTIONS = [
    {
        "type": "create_document",
        "payload": {"width": 32, "height": 32, "background_color": "#FFFFFFFF"},
    },
    {
        "type": "create_layer",
        "payload": {"layer_id": "base", "name": "Base", "kind": "paint"},
    },
    {
        "type": "fill_rect",
        "payload": {"x": 4, "y": 4, "width": 12, "height": 12, "color": "#3366CC"},
    },
    {
        "type": "stroke",
        "payload": {"points": [[4, 24], [28, 24]], "color": "#CC3333", "size": 3},
    },
    {
        "type": "set_layer_properties",
        "payload": {"layer_id": "base", "opacity": 0.5},
    },
    {"type": "finish"},
]


def run_session(output_dir, actions=None):
    output_dir.mkdir(parents=True, exist_ok=True)
    executor = ActionExecutor(HeadlessBackend())
    log_path = output_dir / "session.jsonl"
    with SessionLogger(log_path) as logger:
        summary = AgentLoop(executor, logger).run(
            ScriptedPolicy(list(actions if actions is not None else DEMO_ACTIONS))
        )
    return executor, summary, log_path


def test_loop_runs_to_finish_and_logs_action_observation_pairs(tmp_path):
    _, summary, log_path = run_session(tmp_path / "a")
    assert summary.ok
    assert summary.stop_reason == "finish"

    events = list(read_events(log_path))
    assert events[0]["kind"] == "meta"
    kinds = [event["kind"] for event in events]
    assert kinds.count("action") == len(DEMO_ACTIONS)
    assert "observation" in kinds

    observations = [event["observation"] for event in events if event["kind"] == "observation"]
    deltas = [entry.get("changed_bbox") for entry in observations]
    assert any(delta is not None for delta in deltas)


def test_replay_from_session_log_produces_identical_fingerprint(tmp_path):
    _, first_summary, log_path = run_session(tmp_path / "first")
    replayed_actions = read_actions(log_path)
    _, second_summary, _ = run_session(tmp_path / "second", replayed_actions)

    assert first_summary.fingerprint is not None
    assert first_summary.fingerprint == second_summary.fingerprint


def test_failed_actions_are_logged_and_loop_continues(tmp_path):
    actions = [
        {"type": "create_layer", "payload": {"layer_id": "x", "name": "X", "kind": "paint"}},
        {"type": "create_document", "payload": {"width": 16, "height": 16}},
        {"type": "create_layer", "payload": {"layer_id": "x", "name": "X", "kind": "paint"}},
        {"type": "create_layer", "payload": {"layer_id": "y", "name": "Y", "kind": "paint"}},
        {"type": "create_layer", "payload": {"layer_id": "x", "name": "X2", "kind": "paint"}},
        {"type": "finish"},
    ]
    _, summary, log_path = run_session(tmp_path, actions)
    assert summary.ok and summary.stop_reason == "finish"

    failed = [
        event for event in read_events(log_path)
        if event["kind"] == "action" and not event["result"]["ok"]
    ]
    assert len(failed) == 2
    assert failed[0]["result"]["error"] == "no_document"
    assert failed[1]["result"]["error"] == "duplicate_layer_id"


def test_too_many_consecutive_failures_stops_loop(tmp_path):
    actions = [{"type": "select_layer", "payload": {"layer_id": "ghost"}} for _ in range(20)]
    _, summary, _ = run_session(tmp_path, actions)
    assert not summary.ok and summary.stop_reason == "too_many_failures"


def test_rerun_starts_from_current_document_state(tmp_path):
    # Repair rounds call AgentLoop.run again on the same executor: the first
    # observation must show the existing document, not a blank session.
    executor, _, _ = run_session(tmp_path, DEMO_ACTIONS[:2])
    seen = []

    class RecordingPolicy:
        def next_action(self, observation):
            seen.append(dict(observation))
            return None

    with SessionLogger(tmp_path / "repair.jsonl") as logger:
        AgentLoop(executor, logger).run(RecordingPolicy())
    assert seen[0]["canvas"] == {"width": 32, "height": 32}
    assert [layer["id"] for layer in seen[0]["layers"]] == ["base"]


def test_error_observations_include_full_state(tmp_path):
    actions = [
        {"type": "create_document", "payload": {"width": 16, "height": 16}},
        {"type": "select_layer", "payload": {"layer_id": "ghost"}},
        {"type": "finish"},
    ]
    _, _, log_path = run_session(tmp_path / "err", actions)
    observations = [
        event["observation"] for event in read_events(log_path) if event["kind"] == "observation"
    ]
    error_observation = next(entry for entry in observations if "error" in entry)
    assert error_observation["error"] == "unknown_layer"
    assert error_observation["canvas"] == {"width": 16, "height": 16}
    assert error_observation["layers"] == []
