import json

from nic_agent.stage0 import (
    build_manifest_entry,
    build_repair_message,
    build_sft_training_pair,
    classify_failure,
    extract_sft_samples,
    is_collection_success,
    load_quality_passes,
    load_goals,
    parse_judgement,
    read_manifest,
    replay_fingerprint,
    run_batch,
    summarize_batch,
    validate_sft_sample,
)


def write_goals(tmp_path, lines):
    path = tmp_path / "goals.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def test_load_goals_skips_blanks_and_comments(tmp_path):
    path = write_goals(
        tmp_path,
        [
            "# header comment",
            "Draw a red circle",
            "",
            "   ",
            "Draw a blue square  ",
            "# another comment",
            "Draw a green triangle",
        ],
    )
    assert load_goals(path) == ["Draw a red circle", "Draw a blue square", "Draw a green triangle"]


def test_is_collection_success_requires_finish_and_png():
    assert is_collection_success({"ok": True, "stop_reason": "finish", "exported_png": ["a.png"]})
    assert not is_collection_success({"ok": True, "stop_reason": "max_steps", "exported_png": ["a.png"]})
    assert not is_collection_success({"ok": False, "stop_reason": "finish", "exported_png": []})
    assert not is_collection_success({"ok": True, "stop_reason": "finish", "exported_png": []})


def test_build_manifest_entry_carries_summary_fields():
    summary = {
        "steps": 5,
        "ok": True,
        "stop_reason": "finish",
        "fingerprint": "crc32:abcd1234",
        "blocks_used": 3,
        "exported_png": ["smiley.png"],
        "session_log": "out/session.jsonl",
        "last_feedback": [],
    }
    entry = build_manifest_entry(7, "Draw a cat", summary)
    assert entry["index"] == 7
    assert entry["goal"] == "Draw a cat"
    assert entry["success"] is True
    assert entry["fingerprint"] == "crc32:abcd1234"
    assert "last_feedback" not in entry


def test_run_batch_runs_all_and_writes_manifest(tmp_path):
    calls = []

    def runner(index, goal):
        calls.append((index, goal))
        return {
            "steps": 4 + index,
            "ok": index != 1,
            "stop_reason": "finish" if index != 1 else "max_steps",
            "fingerprint": f"crc32:{index:08x}",
            "blocks_used": 2,
            "exported_png": [] if index == 1 else [f"g{index}.png"],
            "session_log": str(tmp_path / f"goal_{index:04d}" / "session.jsonl"),
            "last_feedback": [],
        }

    manifest = tmp_path / "manifest.jsonl"
    entries = run_batch(["goal a", "goal b", "goal c"], runner, manifest_path=manifest)

    assert calls == [(0, "goal a"), (1, "goal b"), (2, "goal c")]
    assert [entry["index"] for entry in entries] == [0, 1, 2]
    assert entries[1]["success"] is False
    assert summarize_batch(entries) == {"total": 3, "succeeded": 2, "failed": 1}
    raw_lines = manifest.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(raw_lines[0])["goal"] == "goal a"


def test_run_batch_resume_skips_succeeded_and_retries_failed(tmp_path):
    outcomes = {
        0: {"ok": True, "stop_reason": "finish", "exported_png": ["a.png"]},
        1: {"ok": False, "stop_reason": "max_steps", "exported_png": []},
    }

    def first_runner(index, goal):
        outcome = dict(outcomes[index])
        outcome.update(
            steps=2,
            fingerprint=f"crc32:{index:08x}",
            blocks_used=2,
            session_log="log",
            last_feedback=[],
        )
        return outcome

    manifest = tmp_path / "manifest.jsonl"
    run_batch(["g0", "g1"], first_runner, manifest_path=manifest)

    retried = []

    def second_runner(index, goal):
        retried.append(index)
        return {
            "steps": 9,
            "ok": True,
            "stop_reason": "finish",
            "fingerprint": f"crc32:{index:08x}",
            "blocks_used": 2,
            "exported_png": [f"retry{index}.png"],
            "session_log": "log",
            "last_feedback": [],
        }

    logs: list[str] = []
    entries = run_batch(
        ["g0", "g1"],
        second_runner,
        manifest_path=manifest,
        resume=True,
        log=logs.append,
    )

    assert retried == [1]
    assert any("skip" in line for line in logs)
    assert len(entries) == 3
    assert [entry["success"] for entry in entries] == [True, False, True]
    assert summarize_batch(entries)["succeeded"] == 2


