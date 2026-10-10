"""OpenAI SDK wrapper: chat completions and Responses, including streams."""

from __future__ import annotations

from typing import Any

from unseeing.restore import AsyncStreamAdapter, StreamAdapter
from unseeing.scrubber import Scrubber


class UnseeingOpenAI:
    """Drop-in wrapper around an OpenAI (or compatible) client.

    Scrubs outgoing ``messages`` / ``input`` / tool arguments and restores
    incoming content, including streamed deltas and tool-call arguments.
    """

    def __init__(self, client: Any, *, scrubber: Scrubber | None = None, **kwargs: Any) -> None:
        self._client = client
        self.scrubber = scrubber or Scrubber(**kwargs)
        chat = getattr(client, "chat", None)
        if chat is not None:
            self.chat = _ChatProxy(chat, self.scrubber)
        responses = getattr(client, "responses", None)
        if responses is not None:
            self.responses = _ResponsesProxy(responses, self.scrubber)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class _ChatProxy:
    def __init__(self, chat: Any, scrubber: Scrubber) -> None:
        self.completions = _CompletionsProxy(chat.completions, scrubber)


class _CompletionsProxy:
    def __init__(self, completions: Any, scrubber: Scrubber) -> None:
        self._inner = completions
        self.scrubber = scrubber

    def create(self, **kwargs: Any) -> Any:
        return _create_chat(self._inner, self.scrubber, kwargs)

    async def acreate(self, **kwargs: Any) -> Any:  # pragma: no cover - alias
        return await _acreate_chat(self._inner, self.scrubber, kwargs)


class _ResponsesProxy:
    def __init__(self, responses: Any, scrubber: Scrubber) -> None:
        self._inner = responses
        self.scrubber = scrubber

    def create(self, **kwargs: Any) -> Any:
        return _create_responses(self._inner, self.scrubber, kwargs)


def wrap_openai(client: Any, *, scrubber: Scrubber | None = None, **kwargs: Any) -> UnseeingOpenAI:
    return UnseeingOpenAI(client, scrubber=scrubber, **kwargs)


def _scrub_chat_kwargs(scrubber: Scrubber, kwargs: dict[str, Any]) -> dict[str, Any]:
    out = dict(kwargs)
    if "messages" in out:
        out["messages"] = scrubber.scrub_messages(out["messages"])
    if "tools" in out:
        out["tools"] = scrubber.scrub_any(out["tools"])
    return out


def _create_chat(inner: Any, scrubber: Scrubber, kwargs: dict[str, Any]) -> Any:
    stream = bool(kwargs.get("stream"))
    result = inner.create(**_scrub_chat_kwargs(scrubber, kwargs))
    if stream:
        return StreamAdapter(result, scrubber.stream_restorer())
    return scrubber.restore_any(result)


async def _acreate_chat(inner: Any, scrubber: Scrubber, kwargs: dict[str, Any]) -> Any:
    create = inner.create
    stream = bool(kwargs.get("stream"))
    result = await create(**_scrub_chat_kwargs(scrubber, kwargs))
    if stream:
        return AsyncStreamAdapter(result, scrubber.stream_restorer())
    return scrubber.restore_any(result)


def _scrub_responses_kwargs(scrubber: Scrubber, kwargs: dict[str, Any]) -> dict[str, Any]:
    out = dict(kwargs)
    for key in ("input", "instructions", "tools"):
        if key in out:
            out[key] = scrubber.scrub_any(out[key])
    return out


def _create_responses(inner: Any, scrubber: Scrubber, kwargs: dict[str, Any]) -> Any:
    stream = bool(kwargs.get("stream"))
    result = inner.create(**_scrub_responses_kwargs(scrubber, kwargs))
    if stream:
        return StreamAdapter(result, scrubber.stream_restorer())
    return scrubber.restore_any(result)
