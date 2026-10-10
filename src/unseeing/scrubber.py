"""Main scrubber: detect, replace, restore, audit."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from unseeing.audit import AuditReport
from unseeing.detectors.base import Detector, resolve_overlaps
from unseeing.detectors.custom import CustomDetector, deny_detections
from unseeing.detectors.regex import RegexLayer
from unseeing.resume import detect_resume, person_aliases
from unseeing.restore import AsyncStreamAdapter, StreamAdapter, StreamRestorer
from unseeing.types import CustomPattern, DenyItem, Detection, EntityType
from unseeing.vault import Vault
from unseeing.walk import map_strings


class Scrubber:
    """Layered, pluggable PII scrubber with a reversible session vault.

    Implements :class:`unseeing.protocol.ScrubberProtocol` so freewhirr can
    take an optional ``unseeing`` extra and call ``scrub_messages`` /
    ``restore_message`` / ``restore_stream``.
    """

    def __init__(
        self,
        *,
        vault: Vault | None = None,
        allow: Sequence[str] = (),
        deny: Sequence[str | DenyItem] = (),
        custom_patterns: Sequence[CustomPattern] = (),
        resume: bool = False,
        scrub_orgs: bool = False,
        use_surrogates: bool = False,
        scrub_urls: bool = True,
        use_ner: bool = False,
        ner_model: str = "en_core_web_sm",
        use_presidio: bool = False,
        detectors: Sequence[Detector] | None = None,
    ) -> None:
        self.vault = vault or Vault(use_surrogates=use_surrogates)
        if use_surrogates:
            self.vault.use_surrogates = True
        self.allow = tuple(allow)
        self.deny = tuple(deny)
        self.custom_patterns = tuple(custom_patterns)
        self.resume = resume
        self.scrub_orgs = scrub_orgs
        self.scrub_urls = scrub_urls
        self._last_sources: dict[str, int] = {}

        if detectors is not None:
            self.detectors = list(detectors)
        else:
            self.detectors = [RegexLayer(scrub_urls=scrub_urls)]
            if custom_patterns:
                self.detectors.append(CustomDetector(custom_patterns))
            if use_ner:
                from unseeing.detectors.ner import SpacyNERDetector

                self.detectors.append(SpacyNERDetector(model=ner_model))
            if use_presidio:
                from unseeing.detectors.presidio import PresidioDetector

                self.detectors.append(PresidioDetector())

    def detect(self, text: str) -> list[Detection]:
        found: list[Detection] = []
        for detector in self.detectors:
            found.extend(detector.detect(text))
        if self.resume:
            found.extend(detect_resume(text, scrub_orgs=self.scrub_orgs))
        found.extend(deny_detections(text, self.deny))
        found = [item for item in found if not self._is_allowed(item.value)]
        return resolve_overlaps(found)

    def scrub(self, text: str) -> str:
        return self.scrub_text(text)

    def restore(self, text: str) -> str:
        return self.restore_text(text)

    def scrub_text(self, text: str) -> str:
        if not text:
            return text
        self.vault.reserve_from(text)
        detections = self.detect(text)
        self._record_sources(detections)
        out = text
        for item in sorted(detections, key=lambda d: d.start, reverse=True):
            replacement = self.vault.register(item.type_name, item.value)
            out = out[: item.start] + replacement + out[item.end :]
        if self.resume:
            self._alias_people(detections)
        return out

    def restore_text(self, text: str) -> str:
        return self.vault.restore(text)

    def scrub_messages(self, messages: list[Any]) -> list[Any]:
        return map_strings(messages, self.scrub_text)

    def restore_message(self, message: Any) -> Any:
        if isinstance(message, str):
            return self.restore_text(message)
        return map_strings(message, self.restore_text)

    def restore_stream(self, chunks: Iterator[Any]) -> Iterator[Any]:
        return StreamAdapter(chunks, self.vault.stream_restorer())

    def restore_async_stream(self, chunks: AsyncIterator[Any]) -> AsyncIterator[Any]:
        return AsyncStreamAdapter(chunks, self.vault.stream_restorer())

    def stream_restorer(self) -> StreamRestorer:
        return self.vault.stream_restorer()

    def audit(self) -> AuditReport:
        report = self.vault.audit()
        report.sources = dict(self._last_sources)
        return report

    def scrub_any(self, obj: Any) -> Any:
        return map_strings(obj, self.scrub_text)

    def restore_any(self, obj: Any) -> Any:
        return map_strings(obj, self.restore_text)

    def _is_allowed(self, value: str) -> bool:
        folded = value.casefold()
        for allowed in self.allow:
            if len(allowed) < 2:
                continue
            af = allowed.casefold()
            if af == folded or af in folded or folded in af:
                return True
        return False

    def _alias_people(self, detections: Sequence[Detection]) -> None:
        for item in detections:
            if item.type_name != EntityType.PERSON.value:
                continue
            for alias in person_aliases(item.value):
                if self._is_allowed(alias):
                    continue
                self.vault.alias(EntityType.PERSON.value, alias, item.value)

    def _record_sources(self, detections: Sequence[Detection]) -> None:
        sources: dict[str, int] = {}
        for item in detections:
            sources[item.source] = sources.get(item.source, 0) + 1
        self._last_sources = sources


def scrub(
    text: str,
    *,
    vault: Vault | None = None,
    **kwargs: Any,
) -> tuple[str, Vault]:
    """One-shot helper: ``scrubbed, vault = scrub(text)``."""
    scrubber = Scrubber(vault=vault, **kwargs)
    return scrubber.scrub(text), scrubber.vault
