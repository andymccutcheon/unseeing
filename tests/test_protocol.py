from __future__ import annotations

from unseeing import Scrubber, ScrubberProtocol


def test_scrubber_satisfies_protocol() -> None:
    scrubber = Scrubber()
    assert isinstance(scrubber, ScrubberProtocol)
    messages = [{"role": "user", "content": "ada@example.com"}]
    out = scrubber.scrub_messages(messages)
    assert "ada@example.com" not in out[0]["content"]
    restored = scrubber.restore_message(out[0])
    assert restored["content"] == "ada@example.com"
    chunks = list(scrubber.restore_stream(iter(["<EMAIL_1>"])))
    assert "".join(chunks) == "ada@example.com"
