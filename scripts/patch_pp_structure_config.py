from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path("models/layout/pp_structure_v3/PP-StructureV3.yaml")
DEFAULT_MODEL_ROOT = Path("models/layout/pp_structure_v3")


def patch_model_dirs(config_path: Path, model_root: Path) -> tuple[int, list[str]]:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    patched, missing = _patch_node(data, model_root)
    config_path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return patched, missing


def _patch_node(node: Any, model_root: Path) -> tuple[int, list[str]]:
    patched = 0
    missing: list[str] = []
    if isinstance(node, dict):
        model_name = node.get("model_name")
        if model_name and "model_dir" in node and not node.get("model_dir"):
            candidate = model_root / str(model_name)
            if candidate.exists():
                node["model_dir"] = candidate.as_posix()
                patched += 1
            else:
                missing.append(str(model_name))
        for value in node.values():
            child_patched, child_missing = _patch_node(value, model_root)
            patched += child_patched
            missing.extend(child_missing)
    elif isinstance(node, list):
        for item in node:
            child_patched, child_missing = _patch_node(item, model_root)
            patched += child_patched
            missing.extend(child_missing)
    return patched, sorted(set(missing))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Patch PP-StructureV3 PaddleX YAML model_dir fields to local folders."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--model-root", type=Path, default=DEFAULT_MODEL_ROOT)
    args = parser.parse_args()

    patched, missing = patch_model_dirs(args.config, args.model_root)
    print(f"Patched {patched} model_dir field(s) in {args.config}")
    if missing:
        print("Missing local model folder(s):")
        for model_name in missing:
            print(f"  {args.model_root / model_name}")


if __name__ == "__main__":
    main()
