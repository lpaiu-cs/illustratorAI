import json

from nic_agent.chat import ChatError, OllamaChatClient, OpenAICompatChatClient
from nic_agent.planner import (
    LLMPolicy,
    extract_json_object,
    parse_model_response,
    render_observation,
)


class FakeTransportResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class FakeChatClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("FakeChatClient ran out of scripted responses")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_extract_json_object_handles_plain_fenced_and_embedded():
    assert extract_json_object('{"a": 1}') == {"a": 1}
    assert extract_json_object('```json\n{"b": 2}\n```') == {"b": 2}
    assert extract_json_object('Sure! {"c": 3} hope that helps') == {"c": 3}


def test_parse_model_response_reports_parse_error():
    plan = parse_model_response("I cannot do that.")
    assert plan.parse_error and not plan.actions and not plan.done


def test_render_observation_includes_canvas_layers_and_errors():
    text = render_observation(
        {
            "canvas": {"width": 32, "height": 32},
            "active_layer": "base",
            "layers": [{"id": "base", "kind": "paint", "visible": True, "opacity": 1.0}],
            "changed_bbox": [4, 4, 8, 8],
            "error": "stroke_failed: boom",
        }
    )
    assert "canvas: 32x32" in text
    assert "base(paint" in text
    assert "LAST_ACTION_ERROR: stroke_failed: boom" in text


def test_policy_drains_action_block_before_calling_client_again():
    client = FakeChatClient(
        [
            json.dumps(
                {
                    "thought": "start",
                    "actions": [
                        {
                            "type": "create_document",
                            "payload": {"width": 8, "height": 8, "background_color": "#FFFFFFFF"},
                        },
                        {
                            "type": "create_layer",
                            "payload": {"layer_id": "l", "name": "L", "kind": "paint"},
                        },
                    ],
                }
            )
        ]
    )
    policy = LLMPolicy(client, goal="a dot")
    first = policy.next_action({"canvas": None})
    second = policy.next_action({"canvas": {"width": 8, "height": 8}})
    assert first["type"] == "create_document"
    assert second["type"] == "create_layer"
    assert len(client.calls) == 1


def test_done_emits_finish_then_stops():
    client = FakeChatClient([json.dumps({"done": True})])
    policy = LLMPolicy(client, goal="nothing")
    action = policy.next_action({"canvas": None})
    assert action == {"type": "finish"}
    assert policy.next_action({"canvas": None}) is None


def test_invalid_actions_become_feedback_in_next_prompt():
    good_block = json.dumps(
        {"actions": [{"type": "stroke", "payload": {"points": [[0, 0]], "color": "#000", "size": 1}}]}
    )
    client = FakeChatClient(
        [
            good_block,
            json.dumps({"actions": [{"type": "finish"}]}),
        ]
    )
    policy = LLMPolicy(client, goal="line")
    action = policy.next_action({"canvas": None})
    assert action == {"type": "finish"}
    second_prompt = client.calls[1][-1]["content"]
    assert "Feedback on your previous response" in second_prompt
    assert "rejected actions[0]" in second_prompt


def test_fully_rejected_block_retries_within_budget():
    client = FakeChatClient(
        [
            json.dumps(
                {
                    "actions": [
                        {
                            "type": "create_document",
                            "payload": {"width": 64, "height": 64, "background_color": "00000000"},
                        }
                    ]
                }
            ),
            json.dumps(
                {
                    "actions": [
                        {
                            "type": "create_document",
                            "payload": {
                                "width": 64,
                                "height": 64,
                                "background_color": "#00000000",
                            },
                        },
                        {"type": "finish"},
                    ]
                }
            ),
        ]
    )
    policy = LLMPolicy(client, goal="retry")
    first = policy.next_action({"canvas": None})
    assert first["type"] == "create_document"
    assert len(client.calls) == 2
    assert "rejected actions[0]" in client.calls[1][-1]["content"]
    assert "unsupported color format" in client.calls[1][-1]["content"]


def test_parse_failure_triggers_retry_with_feedback():
    client = FakeChatClient(
        [
            "no json here",
            json.dumps({"actions": [{"type": "finish"}]}),
        ]
    )
    policy = LLMPolicy(client, goal="x")
    action = policy.next_action({"canvas": None})
    assert action == {"type": "finish"}
    retry_prompt = client.calls[1][-1]["content"]
    assert "previous response was not valid JSON" in retry_prompt


