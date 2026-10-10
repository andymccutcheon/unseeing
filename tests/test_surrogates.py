from __future__ import annotations

from unseeing import Scrubber


def test_surrogates_are_stable_and_reversible() -> None:
    scrubber = Scrubber(use_surrogates=True, resume=True)
    text = "Ava Chen <ava.chen@example.com>"
    first = scrubber.scrub(text)
    second = Scrubber(use_surrogates=True, resume=True).scrub(text)
    assert first == second
    assert "Ava Chen" not in first
    assert "ava.chen@example.com" not in first
    assert "<" not in first
    assert scrubber.restore(first) == text
