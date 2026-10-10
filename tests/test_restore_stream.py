from __future__ import annotations

from unseeing import Scrubber, scrub


def test_chunk_split_placeholder() -> None:
    text = "Hello Ada Lovelace at ada@example.com"
    scrubbed, vault = scrub(text)
    assert "<EMAIL_1>" in scrubbed
    restorer = vault.stream_restorer()
    # Split inside the placeholder.
    idx = scrubbed.index("<EMAIL")
    left, right = scrubbed[: idx + 4], scrubbed[idx + 4 :]
    assert "<EMAIL_1>" not in left
    rebuilt = restorer.feed(left) + restorer.feed(right) + restorer.flush()
    assert rebuilt == text


def test_char_by_char_stream() -> None:
    text = "Call +1-555-010-0199 please"
    scrubbed, vault = scrub(text)
    restorer = vault.stream_restorer()
    out = "".join(restorer.feed(ch) for ch in scrubbed) + restorer.flush()
    assert out == text


def test_possessive_and_brackets() -> None:
    scrubber = Scrubber(resume=True)
    scrubber.scrub("Ava Chen\nava@example.com\n")
    assert scrubber.restore("<PERSON_1>'s portfolio") == "Ava Chen's portfolio"
    assert scrubber.restore("[PERSON_1] and (EMAIL_1)") == "Ava Chen and ava@example.com"
    assert scrubber.restore("<person_1>") == "Ava Chen"


def test_surrogate_stream_restore() -> None:
    scrubber = Scrubber(use_surrogates=True)
    original = "Write to ada@example.com today"
    scrubbed = scrubber.scrub(original)
    assert "ada@example.com" not in scrubbed
    assert "@example." in scrubbed  # fake domain
    restorer = scrubber.stream_restorer()
    mid = max(1, len(scrubbed) // 2)
    out = restorer.feed(scrubbed[:mid]) + restorer.feed(scrubbed[mid:]) + restorer.flush()
    assert out == original


def test_restore_stream_wrapper() -> None:
    text = "Hi ada@example.com"
    scrubbed, vault = scrub(text)
    chunks = [
        {"choices": [{"delta": {"content": scrubbed[:6]}}]},
        {"choices": [{"delta": {"content": scrubbed[6:]}}]},
    ]
    scrubber = __import__("unseeing", fromlist=["Scrubber"]).Scrubber(vault=vault)
    pieces = []
    for chunk in scrubber.restore_stream(iter(chunks)):
        pieces.append(chunk["choices"][0]["delta"]["content"])
    assert "".join(pieces) == text
