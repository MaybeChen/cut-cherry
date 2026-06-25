# image2pptx-service

无 YOLO 的 Image/PDF 页面到可编辑 PPTX 服务。当前提交完成 **Phase 1 可运行基础链路**：图片输入、预处理、可选 OCR 降级、OpenCV 矩形/线条候选、SlideIR、python-pptx 输出、CLI 与 FastAPI。Phase 2-5 已保留清晰接口与 TODO。

## 目录树

```text
config/                 YAML 配置
scripts/                API/CLI/渲染/模型下载脚本
src/image2pptx/         服务源码：api、cli、config、models、ir、pipeline、processors、renderers、evaluation、storage
tests/                  单元与集成测试
outputs/                运行产物目录
```

## Poetry 依赖说明

基础依赖安装 FastAPI、Typer、OpenCV、Pillow、python-pptx、Pydantic Settings、scikit-image 等，能在纯 CPU 环境运行 Phase 1。重模型放在 optional groups：

- `ocr`: `paddleocr`, `paddlepaddle`
- `gpu`: `paddlepaddle-gpu`, `onnxruntime-gpu`
- `segmentation`: `torch`, `torchvision`, `segment-anything`
- `vlm`: `transformers`, `accelerate`
- `background-removal`: `onnxruntime`

## 安装与运行

> 建议在仓库根目录创建 `input/` 目录存放本地待转换文件，例如 `input/input.png`。该目录已加入 `.gitignore`，不会误提交真实业务图片。

### Linux / macOS / Windows CPU

```bash
poetry install
poetry run image2pptx convert input/input.png --device cpu
```

### Windows CPU + OCR / PP-StructureV3

```powershell
poetry install --with ocr
# 如果你已经有旧环境且仍报 paddlex extra 缺失，可补装：
poetry run pip install "paddlex[ocr]"
poetry run image2pptx convert input/input.png --device cpu
```

### Linux CUDA

GPU wheel 与 CUDA 版本强相关；建议先按 Paddle/PyTorch 官方说明安装匹配 wheel，再安装本项目可选组：

```bash
poetry install --with ocr,segmentation
# 如环境可解析 GPU wheel：
poetry install --with gpu
poetry run image2pptx convert input/input.png --device cuda
```

### Windows CUDA

先安装匹配本机 CUDA 的 PaddlePaddle/PyTorch GPU wheel；如果 `--with gpu` 无法解析对应 wheel，请不要强行依赖 Poetry 一键安装：

```powershell
poetry install --with ocr,segmentation
poetry run image2pptx convert input/input.png --device cuda
```


## 本地模型目录与 OCR 版本建议

本项目约定在仓库根目录使用 `models/` 存放手动下载的模型权重，目录本身会提交，占位和说明文件会保留；真实权重文件已被 `.gitignore` 忽略。

CPU 首轮建议使用 PaddleOCR 的 PP-OCRv6 medium 系列，优先保证 PPT 截图、中文、英文、数字和常见 UI 文本的识别质量：

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

推荐模型：

- 检测：`PP-OCRv6_medium_det`
- 识别：`PP-OCRv6_medium_rec`
- 方向分类：`PP-LCNet_x0_25_textline_ori`


> 注意：PP-OCRv6 / PaddlePaddle 3.x 的 Hugging Face 推理模型通常使用新格式：`inference.json` + `inference.pdiparams` + `inference.yml`，不一定再提供旧版 `inference.pdmodel`。本项目的 OCR 本地目录接受该新格式。

默认配置已指向上述本地路径，并设置 `models.ocr.allow_auto_download=false`，因此缺少模型时会明确降级为空 OCR 结果，不会在代码导入或转换时偷偷下载。

初始化目录：

```bash
poetry run python scripts/download_models.py
```

该脚本只创建目录并打印下载计划，不会联网下载权重。

## 配置

默认配置在 `config/default.yaml`。运行时覆盖示例：

