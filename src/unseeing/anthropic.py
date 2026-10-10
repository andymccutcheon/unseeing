"""Anthropic SDK wrapper: Messages API, tool use, and streams."""

from __future__ import annotations

from typing import Any

from unseeing.restore import AsyncStreamAdapter, StreamAdapter
from unseeing.scrubber import Scrubber


class UnseeingAnthropic:
    """Drop-in wrapper around an Anthropic client."""

    def __init__(self, client: Any, *, scrubber: Scrubber | None = None, **kwargs: Any) -> None:
        self._client = client
        self.scrubber = scrubber or Scrubber(**kwargs)
        messages = getattr(client, "messages", None)
        if messages is not None:
            self.messages = _MessagesProxy(messages, self.scrubber)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class _MessagesProxy:
    def __init__(self, messages: Any, scrubber: Scrubber) -> None:
        self._inner = messages
        self.scrubber = scrubber

    def create(self, **kwargs: Any) -> Any:
        stream = bool(kwargs.get("stream"))
        result = self._inner.create(**_scrub_kwargs(self.scrubber, kwargs))
        if stream:
            return StreamAdapter(result, self.scrubber.stream_restorer())
        return self.scrubber.restore_any(result)

    async def acreate(self, **kwargs: Any) -> Any:  # pragma: no cover
        stream = bool(kwargs.get("stream"))
        result = await self._inner.create(**_scrub_kwargs(self.scrubber, kwargs))
        if stream:
            return AsyncStreamAdapter(result, self.scrubber.stream_restorer())
        return self.scrubber.restore_any(result)

    def stream(self, **kwargs: Any) -> Any:
        stream_fn = getattr(self._inner, "stream", None)
        if stream_fn is None:
            return self.create(**{**kwargs, "stream": True})
        result = stream_fn(**_scrub_kwargs(self.scrubber, kwargs))
        return StreamAdapter(result, self.scrubber.stream_restorer())


def wrap_anthropic(
    client: Any, *, scrubber: Scrubber | None = None, **kwargs: Any
) -> UnseeingAnthropic:
    return UnseeingAnthropic(client, scrubber=scrubber, **kwargs)


def _scrub_kwargs(scrubber: Scrubber, kwargs: dict[str, Any]) -> dict[str, Any]:
    out = dict(kwargs)
    if "messages" in out:
        out["messages"] = scrubber.scrub_messages(out["messages"])
    if "system" in out:
        out["system"] = scrubber.scrub_any(out["system"])
    if "tools" in out:
        out["tools"] = scrubber.scrub_any(out["tools"])
    return out
