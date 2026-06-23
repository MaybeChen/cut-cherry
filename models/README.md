# Local model directory

Place manually downloaded model weights here. The service must not download or initialize heavy models at Python import time.

Recommended OCR layout for CPU development:

```text
models/
  ocr/
    ppocrv5_server_det/
      inference.pdmodel
      inference.pdiparams
    ppocrv5_server_rec/
      inference.pdmodel
      inference.pdiparams
    ch_ppocr_mobile_v2.0_cls/
      inference.pdmodel
      inference.pdiparams
```

Use `config/default.yaml` or another YAML file to point `models.ocr.det_model_dir`, `rec_model_dir`, and `cls_model_dir` to these folders.
