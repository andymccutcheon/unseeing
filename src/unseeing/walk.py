"""Walk chat / Responses / tool-call structures and map every string."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

SKIP_KEYS = frozenset(
    {
        "role",
        "model",
        "id",
        "type",
        "object",
        "finish_reason",
        "index",
        "created",
        "system_fingerprint",
        "event",
        "tool_call_id",
        "call_id",
        "status",
    }
)


def map_strings(obj: T, fn: Callable[[str], str], *, skip_keys: frozenset[str] = SKIP_KEYS) -> T:
    """Recursively apply ``fn`` to strings in dicts, lists, and simple objects."""
    if isinstance(obj, str):
        return fn(obj)  # type: ignore[return-value]
    if isinstance(obj, list):
        return [map_strings(item, fn, skip_keys=skip_keys) for item in obj]  # type: ignore[return-value]
    if isinstance(obj, tuple):
        return tuple(map_strings(item, fn, skip_keys=skip_keys) for item in obj)  # type: ignore[return-value]
    if isinstance(obj, dict):
        return {
            key: value if key in skip_keys else map_strings(value, fn, skip_keys=skip_keys)
            for key, value in obj.items()
        }  # type: ignore[return-value]
    dump = getattr(obj, "model_dump", None)
    copy = getattr(obj, "model_copy", None)
    if callable(dump) and callable(copy):
        mapped = map_strings(dump(), fn, skip_keys=skip_keys)
        try:
            return copy(update=mapped)
        except Exception:
            return mapped  # type: ignore[return-value]
    return obj
