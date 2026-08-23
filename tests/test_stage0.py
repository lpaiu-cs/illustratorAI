import json

from nic_agent.stage0 import (
    build_manifest_entry,
    is_collection_success,
    load_goals,
    read_manifest,
    run_batch,
    summarize_batch,
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