```bash
poetry run image2pptx convert input/input.png --device cpu
poetry run image2pptx convert input/input.png --device cuda
poetry run image2pptx convert input/input.png --config config/cpu.yaml
```

`auto` 会按需检测 CUDA；`cpu` 强制 CPU；`cuda` 在 CUDA 不可用时给出明确错误。所有重模型均不得在 import 阶段下载或加载。

## 模型配置与下载

```bash
poetry run python scripts/download_models.py
```

当前脚本只创建 `models/` 并提示手动放置权重。PaddleOCR、SAM3、RMBG、VLM 均为可选能力：缺失时记录/执行降级路径，不阻断基础 PPTX 生成。

## CLI 示例

```bash
poetry run image2pptx convert input/input.png
poetry run image2pptx convert input/input.png --device cpu --no-sam3 --no-vlm --no-refine
poetry run image2pptx inspect input/input.png
poetry run image2pptx evaluate source.png preview.png
```

## API 示例

```bash
poetry run image2pptx-api
curl http://localhost:8000/health
curl -F "file=@input.png" http://localhost:8000/jobs
curl http://localhost:8000/jobs/{job_id}/artifacts
curl -OJ http://localhost:8000/jobs/{job_id}/download/pptx
```

## 当前已实现能力

- 图片 EXIF 修复、RGB/RGBA 规范化、灰度/边缘/LAB/HSV/preview 中间产物。
- PaddleOCR 可选文本识别；未安装时不伪造文本，继续 OpenCV/SlideIR/PPTX 链路。
- OpenCV 轮廓矩形与 Hough 线段候选。
- SlideIR 元素、关系、z-index 排序、重叠检测、JSON 导入导出。
- 原生 PPTX 背景、形状、文本框、connector 渲染。
- CLI、FastAPI、CPU 集成测试、PPTX 可打开校验。

## Phase 2-5 待实现

- Phase 2：PaddleOCR-VL/PP-Structure、表格结构、图片/Logo 资产、RMBG。
- Phase 3：SAM3 mask、Alpha PNG、箭头头部识别、connector 端点吸附。
- Phase 4：LibreOffice 预览、SSIM/边缘差异闭环、局部修复、残差透明 patch。
- Phase 5：OMML 公式、原生图表、VLM 仲裁、字体搜索、复杂 OOXML。

## 可选模型降级行为

- PaddleOCR 不可用：文本候选为空，不用假文本；仍输出形状/线条 PPTX。
- PaddleOCR-VL 不可用：Phase 1 使用 OCR + OpenCV 布局规则接口占位。
- SAM3 不可用或禁用：不做 mask 分割；Phase 2/3 将回退 RMBG 或矩形裁剪。
- RMBG 不可用或禁用：资产保留矩形裁图。
- VLM 默认关闭：不让 VLM 生成坐标，仅未来用于候选仲裁。
- CUDA 不可用且请求 `cuda`：直接明确报错；`auto` 自动回退 CPU。

## 示例输出

运行 `poetry run image2pptx convert tests/fixtures/example.png --device cpu` 后输出：

```text
outputs/{job_id}/source.png
outputs/{job_id}/normalized.png
outputs/{job_id}/gray.png
outputs/{job_id}/edges.png
outputs/{job_id}/lab.png
outputs/{job_id}/hsv.png
outputs/{job_id}/preview.png
outputs/{job_id}/slide_ir.json
outputs/{job_id}/ocr_results.json
outputs/{job_id}/result.pptx
```

## PaddleOCR-VL / PP-StructureV3 接入

PP-StructureV3 依赖 PaddleX 的 OCR extras。如果导出或启动时报 `PP-StructureV3 requires additional dependencies`，请先运行：

```bash
poetry install --with ocr
# 或在已有虚拟环境中补装
poetry run pip install "paddlex[ocr]"
```


