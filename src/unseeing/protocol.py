"""Stable integration surface for freewhirr and other proxies.

A consumer should depend on these method names, not on concrete classes::

    scrub_messages / restore_message / restore_stream
    restore_async_stream / scrub_text / restore_text / audit
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any, Protocol, runtime_checkable

from unseeing.audit import AuditReport


@runtime_checkable
class ScrubberProtocol(Protocol):
    """Optional-dependency hook. freewhirr can type against this protocol."""

    def scrub_text(self, text: str) -> str: ...

    def restore_text(self, text: str) -> str: ...

    def scrub_messages(self, messages: list[Any]) -> list[Any]: ...

    def restore_message(self, message: Any) -> Any: ...

    def restore_stream(self, chunks: Iterator[Any]) -> Iterator[Any]: ...

    def restore_async_stream(self, chunks: AsyncIterator[Any]) -> AsyncIterator[Any]: ...

    def audit(self) -> AuditReport: ...