def test_read_manifest_missing_file_returns_empty(tmp_path):
    assert read_manifest(tmp_path / "missing.jsonl") == []


def test_classify_failure_returns_empty_for_success():
    summary = {"ok": True, "stop_reason": "finish", "exported_png": ["a.png"], "last_feedback": []}
    assert classify_failure(summary, {"canvas": {"width": 8, "height": 8}}) == []


def test_classify_failure_without_canvas_is_no_document():
    summary = {"ok": False, "stop_reason": "policy_exhausted", "exported_png": [], "last_feedback": []}
    assert classify_failure(summary, {"canvas": None}) == ["no_document"]


def test_classify_failure_exhausted_with_export_is_done_missing():
    summary = {"ok": True, "stop_reason": "policy_exhausted", "exported_png": ["a.png"], "last_feedback": []}
    assert classify_failure(summary, {"canvas": {"width": 8, "height": 8}}) == ["done_missing"]


def test_classify_failure_without_export_is_export_missing():
    observation = {"canvas": {"width": 8, "height": 8}}
    finished_no_export = {"ok": True, "stop_reason": "finish", "exported_png": [], "last_feedback": []}
    assert classify_failure(finished_no_export, observation) == ["export_missing"]
    exhausted_no_export = {"ok": False, "stop_reason": "max_steps", "exported_png": [], "last_feedback": []}
    assert classify_failure(exhausted_no_export, observation) == [
        "action_failures",
        "export_missing",
    ]


def test_classify_failure_flags_invalid_response_from_last_feedback():
    summary = {
        "ok": True,
        "stop_reason": "policy_exhausted",
        "exported_png": ["a.png"],
        "last_feedback": ["previous response was not valid JSON: boom"],
    }
    assert classify_failure(summary, {"canvas": {"width": 8, "height": 8}}) == [
        "invalid_response",
        "done_missing",
    ]


def test_build_repair_message_lists_each_class_hint():
    message = build_repair_message(["done_missing", "export_missing"])
    assert "- done_missing:" in message
    assert "- export_missing:" in message
    assert '"done": true' in message


def test_extract_sft_samples_pairs_contexts_with_assistant_turns():
    conversation = [
        {"role": "system", "content": "You are the planner."},
        {"role": "user", "content": "Goal: draw a cat"},
        {"role": "assistant", "content": '{"actions": [{"type": "create_document"}]}'},
        {"role": "user", "content": "canvas: 8x8"},
        {"role": "assistant", "content": '{"actions": [], "done": true}'},
    ]
    samples = extract_sft_samples(
        conversation, {"index": 3, "goal": "draw a cat", "repair_rounds_used": 1}
    )
    assert len(samples) == 2
    assert samples[0]["turn"] == 1 and samples[1]["turn"] == 2
    assert all(sample["goal"] == "draw a cat" for sample in samples)
    assert samples[0]["source_index"] == 3
    assert samples[0]["used_repair"] is True
    assert len(samples[0]["messages"]) == 3
    assert samples[0]["messages"][-1]["role"] == "assistant"
    assert len(samples[1]["messages"]) == 5


def test_extract_sft_samples_elides_image_parts_via_conversation_copy():
    from nic_agent.planner import LLMPolicy

    class OneShotClient:
        def complete(self, messages):
            return '{"actions": [{"type": "finish"}]}'

    policy = LLMPolicy(OneShotClient(), goal="g", image_provider=lambda: "UElY")
    policy.next_action({"step": 0})
    samples = extract_sft_samples(
        policy.conversation(), {"index": 0, "goal": "g", "repair_rounds_used": 0}
    )
    contents = [message["content"] for sample in samples for message in sample["messages"]]
    assert all(isinstance(content, str) for content in contents)
    assert "[image]" in contents


