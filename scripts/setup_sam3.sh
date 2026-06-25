#!/usr/bin/env bash
# Install the SAM3 source tree in the same style as Edit-Banana.
# Usage: bash scripts/setup_sam3.sh
# Override examples:
#   SAM3_CLONE_URL="https://gitclone.com/github.com/facebookresearch/sam3.git" bash scripts/setup_sam3.sh
#   SAM3_SRC="/opt/sam3_src" MODELS_DIR="/models" bash scripts/setup_sam3.sh
#   NUMPY_SPEC="numpy>=2.1,<2.8" bash scripts/setup_sam3.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

SAM3_SRC="${SAM3_SRC:-$PROJECT_ROOT/sam3_src}"
MODELS_DIR="${MODELS_DIR:-$PROJECT_ROOT/models}"
SAM3_CLONE_URL="${SAM3_CLONE_URL:-https://github.com/facebookresearch/sam3.git}"
NUMPY_SPEC="${NUMPY_SPEC:-numpy>=2.1,<2.8}"
BPE_NAME="bpe_simple_vocab_16e6.txt.gz"

echo "[1/3] Cloning SAM3 source into $SAM3_SRC from $SAM3_CLONE_URL ..."
if [[ -d "$SAM3_SRC/.git" ]]; then
  echo "Existing SAM3 source found; skip clone. Delete $SAM3_SRC to refresh."
else
  rm -rf "$SAM3_SRC"
  git clone --depth 1 "$SAM3_CLONE_URL" "$SAM3_SRC"
fi

echo "[2/4] Aligning NumPy for OpenCV/SciPy/tifffile compatibility ..."
pip install --upgrade "$NUMPY_SPEC"

echo "[3/4] Installing SAM3 package in editable mode ..."
pip install -e "$SAM3_SRC"
pip install --upgrade "$NUMPY_SPEC"
pip check

echo "[4/4] Copying BPE vocab into $MODELS_DIR ..."
mkdir -p "$MODELS_DIR"
for BPE_SRC in "$SAM3_SRC/assets/$BPE_NAME" "$SAM3_SRC/sam3/assets/$BPE_NAME"; do
  if [[ -f "$BPE_SRC" ]]; then
    cp "$BPE_SRC" "$MODELS_DIR/"
    echo "Copied $BPE_NAME to $MODELS_DIR/$BPE_NAME"
    break
  fi
done

if [[ ! -f "$MODELS_DIR/$BPE_NAME" ]]; then
  echo "BPE vocab not found automatically; available .gz files:"
  find "$SAM3_SRC" -name "*.gz" 2>/dev/null || true
fi

echo "Done. Download sam3 checkpoint to models/sam3/ and set models.sam3 paths in config/default.yaml."
