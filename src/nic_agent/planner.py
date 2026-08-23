from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping

from nic_agent.models import ActionValidationError
from nic_agent.validator import validate_action_payload

MAX_POINTS_PER_STROKE = 64


ACTION_SUMMARY = """\
- create_document {width:int, height:int, background_color:"#RRGGBBAA", file_name:str} - first action only
- create_layer {layer_id:str, name:str, kind:"paint"|"group"|"vector", parent_id?:str}
- select_layer {layer_id:str}
- fill_rect {x:int, y:int, width:int, height:int, color:str}
- stroke {points:[[x,y], ...2..%d items], color:"#RRGGBBAA", size:number>0, opacity?:0..1} - active layer must be paint
- add_svg {svg:string} - inject SVG into the active VECTOR layer; subset: rect,circle,ellipse,line,polyline,polygon,path(M/L/H/V/C/Q/A/Z); absolute coordinates only. **IMPORTANT: SVG must have exactly ONE root element. For multiple shapes, wrap them in a <g> group.**
- set_layer_properties {layer_id:str, visible?:bool, opacity?:number 0..1}
- export_png {file_name:str} - call near the end
- finish {} - or set done=true""" % MAX_POINTS_PER_STROKE

DEFAULT_SYSTEM_PROMPT = f"""\
You are the planner of an agentic drawing system. You control a Krita-style document through discrete actions.

Each turn you receive the latest observation of the document. Respond with exactly one JSON object and nothing else:

{{"thought": "<brief reasoning>", "actions": [<action>, ...], "done": false}}

Each action is an object: {{"type": "<type>", "payload": {{...}}}}.

Supported types:
{ACTION_SUMMARY}

Rules:
- If no document exists yet (canvas is none), your first action MUST be create_document.
- "actions" must be a non-empty array unless "done" is true.
- Build the image incrementally: background first, then large shapes, then details.
- Prefer vector layers + add_svg for precise geometric shapes (circles, curves); use stroke for organic lines on paint layers.
- Group related layers (kind:"group") so a human can edit them later (e.g. sketch/line/color groups).
- Canvas coordinates are integers within [0,width) x [0,height).
- There is no implicit root layer. Omit parent_id for top-level layers; use parent_id only with the id of an existing group layer.
- Create a layer BEFORE select_layer/add_svg on it. After any error, read the layer list in the observation and retry only the failed step with corrected actions. Never repeat create_document once it succeeded.
- Each add_svg ADDS new shapes on top of what the layer already contains. Never resend shapes that are already correct; send only the missing/corrected parts.
- Completion: when the rendered image matches the goal and export_png has succeeded, your next response MUST be {{"thought": "...", "actions": [], "done": true}}. Do not keep polishing a finished drawing.
- Rejected actions and runtime errors are reported back to you; correct them on your next turn.

A rendered image of the current canvas is attached with each observation. Inspect it carefully, compare against the goal, and critique your own work before deciding actions."""

VISION_PROMPT_ADDENDUM = (
    "\n\nA rendered image of the current canvas is attached with each observation."
    " Inspect it carefully, compare against the goal, and critique your own work before deciding actions."
)