def test_max_blocks_limit_returns_none():
    responses = [json.dumps({"actions": [{"type": "finish"}]}) for _ in range(5)]
    client = FakeChatClient(responses)
    policy = LLMPolicy(client, goal="loop", max_blocks=3)
    seen = []
    while True:
        action = policy.next_action({"canvas": None})
        if action is None:
            break
        seen.append(action)
    assert len(policy.turns) <= 4


def test_ollama_client_posts_openai_compat_payload_with_images():
    captured = {}

    def transport(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeTransportResponse(
            {"choices": [{"message": {"content": '{"ok": 1}', "reasoning": "hmm"}}]}
        )

    client = OllamaChatClient(
        base_url="http://127.0.0.1:11434", model="qwen3-vl:8b", transport=transport
    )
    messages = [
        {"role": "system", "content": "sys"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
            ],
        },
    ]
    content = client.complete(messages)
    assert content == '{"ok": 1}'
    assert client.last_thinking is None  # OpenAI compat doesn't expose thinking separately
    assert captured["url"].endswith("/v1/chat/completions")
    body = captured["body"]
    assert body["model"] == "qwen3-vl:8b"
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["messages"][1]["content"] == "look"
    assert body["messages"][1]["image_url"][0]["url"].startswith("data:image/png;base64,")
    assert body["max_tokens"] == 8192
    assert body["response_format"] == {"type": "json_object"}


def test_ollama_client_rejects_non_base64_image_urls():
    client = OllamaChatClient(model="m")
    try:
        client.complete(
            [
                {
                    "role": "user",
                    "content": [{"type": "image_url", "image_url": {"url": "http://example.com/x.png"}}],
                }
            ]
        )
    except ChatError as exc:
        assert "base64" in str(exc)
        return
    raise AssertionError("expected ChatError")


def test_policy_attaches_canvas_image_when_provider_given():
    client = FakeChatClient([json.dumps({"actions": [{"type": "finish"}]})])
    policy = LLMPolicy(client, goal="g", image_provider=lambda: "UElY")
    action = policy.next_action({"canvas": None})
    assert action == {"type": "finish"}
    user_message = client.calls[0][-1]
    assert isinstance(user_message["content"], list)
    assert user_message["content"][0]["type"] == "text"
    assert user_message["content"][1]["image_url"]["url"].endswith("base64,UElY")


def test_policy_without_provider_sends_plain_text():
    client = FakeChatClient([json.dumps({"actions": [{"type": "finish"}]})])
    policy = LLMPolicy(client, goal="g")
    policy.next_action({"canvas": None})
    assert isinstance(client.calls[0][-1]["content"], str)


def test_policy_appends_no_think_token_when_suppressed():
    client = FakeChatClient([json.dumps({"actions": [{"type": "finish"}]})])
    policy = LLMPolicy(client, goal="g", suppress_thinking=True)
    assert policy.system_prompt.rstrip().endswith("/no_think")
    policy.next_action({"canvas": None})
    assert client.calls[0][0]["content"] == policy.system_prompt


def test_openai_client_max_tokens_and_json_mode():
    captured = {}

    def transport(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeTransportResponse({"choices": [{"message": {"content": "{}"}}]})

    client = OpenAICompatChatClient(
        base_url="http://127.0.0.1:9999/v1",
        model="m",
        max_tokens=777,
        json_mode=True,
        transport=transport,
    )
    client.complete([{"role": "user", "content": "hi"}])
    assert captured["body"]["max_tokens"] == 777
    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_openai_compat_client_posts_chat_completions_payload():
    captured = {}

    def transport(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeTransportResponse(
            {"choices": [{"message": {"content": '{"ok": true}'}}]}
        )

    client = OpenAICompatChatClient(
        base_url="http://127.0.0.1:9999/v1",
        model="test-model",
        api_key="secret",
        transport=transport,
    )
    content = client.complete([{"role": "user", "content": "hi"}])
    assert content == '{"ok": true}'
    assert captured["url"] == "http://127.0.0.1:9999/v1/chat/completions"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["messages"][-1]["content"] == "hi"


def test_openai_compat_client_wraps_http_errors():
    import urllib.error

    def transport(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 500, "boom", {}, None)

    client = OpenAICompatChatClient(
        base_url="http://127.0.0.1:9999/v1",
        model="m",
        transport=transport,
    )
    try:
        client.complete([])
    except ChatError as exc:
        assert "HTTP 500" in str(exc)
        return
    raise AssertionError("expected ChatError")
