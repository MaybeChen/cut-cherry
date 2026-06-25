import yaml

from scripts.patch_pp_structure_config import patch_model_dirs


def test_patch_model_dirs_sets_local_paths_and_reports_missing(tmp_path):
    model_root = tmp_path / "models" / "layout" / "pp_structure_v3"
    (model_root / "PP-DocLayout_plus-L").mkdir(parents=True)
    config_path = model_root / "PP-StructureV3.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "SubModules": {
                    "LayoutDetection": {
                        "model_name": "PP-DocLayout_plus-L",
                        "model_dir": None,
                    },
                    "ChartRecognition": {
                        "model_name": "PP-Chart2Table",
                        "model_dir": None,
                    },
                }
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    patched, missing = patch_model_dirs(config_path, model_root)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    assert patched == 1
    assert missing == ["PP-Chart2Table"]
    assert (
        data["SubModules"]["LayoutDetection"]["model_dir"]
        == (model_root / "PP-DocLayout_plus-L").as_posix()
    )
