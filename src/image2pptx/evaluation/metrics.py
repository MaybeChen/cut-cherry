from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

def compute_basic_metrics(a: Path, b: Path) -> dict[str, float]:
    ia=cv2.imread(str(a), cv2.IMREAD_GRAYSCALE); ib=cv2.imread(str(b), cv2.IMREAD_GRAYSCALE)
    if ia is None or ib is None: raise ValueError("cannot read comparison images")
    ib=cv2.resize(ib, (ia.shape[1], ia.shape[0]))
    diff=np.abs(ia.astype(float)-ib.astype(float))
    return {"visual_score": float(ssim(ia, ib)), "mae": float(diff.mean()), "mse": float((diff**2).mean()), "patch_area_ratio": 0.0}
