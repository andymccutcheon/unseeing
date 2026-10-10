"""Optional spaCy NER backend (PERSON / ORG / LOCATION)."""

from __future__ import annotations

from unseeing.errors import DetectorError
from unseeing.types import Detection, EntityType

_LABEL_MAP = {
    "PERSON": EntityType.PERSON,
    "PER": EntityType.PERSON,
    "ORG": EntityType.ORGANIZATION,
    "ORGANIZATION": EntityType.ORGANIZATION,
    "GPE": EntityType.LOCATION,
    "LOC": EntityType.LOCATION,
    "LOCATION": EntityType.LOCATION,
    "FAC": EntityType.LOCATION,
}


class SpacyNERDetector:
    """Requires ``pip install unseeing[ner]`` and a spaCy model.

    Default model: ``en_core_web_sm``. Download it with
    ``python -m spacy download en_core_web_sm``.
    """

    name = "spacy"

    def __init__(self, model: str = "en_core_web_sm") -> None:
        try:
            import spacy
        except ImportError as exc:
            raise DetectorError(
                "NER extra is not installed. Run: pip install 'unseeing[ner]' "
                "&& python -m spacy download en_core_web_sm"
            ) from exc
        try:
            self.nlp = spacy.load(model)
        except OSError as exc:
            raise DetectorError(
                f"spaCy model {model!r} is not installed. Run: python -m spacy download {model}"
            ) from exc

    def detect(self, text: str) -> list[Detection]:
        found: list[Detection] = []
        doc = self.nlp(text)
        for ent in doc.ents:
            mapped = _LABEL_MAP.get(ent.label_)
            if mapped is None:
                continue
            value = ent.text.strip()
            if len(value) < 2:
                continue
            found.append(
                Detection(
                    mapped,
                    ent.start_char,
                    ent.end_char,
                    value,
                    source="spacy",
                    confidence=0.8,
                )
            )
        return found


def ner_available(model: str = "en_core_web_sm") -> bool:
    try:
        import spacy

        spacy.load(model)
    except Exception:
        return False
    return True
