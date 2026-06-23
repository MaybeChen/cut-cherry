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

Use `config/default.yaml` or another YAML file to point `models.ocr.det_model_dir`, `rec_model_dir`, and `cls_model_dir` to these folders.
