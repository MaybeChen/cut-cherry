from __future__ import annotations


class Image2PptxError(RuntimeError):
    """Base service error."""


class DeviceError(Image2PptxError):
    """Raised when configured inference device cannot be used."""


class ModelUnavailableWarning(Image2PptxError):
    """Legacy error type retained for callers that imported it."""


class InputValidationError(Image2PptxError):
    """Raised for unsupported or corrupt input files."""


class PipelineStageError(Image2PptxError):
    """Raised when a pipeline stage cannot complete successfully."""


def format_stage_failure(stage: str, warnings: list[dict] | None) -> str:
    """Build a concise, user-facing failure message from warning records."""
    if not warnings:
        return f"{stage} failed"
    parts: list[str] = []
    for warning in warnings[:3]:
        reason = str(warning.get("reason", "unknown"))
        detail = warning.get("message") or warning.get("path") or warning.get("missing_dirs")
        if detail:
            parts.append(f"{reason}: {detail}")
        else:
            parts.append(reason)
    if len(warnings) > 3:
        parts.append(f"... {len(warnings) - 3} more")
    return f"{stage} failed: " + "; ".join(parts)
