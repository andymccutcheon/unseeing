"""unseeing — let the model work on the text without ever seeing the people in it."""

from unseeing._version import __version__
from unseeing.asgi import UnseeingMiddleware
from unseeing.audit import AuditReport
from unseeing.errors import DetectorError, RestoreError, UnseeingError, VaultError
from unseeing.protocol import ScrubberProtocol
from unseeing.restore import StreamRestorer
from unseeing.scrubber import Scrubber, scrub
from unseeing.types import CustomPattern, DenyItem, Detection, EntityType
from unseeing.vault import Vault

__all__ = [
    "AuditReport",
    "CustomPattern",
    "DenyItem",
    "Detection",
    "DetectorError",
    "EntityType",
    "RestoreError",
    "Scrubber",
    "ScrubberProtocol",
    "StreamRestorer",
    "UnseeingError",
    "UnseeingMiddleware",
    "Vault",
    "VaultError",
    "scrub",
    "__version__",
]
