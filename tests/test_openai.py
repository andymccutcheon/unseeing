from __future__ import annotations

from types import SimpleNamespace

from unseeing import Scrubber
from unseeing.openai import UnseeingOpenAI


class _FakeCompletions:
    def __init__(self) -> None:
        self.last: dict | None = None

    def create(self, **kwargs):
        self.last = kwargs
        if kwargs.get("stream"):
            text = "Reach <EMAIL_1> please"
            return iter(
                [
                    {"choices": [{"delta": {"content": text[:8]}}]},
                    {"choices": [{"delta": {"content": text[8:]}}]},
                ]
            )
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Email <EMAIL_1>",
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "lookup",
                                    "arguments": '{"email": "<EMAIL_1>"}',
                                }
                            }
                        ],
                    }
                }
            ]
        }


class _FakeResponses:
    def create(self, **kwargs):
        self.last = kwargs
        return {"output_text": "See <EMAIL_1>", "output": [{"content": "<EMAIL_1>"}]}


class _FakeClient:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions())
        self.responses = _FakeResponses()
        self.api_key = "sk-test"


def test_openai_chat_and_tools() -> None:
    client = _FakeClient()
    wrapped = UnseeingOpenAI(client, scrubber=Scrubber())
    result = wrapped.chat.completions.create(
        model="demo",
        messages=[
            {
                "role": "user",
                "content": "Write to ada@example.com",
                "tool_calls": [
                    {"function": {"name": "x", "arguments": '{"email": "ada@example.com"}'}}
                ],
            }
        ],
    )
    sent = client.chat.completions.last["messages"][0]
    assert "ada@example.com" not in sent["content"]
    assert "<EMAIL_1>" in sent["content"]
    assert "ada@example.com" not in sent["tool_calls"][0]["function"]["arguments"]
    assert result["choices"][0]["message"]["content"] == "Email ada@example.com"
    args = result["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]
    assert "ada@example.com" in args


def test_openai_stream_and_responses() -> None:
    client = _FakeClient()
    wrapped = UnseeingOpenAI(client, scrubber=Scrubber())
    wrapped.chat.completions.create(
        model="demo",
        messages=[{"role": "user", "content": "ada@example.com"}],
        stream=False,
    )
    parts = []
    for chunk in wrapped.chat.completions.create(
        model="demo",
        messages=[{"role": "user", "content": "ada@example.com"}],
        stream=True,
    ):
        parts.append(chunk["choices"][0]["delta"]["content"])
    assert "".join(parts) == "Reach ada@example.com please"

    result = wrapped.responses.create(input="ping ada@example.com")
    assert "ada@example.com" in result["output_text"]
    assert "ada@example.com" not in client.responses.last["input"]


def test_openai_getattr_passthrough() -> None:
    assert UnseeingOpenAI(_FakeClient()).api_key == "sk-test"