def test_validate_sft_sample_accepts_wellformed_and_rejects_broken():
    good = {
        "messages": [
            {"role": "user", "content": "goal"},
            {"role": "assistant", "content": '{"thought": "t", "actions": [], "done": true}'},
        ]
    }
    assert validate_sft_sample(good) == []

    unparseable = {"messages": [{"role": "assistant", "content": "no json here"}]}
    assert any("unparseable" in issue for issue in validate_sft_sample(unparseable))

    missing_done = {
        "messages": [{"role": "assistant", "content": '{"thought": "t", "actions": []}'}]
    }
    assert any("done" in issue for issue in validate_sft_sample(missing_done))

    empty = {"messages": [{"role": "assistant", "content": ""}]}
    assert any("empty" in issue for issue in validate_sft_sample(empty))


def test_replay_fingerprint_matches_headless_document():
    actions = [
        {
            "type": "create_document",
            "payload": {"width": 16, "height": 16, "background_color": "#FFFFFFFF"},
        },
        {"type": "finish"},
    ]
    fingerprint = replay_fingerprint(actions)
    assert fingerprint is not None
    assert fingerprint == replay_fingerprint(actions)

    from nic_agent.simulator import HeadlessDocument

    document = HeadlessDocument(
        width=16,
        height=16,
        background_rgba=(255, 255, 255, 255),
        file_name="untitled",
    )
    assert fingerprint == document.fingerprint()


def test_parse_judgement_accepts_wellformed_and_rejects_broken():
    verdict = parse_judgement('{"match": true, "score": 8, "missing": [], "reasoning": "ok"}')
    assert verdict == {"match": True, "score": 8, "missing": [], "reasoning": "ok"}
    assert parse_judgement("no json") is None
    assert parse_judgement('{"match": "yes", "score": 5}') is None
    assert parse_judgement('{"match": true, "score": "high"}') is None
    clamped = parse_judgement('{"match": false, "score": 42, "missing": ["eyes"], "reasoning": "r"}')
    assert clamped["score"] == 10


def test_load_quality_passes_filters_by_match_and_score(tmp_path):
    path = tmp_path / "quality.jsonl"
    records = [
        {"session_log": r"C:\a\session.jsonl", "match": True, "score": 7},
        {"session_log": r"C:\b\session.jsonl", "match": False, "score": 9},
        {"session_log": r"C:\c\session.jsonl", "match": True, "score": 4},
    ]
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    passes = load_quality_passes([path], min_score=6)
    assert len(passes) == 1
    key = next(iter(passes))
    assert key.endswith("c:\\a\\session.jsonl")


def test_load_quality_passes_missing_file_returns_empty(tmp_path):
    assert load_quality_passes([tmp_path / "missing.jsonl"], min_score=6) == {}


class FakeTokenizer:
    """Chat template where each message contributes one token id (100+index)."""

    def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=False):
        ids = [100 + index for index, _ in enumerate(messages)]
        if add_generation_prompt:
            ids.append(999)
        return ids


def test_build_sft_training_pair_masks_everything_but_final_assistant():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "goal"},
        {"role": "assistant", "content": '{"actions": []}'},
    ]
    pair = build_sft_training_pair(FakeTokenizer(), messages)
    assert pair["input_ids"] == [100, 101, 102]
    assert pair["labels"] == [-100, -100, 102]


def test_build_sft_training_pair_left_truncates_keeping_targets():
    messages = [
        {"role": "user", "content": f"turn {i}"} for i in range(5)
    ] + [{"role": "assistant", "content": "reply"}]
    pair = build_sft_training_pair(FakeTokenizer(), messages, max_len=3)
    assert pair["input_ids"] == [103, 104, 105]
    assert pair["labels"] == [-100, -100, 105]


def test_build_sft_training_pair_requires_assistant_tail():
    try:
        build_sft_training_pair(FakeTokenizer(), [{"role": "user", "content": "x"}])
    except ValueError as exc:
        assert "assistant" in str(exc)
        return
    raise AssertionError("expected ValueError")
