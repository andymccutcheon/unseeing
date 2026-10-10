"""ASGI middleware hook that freewhirr (or any ASGI proxy) can wrap around."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Callable

from unseeing.restore import StreamRestorer
from unseeing.scrubber import Scrubber

Receive = Callable[[], Any]
Send = Callable[[dict[str, Any]], Any]


class UnseeingMiddleware:
    """Scrub JSON request bodies and restore JSON / SSE responses.

    Looks for ``messages``, ``input``, ``instructions``, and ``system`` in
    JSON payloads — the same fields OpenAI, Anthropic, and freewhirr use.

    Example::

        from unseeing import Scrubber
        from unseeing.asgi import UnseeingMiddleware

        app = UnseeingMiddleware(proxy_app, scrubber=Scrubber(resume=True))
    """

    def __init__(
        self,
        app: Any,
        *,
        scrubber: Scrubber | None = None,
        paths: Sequence[str] | None = None,
    ) -> None:
        self.app = app
        self.scrubber = scrubber or Scrubber()
        self.paths = set(paths) if paths is not None else None

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if self.paths is not None and path not in self.paths:
            await self.app(scope, receive, send)
            return

        body = await _read_body(receive)
        body = self._scrub_request(body)
        headers = [
            (key, value)
            if key != b"content-length"
            else (key, str(len(body)).encode("ascii"))
            for key, value in scope.get("headers", [])
        ]
        new_scope = dict(scope)
        new_scope["headers"] = headers

        sent = False

        async def new_receive() -> dict[str, Any]:
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        restorer = self.scrubber.stream_restorer()
        start_message: dict[str, Any] | None = None
        buffer = bytearray()
        sse = False

        async def new_send(message: dict[str, Any]) -> None:
            nonlocal start_message, sse
            kind = message.get("type")
            if kind == "http.response.start":
                headers_map = {k.lower(): v for k, v in message.get("headers", [])}
                content_type = headers_map.get(b"content-type", b"").decode("latin-1").lower()
                sse = "text/event-stream" in content_type
                if sse:
                    await send(message)
                else:
                    start_message = message
                return
            if kind == "http.response.body":
                chunk = message.get("body", b"") or b""
                more = bool(message.get("more_body"))
                if sse:
                    await send({**message, "body": _restore_sse(chunk, restorer, flush=not more)})
                    return
                buffer.extend(chunk)
                if more:
                    return
                restored = self._restore_response(bytes(buffer))
                headers = list((start_message or {}).get("headers", []))
                headers = [
                    (key, value)
                    if key.lower() != b"content-length"
                    else (key, str(len(restored)).encode("ascii"))
                    for key, value in headers
                ]
                if start_message is not None:
                    await send({**start_message, "headers": headers})
                await send({"type": "http.response.body", "body": restored, "more_body": False})
                return
            await send(message)

        await self.app(new_scope, new_receive, new_send)

    def _scrub_request(self, body: bytes) -> bytes:
        if not body:
            return body
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return body
        return json.dumps(self._scrub_payload(data), ensure_ascii=False).encode("utf-8")

    def _scrub_payload(self, data: Any) -> Any:
        if not isinstance(data, dict):
            return self.scrubber.scrub_any(data)
        out = dict(data)
        if "messages" in out:
            out["messages"] = self.scrubber.scrub_messages(out["messages"])
        if "input" in out:
            out["input"] = self.scrubber.scrub_any(out["input"])
        if "instructions" in out:
            out["instructions"] = self.scrubber.scrub_any(out["instructions"])
        if "system" in out:
            out["system"] = self.scrubber.scrub_any(out["system"])
        return out

    def _restore_response(self, body: bytes) -> bytes:
        if not body:
            return body
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self.scrubber.restore_text(body.decode("utf-8", errors="replace")).encode("utf-8")
        return json.dumps(self.scrubber.restore_any(data), ensure_ascii=False).encode("utf-8")


def _restore_sse(chunk: bytes, restorer: StreamRestorer, *, flush: bool) -> bytes:
    text = chunk.decode("utf-8", errors="replace")
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    for line in lines:
        if line.startswith("data:"):
            prefix, _, payload = line.partition(":")
            payload_nl = ""
            body = payload
            if body.endswith("\r\n"):
                payload_nl = "\r\n"
                body = body[:-2]
            elif body.endswith("\n"):
                payload_nl = "\n"
                body = body[:-1]
            if body.startswith(" "):
                lead = " "
                raw = body[1:]
            else:
                lead = ""
                raw = body
            restored = _restore_sse_payload(raw, restorer)
            out.append(f"{prefix}:{lead}{restored}{payload_nl}")
        else:
            out.append(line)
    if flush:
        tail = restorer.flush()
        if tail:
            out.append(f"data: {json.dumps({'content': tail})}\n")
    return "".join(out).encode("utf-8")


def _restore_sse_payload(raw: str, restorer: StreamRestorer) -> str:
    raw = raw.strip()
    if not raw or raw == "[DONE]":
        return raw
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return restorer.feed(raw)
    if isinstance(data, dict):
        text = _sse_text(data)
        if text is not None:
            restored = restorer.feed(text)
            return json.dumps(_sse_put_text(data, restored), ensure_ascii=False)
        return json.dumps(data, ensure_ascii=False)
    if isinstance(data, str):
        return json.dumps(restorer.feed(data), ensure_ascii=False)
    return raw


def _sse_text(data: dict[str, Any]) -> str | None:
    choices = data.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        delta = choices[0].get("delta") or choices[0].get("message") or {}
        if isinstance(delta, dict) and isinstance(delta.get("content"), str):
            return delta["content"]
    delta = data.get("delta")
    if isinstance(delta, dict) and isinstance(delta.get("text"), str):
        return delta["text"]
    if isinstance(data.get("content"), str):
        return data["content"]
    if isinstance(data.get("text"), str):
        return data["text"]
    return None


def _sse_put_text(data: dict[str, Any], text: str) -> dict[str, Any]:
    out = dict(data)
    choices = out.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        first = dict(choices[0])
        if isinstance(first.get("delta"), dict):
            delta = dict(first["delta"])
            delta["content"] = text
            first["delta"] = delta
        elif isinstance(first.get("message"), dict):
            message = dict(first["message"])
            message["content"] = text
            first["message"] = message
        out["choices"] = [first, *choices[1:]]
        return out
    if isinstance(out.get("delta"), dict):
        delta = dict(out["delta"])
        if "text" in delta:
            delta["text"] = text
        else:
            delta["content"] = text
        out["delta"] = delta
        return out
    if "content" in out:
        out["content"] = text
    elif "text" in out:
        out["text"] = text
    return out


async def _read_body(receive: Receive) -> bytes:
    chunks = bytearray()
    while True:
        message = await receive()
        if message.get("type") != "http.request":
            break
        chunks.extend(message.get("body") or b"")
        if not message.get("more_body"):
            break
    return bytes(chunks)

