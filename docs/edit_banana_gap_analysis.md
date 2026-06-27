# image2pptx 当前实现检视、Edit-Banana 对比与优化方案

> 日期：2026-06-27  
> 范围：基于当前仓库实现，并对照 Edit-Banana GitHub 公开 README / `main.py` / `config.yaml.example`。注意：Edit-Banana README 明确说明 GitHub 版本落后于线上服务，因此本文只对齐其公开代码与公开架构，不假设线上未开源能力。

## 1. 当前实现状态

当前项目已经是可运行的 **Image/PDF 页面 → SlideIR → PPTX** 工程化管线，主链路由 `ImageToPptxPipeline.run()` 串联：

1. `preprocess`：输入规范化，生成灰度、边缘、颜色空间、预览等 artifact。
2. `geometry` / `arrow`：OpenCV 轮廓、矩形、线段与基础 connector 候选。
3. `sam3`：可选 SAM3 endpoint 或本地 runtime，输出视觉区域候选。
4. `text` / `text_layer`：PaddleOCR 文本识别与文本层归一化。
5. `layout`：layout 模型与规则区域融合。
6. `table` / `formula` / `chart`：专项结构候选。
7. `layer_decomposition`：按 background、container、text、asset、connector 分层，并生成统一 `element_groups` 协议。
8. `vlm_arbitration`：可选 VLM 语义仲裁；仲裁后重建 `element_groups`，避免图层与元素组漂移。
9. `candidate_fusion`：以 `element_groups` 为主线，按 table/asset/formula/chart/container/text/connector 顺序融合为 SlideIR，并导出资产。
10. `pptx_render`：用 `python-pptx` 输出 `result.pptx`。

优点：

- 模块边界清晰，配置开关完整，CPU 与可选重模型路径都已覆盖。
- SlideIR 已经承载背景、shape、text、connector、asset、table、formula、chart 等元素类型。
- 有 artifacts、asset manifest、日志与测试基础，适合继续做质量闭环。

当前核心问题：

- 已新增 `CandidateElement` / `ElementGroup` 统一候选协议，`layer_decomposition` 会把 legacy candidates 适配为 `element_groups`，使 pipeline 主线从松散 dict 转向元素组/图层。
- `CandidateFusionProcessor` 已优先消费 `element_groups`，但仍承担资产裁剪、结构过滤、文本拆分、样式估计、connector 过滤、SlideIR 组装等职责，后续还需要拆成分组 fusion 子模块。
- PPTX native renderer 仍是短板：shape/connector/text ownership/style mapping 还不足以达到 Edit-Banana 展示的“每个元素独立可编辑”。
- 质量闭环未成为默认主路径：缺少稳定的 debug bundle、render-back preview、diff heatmap、bad-region refinement。
- 已清理掉一个不应进入通用管线的样例特化逻辑：`candidate_fusion` 之前会根据右侧文本位置和特定英文 token 合成卡片/标注框，这类 fixture-specific heuristic 会污染真实输入，现已删除。

## 2. 与 Edit-Banana 公开实现的关键差异

| 维度 | 当前 image2pptx | Edit-Banana 公开实现 | 差距 |
| --- | --- | --- | --- |
| 输出目标 | PPTX，强调 Office 原生可编辑 | DrawIO XML，强调图表元素可拖拽、改样式、替换模板 | PPTX native mapping 更难，需要更强 render plan |
| 主分割路径 | SAM3 是可选候选来源之一，输出会被适配进 `element_groups` | SAM3 是主路径，支持 prompt group：image / arrow / shape / background | 我们已有 group-first 中间协议，但仍缺少 per-group 质量统计与 SAM3 prompt group 驱动 |
| 文本路径 | OCR → text blocks → text layer → fusion | OCR 先生成 text-only DrawIO，再与 SAM3 空间 merge | 我们缺少可单独评估的 text-only 产物和文本召回 proxy |
| 公式 | 有公式候选与 Office Math 策略 | Pix2Text + high-res crop-guided strategy | 我们缺少 crop provenance、公式识别置信度与局部重跑 |
| 中间产物 | 有 artifacts 和 asset manifest，但索引不统一 | 输出 text-only XML、SAM3 visualization、metadata、metric/refinement 结果 | 我们需要统一 debug/index.json 和 overlay 集合 |
| 质量闭环 | evaluation 模块存在，但未强接入主链路 | metric evaluation + bad-region refinement | 我们还不能稳定回答“哪里没还原好” |
| 人工修复 | 暂无 patchable repair schema | README 展示 manual repair/save locally | 我们需要 SlideIR patch schema + rerender API |
| 失败策略 | fail-fast 明确，但低配环境体验偏硬 | 可通过 `--refine`、`--no-text`、prompt groups 控制 | 我们需要区分阻塞失败与可降级低置信候选 |