Layout 阶段现在会优先尝试 `models.layout.engine` 指定的结构化模型，并在模型不可用、缺少本地配置或推理失败时自动回退到规则版 OCR + OpenCV layout。默认配置使用 `pp_structure_v3`，且 `allow_auto_download=false`，因此不会偷偷下载模型。

所有应用侧 layout 配置都定义在 `config/default.yaml` 的 `models.layout` 下；不需要额外新建 `config/layout_paddleocr_vl_local.yaml`。需要切换 PP-StructureV3 或 PaddleOCR-VL 时，直接修改 `config/default.yaml` 中的 `models.layout.engine`、`paddlex_config`、`allow_auto_download` 等字段即可。

CPU/离线建议先准备 PP-StructureV3 的 PaddleX 配置或本地模型目录，然后在 `config/default.yaml` 中设置：

```yaml
models:
  layout:
    engine: pp_structure_v3
    allow_auto_download: false
    paddlex_config: models/layout/pp_structure_v3/PP-StructureV3.yaml
    layout_model_dir: models/layout/pp_structure_v3
```

`PP-StructureV3.yaml` 不是手写给本项目解析的 YAML，而是 PaddleOCR/PaddleX 的 pipeline 配置文件。注意：直接执行 `PPStructureV3()` 会创建完整 pipeline，PaddleX 会按默认配置准备 LayoutDetection、OCR、Table、Formula、Chart 等子模块，因此可能联网下载很多默认模型。这个导出命令只适合在“联网引导机器”上执行一次：

```bash
# ONLINE BOOTSTRAP ONLY: may download PP-StructureV3 default sub-models
poetry run python -c "from paddleocr import PPStructureV3; PPStructureV3().export_paddlex_config_to_yaml('models/layout/pp_structure_v3/PP-StructureV3.yaml')"
```

离线/生产环境不要直接运行上面的命令；应从联网机器或制品库复制已经导出的 `PP-StructureV3.yaml`，再把其中的 `model_dir` 字段改成本地模型路径。这个 YAML 通常包含 `SubModules.LayoutDetection`、`SubPipelines.GeneralOCR`、`TextDetection`、`TextRecognition` 等模块配置；官方文档示例中也说明了可以把这些模块下的 `model_dir: null` 替换成你自己的本地模型目录。


你当前下载的 PP-StructureV3 模型目录如果和 `model_name` 同名，例如 `PP-DocLayout_plus-L/`、`PP-OCRv5_server_det/`、`SLANet_plus/`，可以用脚本自动把 YAML 里的 `model_dir: null` 补成本地路径：

```bash
poetry run python scripts/patch_pp_structure_config.py \
  --config models/layout/pp_structure_v3/PP-StructureV3.yaml \
  --model-root models/layout/pp_structure_v3
```

脚本会按每个节点的 `model_name` 查找同名目录，例如 `model_name: PP-DocLayout_plus-L` 会填成 `models/layout/pp_structure_v3/PP-DocLayout_plus-L`。如果某个目录缺失，会打印 missing 列表。

如需快速验证官方默认模型，可临时在 `config/default.yaml` 中显式允许 PaddleOCR/PaddleX 自行下载：

```yaml
models:
  layout:
    engine: pp_structure_v3
    allow_auto_download: true
```

PaddleOCR-VL 建议也下载到本地。推荐先用 Hugging Face CLI 或内部制品库把模型放到 `models/layout/paddleocr_vl/`：

```bash
huggingface-cli download PaddlePaddle/PaddleOCR-VL-1.6 --local-dir models/layout/paddleocr_vl
```

然后准备本地 PaddleX pipeline YAML，例如 `models/layout/paddleocr_vl/PaddleOCR-VL.yaml`，让 YAML 中的 VLM 路径指向 `models/layout/paddleocr_vl/`。本项目仍然只改 `config/default.yaml`：

```yaml
models:
  layout:
    engine: paddleocr_vl
    allow_auto_download: false
    paddlex_config: models/layout/paddleocr_vl/PaddleOCR-VL.yaml
    pipeline_name: PaddleOCR-VL
    paddleocr_vl_model_dir: models/layout/paddleocr_vl
```

