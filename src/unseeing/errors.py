"""Public exception hierarchy."""

from __future__ import annotations


class UnseeingError(Exception):
    """Base error for the unseeing package."""


class DetectorError(UnseeingError):
    """A detector backend is missing, misconfigured, or failed."""


class VaultError(UnseeingError):
    """Vault serialization, encryption, or lookup failed."""


class RestoreError(UnseeingError):
    """A restore operation failed."""
