"""Robust placeholder restoration, including streamed chunks."""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field

_BRACKET_OPEN = "<[("
_BRACKET_CLOSE = {">": "<", "]": "[", ")": "("}
_INCOMPLETE_INNER = re.compile(r"^[A-Za-z][A-Za-z0-9]*_?\d*$")


@dataclass(frozen=True)
class Mapping:
    """One vault token and the original value it stands for."""

    token: str  # PERSON_1
    original: str
    display: str  # <PERSON_1> or a surrogate


def _token_pattern(tokens: Sequence[str]) -> re.Pattern[str] | None:
    if not tokens:
        return None
    bodies = "|".join(re.escape(tok) for tok in sorted(set(tokens), key=len, reverse=True))
    return re.compile(
        rf"(?P<open>[<\(\[])?(?P<tok>{bodies})(?P<close>[>\)\]])?(?P<poss>'s|'s|')?",
        re.I,
    )


def restore_text(text: str, mappings: Sequence[Mapping]) -> str:
    """Replace placeholders / surrogates with originals.

    Tolerates case changes, ``<>`` / ``[]`` / ``()`` brackets, missing
    brackets, and possessives (``<PERSON_1>'s``).
    """
    if not mappings or not text:
        return text
    tokens = [item.token for item in mappings]
    by_token = {item.token.upper(): item.original for item in mappings}
    pattern = _token_pattern(tokens)
    if pattern is None:
        return text

    def repl_tag(match: re.Match[str]) -> str:
        original = by_token.get(match.group("tok").upper())
        if original is None:
            return match.group(0)
        return original + (match.group("poss") or "")

    out = pattern.sub(repl_tag, text)

    # Surrogate (or leftover display) strings, longest first.
    displays = sorted(
        {(item.display, item.original) for item in mappings if item.display},
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    for display, original in displays:
        if display.startswith("<") and display.endswith(">"):
            continue  # already handled via token pattern
        if not display or display == original:
            continue
        out = re.sub(rf"(?<!\w){re.escape(display)}(?!\w)", original, out, flags=re.I)
    return out


def _incomplete_bracket_prefix(suffix: str) -> bool:
    if not suffix or suffix[0] not in _BRACKET_OPEN:
        return False
    closer = {k: v for v, k in _BRACKET_CLOSE.items()}[suffix[0]]
    if closer in suffix[1:]:
        return False
    inner = suffix[1:]
    return inner == "" or bool(_INCOMPLETE_INNER.fullmatch(inner))


class StreamRestorer:
    """Restore placeholders that may be split across streamed chunks."""

    def __init__(self, mappings: Sequence[Mapping] | None = None) -> None:
        self.mappings: list[Mapping] = list(mappings or ())
        self._buf = ""
        self._needles = [item.display.lower() for item in self.mappings if item.display]
        self._needles.extend(item.token.lower() for item in self.mappings)
        self._max_hold = max((len(n) for n in self._needles), default=0) + 8

    def reset(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buf += chunk
        hold = self._hold_len(self._buf)
        if hold:
            emit, self._buf = self._buf[:-hold], self._buf[-hold:]
        else:
            emit, self._buf = self._buf, ""
        return restore_text(emit, self.mappings)

    def flush(self) -> str:
        out = restore_text(self._buf, self.mappings)
        self._buf = ""
        return out

    def feed_many(self, chunks: Iterable[str]) -> str:
        parts = [self.feed(chunk) for chunk in chunks]
        parts.append(self.flush())
        return "".join(parts)

    def _hold_len(self, text: str) -> int:
        if not text:
            return 0
        # Hold an unfinished <TYPE_N> / [TYPE_N] / (TYPE_N) suffix.
        last_open = max((text.rfind(ch) for ch in _BRACKET_OPEN), default=-1)
        if last_open >= 0 and _incomplete_bracket_prefix(text[last_open:]):
            return len(text) - last_open
        # Hold a suffix that is a proper prefix of a known token or display.
        limit = min(len(text), self._max_hold)
        lower = text.lower()
        for length in range(limit, 0, -1):
            suffix = lower[-length:]
            if any(needle.startswith(suffix) and needle != suffix for needle in self._needles):
                return length
        return 0


@dataclass
class StreamAdapter:
    """Wrap an SDK stream, restoring text on each chunk and flushing the tail."""

    inner: Iterator[object]
    restorer: StreamRestorer
    extract: object = None
    replace: object = None
    _done: bool = field(default=False, init=False, repr=False)

    def __iter__(self) -> Iterator[object]:
        extract = self.extract or default_extract_text
        replace = self.replace or default_replace_text
        last: object | None = None
        for chunk in self.inner:
            text = extract(chunk)
            if isinstance(text, str) and text:
                restored = self.restorer.feed(text)
                chunk = replace(_copy_chunk(chunk), restored)
            last = chunk
            yield chunk
        tail = self.restorer.flush()
        if tail and last is not None:
            yield replace(_copy_chunk(last), tail)

    def __next__(self) -> object:  # pragma: no cover - iteration used via __iter__
        return next(iter(self))


class AsyncStreamAdapter:
    def __init__(
        self,
        inner: object,
        restorer: StreamRestorer,
        extract: object = None,
        replace: object = None,
    ) -> None:
        self.inner = inner
        self.restorer = restorer
        self.extract = extract or default_extract_text
        self.replace = replace or default_replace_text

    def __aiter__(self) -> AsyncStreamAdapter:
        return self

    async def __anext__(self) -> object:
        if not hasattr(self, "_agen"):
            self._agen = self._iterate()
        try:
            return await self._agen.__anext__()
        except StopAsyncIteration:
            raise

    async def _iterate(self) -> object:
        last: object | None = None
        async for chunk in self.inner:  # type: ignore[misc]
            text = self.extract(chunk)  # type: ignore[operator]
            if isinstance(text, str) and text:
                restored = self.restorer.feed(text)
                chunk = self.replace(_copy_chunk(chunk), restored)  # type: ignore[operator]
            last = chunk
            yield chunk
        tail = self.restorer.flush()
        if tail and last is not None:
            yield self.replace(_copy_chunk(last), tail)  # type: ignore[operator]


def _copy_chunk(chunk: object) -> object:
    if isinstance(chunk, dict):
        return dict(chunk)
    try:
        import copy

        return copy.copy(chunk)
    except Exception:
        return chunk


def default_extract_text(chunk: object) -> str | None:
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, dict):
        return _extract_dict(chunk)
    for getter in (
        lambda c: c.choices[0].delta.content,  # type: ignore[index]
        lambda c: c.choices[0].text,  # type: ignore[index]
        lambda c: c.delta.text,
        lambda c: c.delta.content,
        lambda c: c.content,
        lambda c: c.text,
    ):
        try:
            value = getter(chunk)
        except Exception:
            continue
        if isinstance(value, str):
            return value
    return None


def default_replace_text(chunk: object, text: str) -> object:
    if isinstance(chunk, str):
        return text
    if isinstance(chunk, dict):
        return _replace_dict(chunk, text)
    for setter in (
        _set_openai_delta,
        _set_attr_chain("delta", "text"),
        _set_attr_chain("delta", "content"),
        _set_attr("content"),
        _set_attr("text"),
    ):
        if setter(chunk, text):
            return chunk
    return chunk


def _extract_dict(data: dict) -> str | None:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            delta = first.get("delta") or first.get("message") or {}
            if isinstance(delta, dict):
                content = delta.get("content") or delta.get("text")
                if isinstance(content, str):
                    return content
            text = first.get("text")
            if isinstance(text, str):
                return text
    for key in ("delta", "content", "text"):
        value = data.get(key)
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            inner = value.get("text") or value.get("content")
            if isinstance(inner, str):
                return inner
    return None


def _replace_dict(data: dict, text: str) -> dict:
    out = dict(data)
    choices = out.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        first = dict(choices[0])
        if isinstance(first.get("delta"), dict):
            delta = dict(first["delta"])
            if "content" in delta or not delta:
                delta["content"] = text
            elif "text" in delta:
                delta["text"] = text
            first["delta"] = delta
        elif "text" in first:
            first["text"] = text
        elif isinstance(first.get("message"), dict):
            message = dict(first["message"])
            message["content"] = text
            first["message"] = message
        out["choices"] = [first, *choices[1:]]
        return out
    if "delta" in out and isinstance(out["delta"], dict):
        delta = dict(out["delta"])
        if "text" in delta:
            delta["text"] = text
        else:
            delta["content"] = text
        out["delta"] = delta
        return out
    if "content" in out:
        out["content"] = text
    elif "text" in out:
        out["text"] = text
    return out


def _set_openai_delta(chunk: object, text: str) -> bool:
    try:
        chunk.choices[0].delta.content = text  # type: ignore[index, union-attr]
        return True
    except Exception:
        return False


def _set_attr(name: str):
    def setter(chunk: object, text: str) -> bool:
        if hasattr(chunk, name):
            try:
                setattr(chunk, name, text)
                return True
            except Exception:
                return False
        return False

    return setter


def _set_attr_chain(*names: str):
    def setter(chunk: object, text: str) -> bool:
        obj: object = chunk
        for name in names[:-1]:
            obj = getattr(obj, name, None)
            if obj is None:
                return False
        try:
            setattr(obj, names[-1], text)
            return True
        except Exception:
            return False

    return setter
