#!/usr/bin/env bash
# Install the SAM3 source tree in the same style as Edit-Banana.
# Usage: bash scripts/setup_sam3.sh
# Override examples:
#   SAM3_CLONE_URL="https://gitclone.com/github.com/facebookresearch/sam3.git" bash scripts/setup_sam3.sh
#   SAM3_SRC="/opt/sam3_src" MODELS_DIR="/models" bash scripts/setup_sam3.sh
#   NUMPY_SPEC="numpy>=1.26,<2" bash scripts/setup_sam3.sh
#   SETUPTOOLS_SPEC="setuptools<81" bash scripts/setup_sam3.sh
#   TRITON_SPEC="triton-windows" bash scripts/setup_sam3.sh
#   PYCOCOTOOLS_SPEC="pycocotools" bash scripts/setup_sam3.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

SAM3_SRC="${SAM3_SRC:-$PROJECT_ROOT/sam3_src}"
SAM3_MODEL_DIR="${SAM3_MODEL_DIR:-$PROJECT_ROOT/models/sam3}"
SAM3_CLONE_URL="${SAM3_CLONE_URL:-https://github.com/facebookresearch/sam3.git}"
NUMPY_SPEC="${NUMPY_SPEC:-numpy>=1.26,<2}"
OPENCV_SPEC="${OPENCV_SPEC:-opencv-python<4.13}"
SCIPY_SPEC="${SCIPY_SPEC:-scipy<1.18}"
TIFFFILE_SPEC="${TIFFFILE_SPEC:-tifffile<2026}"
SETUPTOOLS_SPEC="${SETUPTOOLS_SPEC:-setuptools<81}"
PYCOCOTOOLS_SPEC="${PYCOCOTOOLS_SPEC:-pycocotools}"
if [[ -z "${TRITON_SPEC:-}" ]]; then
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) TRITON_SPEC="triton-windows" ;;
    *) TRITON_SPEC="triton" ;;
  esac
fi
BPE_NAME="bpe_simple_vocab_16e6.txt.gz"

echo "[1/5] Cloning SAM3 source into $SAM3_SRC from $SAM3_CLONE_URL ..."
if [[ -d "$SAM3_SRC/.git" ]]; then
  echo "Existing SAM3 source found; skip clone. Delete $SAM3_SRC to refresh."
else
  rm -rf "$SAM3_SRC"
  git clone --depth 1 "$SAM3_CLONE_URL" "$SAM3_SRC"
fi

echo "[2/5] Aligning NumPy/OpenCV/SciPy/tifffile compatibility ..."
pip install --upgrade "$SETUPTOOLS_SPEC" "$NUMPY_SPEC" "$OPENCV_SPEC" "$SCIPY_SPEC" "$TIFFFILE_SPEC"

echo "[3/5] Installing SAM3 package in editable mode ..."
pip install -e "$SAM3_SRC"
pip install --upgrade "$SETUPTOOLS_SPEC" "$NUMPY_SPEC" "$OPENCV_SPEC" "$SCIPY_SPEC" "$TIFFFILE_SPEC"

echo "[4/5] Installing SAM3 local runtime dependencies: $TRITON_SPEC, $PYCOCOTOOLS_SPEC ..."
pip install --upgrade "$TRITON_SPEC" "$PYCOCOTOOLS_SPEC"
pip check

echo "[5/5] Verifying existing SAM3 model assets in $SAM3_MODEL_DIR ..."
mkdir -p "$SAM3_MODEL_DIR"
if [[ -f "$SAM3_MODEL_DIR/$BPE_NAME" ]]; then
  echo "Found BPE vocab: $SAM3_MODEL_DIR/$BPE_NAME"
else
  echo "BPE vocab is not present at $SAM3_MODEL_DIR/$BPE_NAME"
  echo "Place your existing BPE there or update models.sam3.bpe_path in config/default.yaml."
fi
if [[ -f "$SAM3_MODEL_DIR/sam3.pt" ]]; then
  echo "Found checkpoint: $SAM3_MODEL_DIR/sam3.pt"
else
  echo "SAM3 checkpoint is not present at $SAM3_MODEL_DIR/sam3.pt"
  echo "Place your existing checkpoint there or update models.sam3.model_path in config/default.yaml."
fi

echo "Done. This script does not download or copy BPE/checkpoint files; it only verifies existing assets."