@dataclass(slots=True, frozen=True)
class ModelPlan:
    thought: str | None
    actions: tuple[dict[str, Any], ...]
    done: bool
    parse_error: str | None = None


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL)
    sources = [fence.group(1), stripped] if fence else [stripped]
    decoder = json.JSONDecoder()
    for source in sources:
        try:
            parsed = json.loads(source.strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        index = source.find("{")
        while index != -1:
            try:
                parsed, _end = decoder.raw_decode(source[index:])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
            index = source.find("{", index + 1)
    raise ValueError("no JSON object found in model response")


def parse_model_response(raw_text: str) -> ModelPlan:
    try:
        payload = extract_json_object(raw_text)
    except ValueError as exc:
        return ModelPlan(None, (), False, parse_error=str(exc))
    thought_value = payload.get("thought")
    thought = str(thought_value) if thought_value else None
    raw_actions = payload.get("actions", [])
    if not isinstance(raw_actions, list):
        return ModelPlan(thought, (), bool(payload.get("done")), "actions must be an array")
    actions: list[dict[str, Any]] = []
    for index, item in enumerate(raw_actions):
        if not isinstance(item, dict):
            return ModelPlan(
                thought,
                tuple(actions),
                False,
                parse_error=f"actions[{index}] must be an object",
            )
        actions.append(item)
    return ModelPlan(thought, tuple(actions), bool(payload.get("done")))


def validate_model_actions(
    actions: tuple[dict[str, Any], ...]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, action in enumerate(actions):
        try:
            validate_action_payload(action)
        except ActionValidationError as exc:
            rejected.append({"index": index, "action": action, "error": str(exc)})
        else:
            accepted.append(action)
    return accepted, rejected


def render_observation(observation: Mapping[str, Any]) -> str:
    canvas = observation.get("canvas")
    lines: list[str] = []
    if canvas is None:
        lines.append("canvas: none (no document yet)")
    else:
        lines.append(f"canvas: {canvas['width']}x{canvas['height']}")
    lines.append(f"active_layer: {observation.get('active_layer')}")
    layers = observation.get("layers") or []
    if layers:
        rendered_layers = ", ".join(
            "{id}({kind}, visible={visible}, opacity={opacity})".format(**layer)
            for layer in layers
        )
        lines.append(f"layers: {rendered_layers}")
    else:
        lines.append("layers: none")
    lines.append(f"changed_bbox: {observation.get('changed_bbox')}")
    error = observation.get("error")
    if error:
        lines.append(f"LAST_ACTION_ERROR: {error}")
    return "\n".join(lines)


class LLMPolicy:
    def __init__(
        self,
        chat_client: Any,
        goal: str,
        *,
        max_blocks: int = 32,
        history_turns: int = 12,
        system_prompt: str | None = None,
        image_provider: Any = None,
        suppress_thinking: bool = False,
    ) -> None:
        self.chat_client = chat_client
        self.goal = goal
        self.max_blocks = max_blocks
        self.history_turns = history_turns
        self.image_provider = image_provider
        resolved_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        if image_provider is not None:
            resolved_prompt += VISION_PROMPT_ADDENDUM
        if suppress_thinking:
            resolved_prompt += " /no_think"
        self.system_prompt = resolved_prompt
        self.blocks_used = 0
        self.turns: list[ModelPlan] = []
        self.last_feedback: list[str] = []
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt}
        ]
        self._pending: deque[dict[str, Any]] = deque()
        self._done = False

    def next_action(self, observation: Mapping[str, Any]) -> Mapping[str, Any] | None:
        while not self._pending:
            if self._done or self.blocks_used >= self.max_blocks:
                return None
            self._request_block(observation)
        return self._pending.popleft()

    def _request_block(self, observation: Mapping[str, Any]) -> None:
        self.blocks_used += 1
        user_content = self._render_user_content(observation)
        self._append_user_message(user_content)
        raw_text = self.chat_client.complete(self._trimmed_messages())
        plan = parse_model_response(raw_text)
        self.turns.append(plan)
        self._messages.append({"role": "assistant", "content": raw_text})
        self.last_feedback = []

        if plan.parse_error is not None:
            self.last_feedback.append(f"previous response was not valid JSON: {plan.parse_error}")
            return
        if plan.done and not plan.actions:
            self._done = True
            self._pending.append({"type": "finish"})
            return
        accepted, rejected = validate_model_actions(plan.actions)
        for item in rejected:
            self.last_feedback.append(
                f"rejected actions[{item['index']}]: {json.dumps(item['action'], ensure_ascii=False)} -> {item['error']}"
            )
        if plan.done:
            self._done = True
            if not accepted or accepted[-1].get("type") != "finish":
                accepted.append({"type": "finish"})
        if not accepted:
            self.last_feedback.append("previous block contained no usable actions")
        self._pending.extend(accepted)

    def _render_user_content(self, observation: Mapping[str, Any]) -> Any:
        parts = [f"Goal: {self.goal}", "", render_observation(observation)]
        if self.last_feedback:
            parts.append("")
            parts.append("Feedback on your previous response:")
            for item in self.last_feedback:
                parts.append(f"- {item}")
        parts.append("")
        parts.append("Respond with the next JSON block.")
        text = "\n".join(parts)
        if self.image_provider is None:
            return text
        canvas_b64 = self.image_provider()
        if not canvas_b64:
            return text
        return [
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{canvas_b64}"},
            },
        ]

    def _append_user_message(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})

    def _trimmed_messages(self) -> list[dict[str, Any]]:
        head = self._messages[:2]
        tail = self._messages[2:]
        keep_count = self.history_turns * 2
        keep_from = max(0, len(tail) - keep_count)
        keep_from -= keep_from % 2
        return head + tail[keep_from:]