## 3. 已删除/整理的不必要代码

本次清理了 `CandidateFusionProcessor` 中的样例特化合成逻辑：

- 删除右侧文本自动合成 `synthetic_right_panel` 的规则。
- 删除命中特定英文 token（`from ambition`、`executable`、`patterns`）后合成 callout 的规则。
- 将 shape 候选来源恢复为实际 processor 产出的 `base_shapes`，避免凭某个演示图布局生成不存在的元素。

保留的规则仍然是通用规则：文本分块、结构性 image 区域过滤、asset manifest、背景 underlay、connector 装饰线过滤等。

## 4. 接下来建议优化路线

### Phase 1：可观测性与质量报告先行

交付：

- 每个 job 输出 `debug/index.json`，统一索引 normalized image、overlays、SlideIR、PPTX、asset manifest、quality report。
- 输出 overlay：geometry boxes、SAM3 masks、OCR boxes、layout regions、fused SlideIR boxes。
- 增加 render-back preview 与 diff heatmap。
- `quality_report.json` 至少包含：visual score、edge score、native_editability_ratio、residual_patch_area_ratio、text block count、connector endpoint score、top bad regions。

验收：能快速判断失败来自 OCR、SAM3、layout、fusion 还是 renderer。

### Phase 2：CandidateElement / ElementGroup 统一候选协议

当前已新增统一 schema，并由 `layer_decomposition` 生成 `ctx.candidates["element_groups"]`：

```python
class CandidateElement(BaseModel):
    id: str
    group: ElementGroup
    bbox: Rect
    score: float
    source: str
    mask_path: Path | None = None
    text: str | None = None
    style: dict[str, Any] = {}
    provenance: dict[str, Any] = {}
```

实施进度：当前由 layer decomposition 统一适配 SAM3、OCR、layout、geometry、table、formula、chart 等 legacy candidates；CandidateFusion 已优先消费 `element_groups`。下一步是让各 processor 原生输出 `CandidateElement`，并逐步移除 fusion 对 legacy dict 的 fallback。

### Phase 3：分组融合重构

推荐融合顺序：

1. Text / Formula first：先锁定文本和公式，避免被 asset 或 shape 吞掉。
2. Container / Shape second：建立 shape 与内部文本 parent-child。
3. Connector third：端点吸附到 shape anchor 或 text group。
4. Asset fourth：确认 logo/icon/image/chart/table 是 raster 还是 native。
5. Residual last：只对 bad regions 生成不可编辑残差图层。

### Phase 4：PPTX native renderer 增强

优先补齐：

- Office shape mapping：rectangle、roundRect、diamond、ellipse、parallelogram、cloud、callout。
- Connector mapping：straight / elbow / curve、begin/end arrow、dash、line width、color。
- Anchor snapping：connector 端点吸附 shape 的 top/right/bottom/left anchor。
- Text ownership：shape 内文本优先写入 shape text frame，而不是独立 textbox。
- Style provenance：fill、stroke、font、alignment、bold/italic 都记录置信度和来源。

### Phase 5：残差驱动 refinement

流程：

1. render-back diff 生成 bad regions。
2. 分类 bad regions：missing text、missing connector、style mismatch、unclassified raster。
3. 对局部 crop 重跑 OCR/SAM3/VLM 或规则检测。
4. 仍失败才生成 residual patch，并在 report 中标注不可编辑面积。

### Phase 6：人工修复闭环

交付：

- `slide_ir_patch.json` schema：add、update、delete、reorder、retype、link_connector。
- CLI：`image2pptx render --ir slide_ir.json --patch patch.json`。
- API：上传 patch 后重新渲染 PPTX。
- 简易 debug HTML：展示元素框、类型、置信度、source、可编辑策略。

## 5. 建议 PR 拆分

1. Debug bundle/index + overlay 输出。
2. quality_report 接入主流程。
3. CandidateElement/ElementGroup schema。
4. CandidateFusion 分组化与单元测试。
5. Connector snapping + Office shape/style mapping。
6. SlideIR patch schema + rerender API。
