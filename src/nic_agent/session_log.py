from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator, Mapping


class SessionLogger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._seq = 0
        self._handle = self.path.open("w", encoding="utf-8")

    def log_meta(self, **fields: Any) -> None:
        self._write("meta", fields)

    def log_action(self, action: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        self._write("action", {"action": dict(action), "result": dict(result)})

    def log_observation(self, observation: Mapping[str, Any]) -> None:
        self._write("observation", {"observation": dict(observation)})

    def log_repair(self, fields: Mapping[str, Any]) -> None:
        self._write("repair", dict(fields))

    def close(self) -> None:
        self._handle.close()

    def __enter__(self) -> "SessionLogger":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def _write(self, kind: str, fields: Mapping[str, Any]) -> None:
        self._seq += 1
        record = {"seq": self._seq, "kind": kind, **fields}
        self._handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        self._handle.flush()


def read_events(path: Path) -> Iterator[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def read_actions(path: Path) -> list[dict[str, Any]]:
    return [event["action"] for event in read_events(path) if event.get("kind") == "action"]
