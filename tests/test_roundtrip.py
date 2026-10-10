from __future__ import annotations

from hypothesis import given, settings, strategies as st

from unseeing import scrub

# Avoid unpaired surrogates; placeholders in the *input* are reserved, so
# restore(scrub(s)) should still be identity.
SAFE = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), min_codepoint=32),
    max_size=300,
)


@given(SAFE)
@settings(max_examples=80)
def test_restore_scrub_is_identity(text: str) -> None:
    scrubbed, vault = scrub(text, resume=True)
    assert vault.restore(scrubbed) == text


@given(SAFE, st.integers(min_value=1, max_value=17))
@settings(max_examples=40)
def test_stream_matches_bulk_restore(text: str, n: int) -> None:
    scrubbed, vault = scrub(text)
    restorer = vault.stream_restorer()
    if not scrubbed:
        assert restorer.flush() == ""
        return
    size = max(1, len(scrubbed) // n)
    chunks = [scrubbed[i : i + size] for i in range(0, len(scrubbed), size)]
    streamed = "".join(restorer.feed(chunk) for chunk in chunks) + restorer.flush()
    assert streamed == vault.restore(scrubbed) == text
