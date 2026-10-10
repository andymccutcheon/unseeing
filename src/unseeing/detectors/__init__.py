"""Pluggable detectors."""

from unseeing.detectors.base import Detector, resolve_overlaps
from unseeing.detectors.custom import CustomDetector
from unseeing.detectors.regex import RegexLayer

__all__ = ["CustomDetector", "Detector", "RegexLayer", "resolve_overlaps"]
