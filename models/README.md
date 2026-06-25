# Local model directory

Place manually downloaded model weights here. The service must not download or initialize heavy models at Python import time.

Recommended OCR layout for CPU development:

```text
models/
  ocr/
    ppocrv6_medium_det/
      inference.json
      inference.pdiparams
      inference.yml
    ppocrv6_medium_rec/
      inference.json
      inference.pdiparams
      inference.yml
    pp_lcnet_x0_25_textline_ori/
      inference.json
      inference.pdiparams
      inference.yml
```


> 注意：PP-OCRv6 / PaddlePaddle 3.x 的 Hugging Face 推理模型通常使用新格式：`inference.json` + `inference.pdiparams` + `inference.yml`，不一定再提供旧版 `inference.pdmodel`。本项目的 OCR 本地目录接受该新格式。

Use `config/default.yaml` or another YAML file to point `models.ocr.det_model_dir`, `rec_model_dir`, and `cls_model_dir` to these folders. For PaddleOCR 3.x offline startup, also keep the matching `det_model_name`, `rec_model_name`, and `cls_model_name` values so PaddleOCR does not fall back to a default orientation model.


## Layout models

Recommended local layout for Phase 2 development:

```text
models/
  layout/
    pp_structure_v3/
      PP-StructureV3.yaml
      # plus any local PaddleX model folders referenced by the YAML
    paddleocr_vl/
      config.json
      model.safetensors / model shards
      tokenizer and processor files
```

PaddleOCR-VL should be downloaded explicitly before offline runs, for example:

```bash
huggingface-cli download PaddlePaddle/PaddleOCR-VL-1.6 --local-dir models/layout/paddleocr_vl
```

For this service, keep all application-side model settings in `config/default.yaml`. Prefer a local PaddleX pipeline YAML and point `models.layout.paddlex_config` to it from `config/default.yaml`. The YAML should reference `models/layout/paddleocr_vl` so PaddleX does not fetch the VLM at runtime. Keep `models.layout.allow_auto_download=false` in production/offline environments.
