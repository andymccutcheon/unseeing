from __future__ import annotations

from unseeing import Scrubber
from unseeing.anthropic import UnseeingAnthropic


class _FakeMessages:
    def __init__(self) -> None:
        self.last = None

    def create(self, **kwargs):
        self.last = kwargs
        if kwargs.get("stream"):
            return iter(
                [
                    {"delta": {"text": "Hi <"}},
                    {"delta": {"text": "PERSON_1>"}},
                ]
            )
        return {
            "content": [
                {"type": "text", "text": "Hello <PERSON_1>"},
                {"type": "tool_use", "name": "lookup", "input": {"name": "<PERSON_1>"}},
            ]
        }


class _FakeAnthropic:
    def __init__(self) -> None:
        self.messages = _FakeMessages()
        self.timeout = 30


def test_anthropic_messages_and_tools() -> None:
    client = _FakeAnthropic()
    wrapped = UnseeingAnthropic(client, scrubber=Scrubber(resume=True))
    result = wrapped.messages.create(
        model="demo",
        system="Never mention Ava Chen",
        messages=[{"role": "user", "content": "Ava Chen applied."}],
    )
    assert "Ava Chen" not in client.messages.last["system"]
    assert "Ava Chen" not in client.messages.last["messages"][0]["content"]
    assert result["content"][0]["text"] == "Hello Ava Chen"
    assert result["content"][1]["input"]["name"] == "Ava Chen"


def test_anthropic_stream() -> None:
    client = _FakeAnthropic()
    wrapped = UnseeingAnthropic(client, scrubber=Scrubber(resume=True))
    wrapped.messages.create(
        model="demo",
        messages=[{"role": "user", "content": "Ava Chen applied."}],
    )
    parts = []
    for event in wrapped.messages.create(
        model="demo",
        messages=[{"role": "user", "content": "ping"}],
        stream=True,
    ):
        parts.append(event["delta"]["text"])
    assert "".join(parts) == "Hi Ava Chen"


def test_anthropic_passthrough() -> None:
    assert UnseeingAnthropic(_FakeAnthropic()).timeout == 30
