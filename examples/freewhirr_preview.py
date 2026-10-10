"""How freewhirr can take unseeing as an optional dependency.

freewhirr would type against ``unseeing.ScrubberProtocol`` and, if the extra
is installed, wrap its OpenAI-compatible proxy::

    pip install freewhirr unseeing
"""

from unseeing import Scrubber, ScrubberProtocol, UnseeingMiddleware


def attach_to_proxy(app, scrubber: ScrubberProtocol | None = None):
    """Preview of a freewhirr integration point."""
    hook = scrubber or Scrubber(resume=True)
    return UnseeingMiddleware(app, scrubber=hook)  # type: ignore[arg-type]


async def _dummy_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok", "more_body": False})


app = attach_to_proxy(_dummy_app)
print("ASGI app wrapped with", type(app).__name__)
print(
    "Protocol methods: scrub_messages, restore_message, restore_stream, "
    "restore_async_stream, scrub_text, restore_text, audit"
)
