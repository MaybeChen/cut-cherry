from __future__ import annotations

from enum import StrEnum

from image2pptx.core.errors import DeviceError


class DeviceMode(StrEnum):
    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"


def cuda_available() -> bool:
    """按需检测 CUDA；不在 import 阶段初始化 GPU。"""
    try:
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except ImportError:
        return False


def resolve_device(requested: str) -> str:
    mode = DeviceMode(requested)
    if mode == DeviceMode.CPU:
        return "cpu"
    if mode == DeviceMode.CUDA:
        if not cuda_available():
            raise DeviceError("runtime.device=cuda was requested, but CUDA is not available")
        return "cuda"
    return "cuda" if cuda_available() else "cpu"
