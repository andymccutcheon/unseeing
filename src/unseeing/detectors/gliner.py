"""Optional local GLiNER PII backend (ONNX Runtime on CPU).

Default model: ``knowledgator/gliner-pii-small-v1.0`` (Apache-2.0). It is a
PII-focused small checkpoint with official ONNX graphs (FP16 ~330MB, QUINT8
~197MB). unseeing loads the QUINT8 ONNX file by default and runs
``onnxruntime`` on CPU.

The ``gliner`` library currently lists PyTorch as a required Python
dependency even when inference uses ONNX Runtime. The extra therefore
installs ``gliner`` + ``onnxruntime``; we do not load the PyTorch weights
and we do not download a spaCy model. Default ``pip install unseeing``
still has zero required dependencies.

Override the model with ``UNSEEING_GLINER_MODEL``, the ONNX filename with
``UNSEEING_GLINER_ONNX_FILE``, and the score cutoff with
``UNSEEING_GLINER_THRESHOLD``. Constructor arguments win over the env.
"""

from __future__ import annotations

import os
from typing import Any

from unseeing.errors import DetectorError
from unseeing.types import Detection, EntityType

DEFAULT_MODEL = "knowledgator/gliner-pii-small-v1.0"
DEFAULT_ONNX_FILE = "onnx/model_quint8.onnx"
DEFAULT_THRESHOLD = 0.55

# Labels the model was trained to recognize, mapped to unseeing types.
# Keep this list short: extra labels add FPs and latency.
_LABELS: tuple[tuple[str, str], ...] = (
    ("person", EntityType.PERSON.value),
    ("email address", EntityType.EMAIL.value),
    ("phone number", EntityType.PHONE.value),
    ("credit card", EntityType.CREDIT_CARD.value),
    ("ssn", EntityType.SSN.value),
    ("social security number", EntityType.SSN.value),
    ("national id number", EntityType.NATIONAL_ID.value),
    ("identity card number", EntityType.NATIONAL_ID.value),
    ("date of birth", EntityType.DATE_OF_BIRTH.value),
    ("location street", EntityType.STREET_ADDRESS.value),
    ("location address", EntityType.STREET_ADDRESS.value),
    ("location city", EntityType.LOCATION.value),
    ("ip address", EntityType.IP_ADDRESS.value),
    ("url", EntityType.URL.value),
    ("iban", EntityType.IBAN.value),
)

_LABEL_MAP = {label: entity for label, entity in _LABELS}
_PROMPT_LABELS = [label for label, _entity in _LABELS]

_MODEL_CACHE: dict[tuple[str, str], Any] = {}


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else default


def _threshold(raw: float | None) -> float:
    if raw is not None:
        return raw
    text = os.environ.get("UNSEEING_GLINER_THRESHOLD")
    if text:
        try:
            return float(text)
        except ValueError:
            pass
    return DEFAULT_THRESHOLD


def _load_model(model_id: str, onnx_file: str) -> Any:
    key = (model_id, onnx_file)
    cached = _MODEL_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        from gliner import GLiNER
    except ImportError as exc:
        raise DetectorError(
            "GLiNER extra is not installed. Run: pip install 'unseeing[gliner]'"
        ) from exc
    try:
        import onnxruntime  # noqa: F401
    except ImportError as exc:
        raise DetectorError(
            "onnxruntime is required for unseeing[gliner]. Run: pip install 'unseeing[gliner]'"
        ) from exc

    load_errors: list[str] = []
    model = None
    try:
        model = GLiNER.from_pretrained(
            model_id,
            runtime="onnxruntime",
            runtime_model_file=onnx_file,
            runtime_options={"providers": ["CPUExecutionProvider"]},
            allow_patterns=["*.json", "onnx/*", "tokenizer*", "special_tokens*"],
        )
    except TypeError as exc:
        load_errors.append(f"runtime=: {exc}")
        try:
            model = GLiNER.from_pretrained(
                model_id,
                load_onnx_model=True,
                onnx_model_file=onnx_file,
            )
        except Exception as inner:  # noqa: BLE001
            load_errors.append(f"load_onnx_model=: {inner}")
            model = None
    except Exception as exc:  # noqa: BLE001
        load_errors.append(str(exc))
        model = None

    if model is None:
        raise DetectorError(
            f"Could not load GLiNER ONNX model {model_id!r} "
            f"({onnx_file}). " + " | ".join(load_errors)
        )
    _MODEL_CACHE[key] = model
    return model


class GLiNERDetector:
    """Local GLiNER PII detector. Lazy-loads and caches the ONNX session."""

    name = "gliner"

    def __init__(
        self,
        model: str | None = None,
        *,
        onnx_file: str | None = None,
        threshold: float | None = None,
    ) -> None:
        self.model_id = model or _env("UNSEEING_GLINER_MODEL", DEFAULT_MODEL)
        self.onnx_file = onnx_file or _env("UNSEEING_GLINER_ONNX_FILE", DEFAULT_ONNX_FILE)
        self.threshold = _threshold(threshold)
        self._model: Any | None = None

    def _ensure_model(self) -> Any:
        if self._model is None:
            self._model = _load_model(self.model_id, self.onnx_file)
        return self._model

    def detect(self, text: str) -> list[Detection]:
        if not text or not text.strip():
            return []
        model = self._ensure_model()
        try:
            entities = model.predict_entities(text, _PROMPT_LABELS, threshold=self.threshold)
        except Exception as exc:  # noqa: BLE001
            raise DetectorError(f"GLiNER inference failed: {exc}") from exc

        found: list[Detection] = []
        for ent in entities or []:
            label = str(ent.get("label") or "").strip().casefold()
            mapped = _LABEL_MAP.get(label)
            if mapped is None:
                continue
            start = int(ent.get("start", -1))
            end = int(ent.get("end", -1))
            value = str(ent.get("text") or "")
            if start < 0 or end <= start or end > len(text):
                # Some exports omit offsets; recover from the surface form.
                value = value or ""
                if not value:
                    continue
                found_at = text.find(value)
                if found_at < 0:
                    continue
                start, end = found_at, found_at + len(value)
            if not value:
                value = text[start:end]
            score = float(ent.get("score") or 0.0)
            found.append(
                Detection(
                    mapped,
                    start,
                    end,
                    value,
                    source="gliner",
                    confidence=score,
                )
            )
        return found


def gliner_installed() -> bool:
    try:
        import gliner  # noqa: F401
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def gliner_available(model: str | None = None, onnx_file: str | None = None) -> bool:
    if not gliner_installed():
        return False
    try:
        model_id = model or _env("UNSEEING_GLINER_MODEL", DEFAULT_MODEL)
        onnx = onnx_file or _env("UNSEEING_GLINER_ONNX_FILE", DEFAULT_ONNX_FILE)
        _load_model(model_id, onnx)
    except Exception:
        return False
    return True
