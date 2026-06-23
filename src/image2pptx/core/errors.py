from __future__ import annotations


class Image2PptxError(RuntimeError):
    """Base service error."""


class DeviceError(Image2PptxError):
    """Raised when configured inference device cannot be used."""


class ModelUnavailableWarning(Image2PptxError):
    """Raised internally when an optional model is unavailable and a fallback is used."""


class InputValidationError(Image2PptxError):
    """Raised for unsupported or corrupt input files."""
