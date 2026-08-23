from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Protocol


class ChatError(RuntimeError):
    pass


class ChatClient(Protocol):
    def complete(self, messages: list[dict[str, Any]]) -> str: ...


class OpenAICompatChatClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        *,
        timeout: float = 60.0,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        json_mode: bool = False,
        transport: Callable[..., Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.json_mode = json_mode
        self._transport = transport if transport is not None else urllib.request.urlopen

    def complete(self, messages: list[dict[str, Any]]) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": list(messages),
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with self._transport(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ChatError(f"chat endpoint returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ChatError(f"chat endpoint unreachable: {exc}") from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ChatError(f"unexpected chat response shape: {body!r}") from exc
        return str(content)


class OllamaChatClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "",
        *,
        max_tokens: int = 8192,
        timeout: float = 300.0,
        temperature: float = 0.7,
        transport: Callable[..., Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.temperature = temperature
        self.last_thinking: str | None = None
        self._transport = transport if transport is not None else urllib.request.urlopen

    def complete(self, messages: list[dict[str, Any]]) -> str:
        payload_messages = []
        for message in messages:
            text, images = _split_content_parts(message.get("content"))
            entry: dict[str, Any] = {"role": message.get("role", "user"), "content": text}
            if images:
                entry["images"] = images
            payload_messages.append(entry)
        payload = {
            "model": self.model,
            "messages": payload_messages,
            "format": "json",
            "stream": False,
            "options": {
                "num_predict": self.num_predict,
                "temperature": self.temperature,
            },
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._transport(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ChatError(f"ollama endpoint returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ChatError(f"ollama endpoint unreachable: {exc}") from exc
        message = body.get("message") or {}
        self.last_thinking = message.get("thinking") or None
        content = message.get("content", "")
        # If content is empty but thinking exists, use thinking as content
        if not content and self.last_thinking:
            content = self.last_thinking
        return str(content)

    def complete(self, messages: list[dict[str, Any]]) -> str:
        payload_messages = []
        for message in messages:
            text, images = _split_content_parts(message.get("content"))
            entry: dict[str, Any] = {"role": message.get("role", "user"), "content": text}
            if images:
                entry["image_url"] = [{"url": f"data:image/png;base64,{img}"} for img in images]
            payload_messages.append(entry)
        payload = {
            "model": self.model,
            "messages": payload_messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._transport(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ChatError(f"ollama endpoint returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ChatError(f"ollama endpoint unreachable: {exc}") from exc
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ChatError(f"unexpected chat response shape: {body!r}") from exc
        return str(content)


def _split_content_parts(content: Any) -> tuple[str, list[str]]:
    if isinstance(content, str):
        return content, []
    texts: list[str] = []
    images: list[str] = []
    for part in content:
        kind = part.get("type")
        if kind == "text":
            texts.append(str(part.get("text", "")))
        elif kind == "image_url":
            url = str(part.get("image_url", {}).get("url", ""))
            _, separator, encoded = url.partition("base64,")
            if not separator or not encoded:
                raise ChatError("image_url parts must use data:image/...;base64,... urls")
            images.append(encoded)
        else:
            raise ChatError(f"unsupported message part type: {kind!r}")
    return "\n".join(texts), images



