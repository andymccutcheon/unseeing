from __future__ import annotations

import json

import pytest

from unseeing import Scrubber, UnseeingMiddleware


async def _echo_app(scope, receive, send):
    body = bytearray()
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        body.extend(message.get("body") or b"")
        if not message.get("more_body"):
            break
    payload = json.loads(bytes(body).decode("utf-8"))
    reply = {
        "choices": [
            {"message": {"role": "assistant", "content": f"echo {payload['messages'][0]['content']}"}}
        ]
    }
    raw = json.dumps(reply).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json"), (b"content-length", b"0")],
        }
    )
    await send({"type": "http.response.body", "body": raw, "more_body": False})


async def _sse_app(scope, receive, send):
    _ = await receive()
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/event-stream")],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": b'data: {"content":"<EMAIL_1>"}\n',
            "more_body": False,
        }
    )


async def _call(app, path: str, payload: dict) -> tuple[int, bytes, list]:
    body = json.dumps(payload).encode("utf-8")
    messages = [{"type": "http.request", "body": body, "more_body": False}]
    sent: list[dict] = []

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "path": path,
        "headers": [(b"content-type", b"application/json")],
    }
    await app(scope, receive, send)
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    chunks = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, chunks, sent


@pytest.mark.asyncio
async def test_asgi_json_roundtrip() -> None:
    scrubber = Scrubber()
    app = UnseeingMiddleware(_echo_app, scrubber=scrubber)
    status, body, _ = await _call(
        app,
        "/v1/chat/completions",
        {"messages": [{"role": "user", "content": "ping ada@example.com"}]},
    )
    assert status == 200
    data = json.loads(body)
    assert "ada@example.com" in data["choices"][0]["message"]["content"]
    assert "<EMAIL_" not in data["choices"][0]["message"]["content"]


@pytest.mark.asyncio
async def test_asgi_sse() -> None:
    scrubber = Scrubber()
    scrubber.scrub("ada@example.com")
    app = UnseeingMiddleware(_sse_app, scrubber=scrubber)
    _, body, _ = await _call(app, "/v1/chat/completions", {"messages": []})
    assert b"ada@example.com" in body
