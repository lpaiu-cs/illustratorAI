from nic_agent.session_log import SessionLogger, read_actions, read_events


def test_logger_writes_sequential_typed_events(tmp_path):
    log_path = tmp_path / "session.jsonl"
    with SessionLogger(log_path) as logger:
        logger.log_meta(protocol_version="0.1.0", max_steps=16)
        logger.log_action({"type": "finish"}, {"ok": True, "error": None})
        logger.log_observation({"step": 1, "changed_bbox": None})

    events = list(read_events(log_path))
    assert [event["seq"] for event in events] == [1, 2, 3]
    assert [event["kind"] for event in events] == ["meta", "action", "observation"]
    assert events[1]["action"] == {"type": "finish"}
    assert events[2]["observation"]["step"] == 1


def test_read_actions_extracts_actions_in_order(tmp_path):
    log_path = tmp_path / "session.jsonl"
    with SessionLogger(log_path) as logger:
        logger.log_action(
            {"type": "create_document", "width": 4, "height": 4}, {"ok": True}
        )
        logger.log_observation({"step": 1})
        logger.log_action({"type": "finish"}, {"ok": True})

    actions = read_actions(log_path)
    assert [action["type"] for action in actions] == ["create_document", "finish"]


def test_log_file_is_valid_jsonl_one_object_per_line(tmp_path):
    log_path = tmp_path / "session.jsonl"
    with SessionLogger(log_path) as logger:
        logger.log_meta()
        logger.log_observation({"step": 1})
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    import json

    assert all(isinstance(json.loads(line), dict) for line in lines)