如果只是联网快速验证 PaddleX 默认 pipeline，可以临时在 `config/default.yaml` 中显式允许下载：

```yaml
models:
  layout:
    engine: paddleocr_vl
    allow_auto_download: true
    pipeline_name: PaddleOCR-VL
```

转换完成后会额外输出：

```text
outputs/{job_id}/layout_results.json
```

该文件会记录 layout engine、模型识别数量、最终 layout regions、warnings 与 fallback 状态。

## PaddleOCR 版本兼容说明

PaddleOCR 3.x 的 Python API 已不再接受旧版 `use_gpu` 参数，设备选择使用 `device="cpu"` 或 `device="gpu"`；PaddleOCR 2.x 仍使用 `use_gpu=True/False`。本工程的 `TextProcessor` 会优先按 3.x API 初始化 `PaddleOCR`，如果当前环境安装的是 2.x 且出现 `Unknown argument`，会自动回退到 2.x 参数形态，不再因为 `ValueError: Unknown argument: use_gpu` 中断转换。

PP-OCRv6 推荐搭配 PaddleOCR 3.x 使用；如需使用 PaddleOCR 2.x，请改用兼容 2.x 的 PP-OCR 模型目录或确认本地模型格式可被旧版加载。

CLI 转换完成后会打印 OCR 状态、识别条数、`ocr_results.json` 路径，并在识别成功时输出前 100 条识别文本、置信度和 bbox。

PaddleOCR 3.x 离线本地模型建议同时配置模型名与模型目录，例如 `det_model_name: PP-OCRv6_medium_det` 搭配 `det_model_dir: models/ocr/ppocrv6_medium_det`。当显式配置本地模型名或目录时，本工程不会向 PaddleOCR 3.x 继续传入 `lang`，以避免启动时出现 `lang and ocr_version will be ignored` 警告；方向分类模型名也固定为 `PP-LCNet_x0_25_textline_ori`，避免默认创建 `PP-LCNet_x1_0_textline_ori`。


如果 CLI 输出 `local_ocr_model_mismatch`，例如 detection 目录期望 `PP-OCRv6_medium_det` 但发现 `PP-OCRv6_medium_rec`，说明模型文件放错目录：请重新检查 `models/ocr/ppocrv6_medium_det/`、`models/ocr/ppocrv6_medium_rec/`、`models/ocr/pp_lcnet_x0_25_textline_ori/` 里的 `inference.yml` / `inference.json` 是否来自对应模型仓库。检测模型、识别模型和方向分类模型不能互换目录。


如果 OCR 推理失败并输出 `ocr_inference_failed_onednn` 或 `ConvertPirAttribute2RuntimeAttribute`，这是 PaddlePaddle 3.x CPU oneDNN/PIR 路径兼容问题。工程会在导入 PaddleOCR 前默认设置 `FLAGS_use_mkldnn=0`、`FLAGS_enable_mkldnn=false`、`PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT=0`，并在 PaddleOCR 3.x 初始化参数中设置 `enable_mkldnn=false` 来禁用 oneDNN/MKLDNN；修改后请重新启动 CLI 进程再运行转换。如果仍失败，请更换与你的 Python / Windows 版本匹配的 PaddlePaddle CPU wheel。


PaddleOCR / Paddle 在模型初始化阶段可能打印 `Creating model: ...`、Windows `信息: 用提供的模式无法找到文件。` 或可选的 `No ccache found` 提示。默认配置 `models.ocr.suppress_startup_logs=true` 会在 PaddleOCR 导入和模型构造期间捕获这些启动噪声；这不会隐藏 OCR 推理失败，真实错误仍会写入 `ocr_results.json`。如需调试 PaddleOCR 原始启动日志，可在 YAML 中设置 `suppress_startup_logs: false`。
