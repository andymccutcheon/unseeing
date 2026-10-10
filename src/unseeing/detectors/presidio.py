"""Optional Microsoft Presidio adapter, used only if Presidio is installed."""

from __future__ import annotations

from unseeing.errors import DetectorError
from unseeing.types import Detection, EntityType

_PRESIDIO_MAP = {
    "PERSON": EntityType.PERSON,
    "EMAIL_ADDRESS": EntityType.EMAIL,
    "PHONE_NUMBER": EntityType.PHONE,
    "CREDIT_CARD": EntityType.CREDIT_CARD,
    "US_SSN": EntityType.SSN,
    "US_ITIN": EntityType.NATIONAL_ID,
    "US_PASSPORT": EntityType.NATIONAL_ID,
    "US_DRIVER_LICENSE": EntityType.NATIONAL_ID,
    "UK_NHS": EntityType.NATIONAL_ID,
    "UK_NINO": EntityType.NATIONAL_ID,
    "IBAN_CODE": EntityType.IBAN,
    "IP_ADDRESS": EntityType.IP_ADDRESS,
    "URL": EntityType.URL,
    "LOCATION": EntityType.LOCATION,
    "NRP": EntityType.PERSON,
    "DATE_TIME": EntityType.DATE_OF_BIRTH,
    "ORGANIZATION": EntityType.ORGANIZATION,
}


class PresidioDetector:
    """Thin adapter around ``presidio_analyzer.AnalyzerEngine``."""

    name = "presidio"

    def __init__(self, language: str = "en") -> None:
        try:
            from presidio_analyzer import AnalyzerEngine
        except ImportError as exc:
            raise DetectorError(
                "Presidio is not installed. Run: pip install 'unseeing[presidio]'"
            ) from exc
        self.language = language
        self.analyzer = AnalyzerEngine()

    def detect(self, text: str) -> list[Detection]:
        results = self.analyzer.analyze(text=text, language=self.language)
        found: list[Detection] = []
        for result in results:
            mapped = _PRESIDIO_MAP.get(result.entity_type)
            entity: EntityType | str = mapped if mapped is not None else result.entity_type
            found.append(
                Detection(
                    entity,
                    result.start,
                    result.end,
                    text[result.start : result.end],
                    source="presidio",
                    confidence=float(result.score or 0.5),
                )
            )
        return found


def presidio_available() -> bool:
    try:
        import presidio_analyzer  # noqa: F401
    except ImportError:
        return False
    return True
