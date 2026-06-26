# 当前 image2pptx 流程对比 Edit-Banana：差异分析与改进计划

> 日期：2026-06-26  
> 目的：不再做泛泛的“参考路线图”，而是把当前 `image2pptx` 的真实 pipeline 与 Edit-Banana 公开流程逐项对齐，找出导致效果不理想的结构性差异，并拆成可执行改进计划。

## 1. 结论

当前 `image2pptx` 已具备完整的“输入预处理 → 视觉/文本/结构候选 → 候选融合 → SlideIR → PPTX 渲染”链路，但它更像一个**多模块串联的工程管线**；Edit-Banana 的公开设计更像一个围绕“图表元素可编辑重建”优化过的**分组抽取 + 质量闭环管线**。

核心差异不是“有没有 SAM3/OCR/VLM”，而是：

1. Edit-Banana 把图表可编辑重建作为唯一主目标，输出 DrawIO XML；当前项目同时处理 PPTX、布局、资产、表格、图表、公式等，目标更宽，导致主路径不够聚焦。
2. Edit-Banana 以 SAM3 prompt group 和 OCR 空间结果为主线合并；当前项目的候选来源较多，但缺少统一的 element-group contract、分组置信度和冲突规则。
3. Edit-Banana 在输出目录保留 SAM3 可视化、metadata、text-only XML、metric/refinement 中间结果；当前项目有 artifacts 与日志，但缺少稳定 debug bundle 和可量化质量门槛。
4. Edit-Banana 将 manual repair/refinement 作为体验闭环；当前项目输出 PPTX/SlideIR 后缺少 patchable repair schema 和二次渲染入口。
5. 当前 PPTX renderer 的 native shape/connector 映射还比较基础，是影响“看起来像”和“编辑起来像”的关键短板。

因此改进顺序应为：**先建立可观测质量闭环，再重构分组融合，最后增强 PPTX native renderer 与人工修复**。不建议再次进行大范围格式化或泛清理。

## 2. 当前 image2pptx 流程拆解

根据当前代码，主流程由 `ImageToPptxPipeline.run()` 串联以下阶段：

| 顺序 | 当前阶段 | 当前作用 | 当前产物/问题 |
| --- | --- | --- | --- |
| 0 | preprocess | 规范化输入，生成 gray/edges/lab/hsv/preview 等 artifacts | 有基础 artifacts，但没有统一 debug bundle 索引 |
| 1 | geometry + arrow | OpenCV 轮廓/矩形/线段与基础 connector | 偏规则化，容易受复杂背景影响；connector 缺少端点吸附与形状归属 |
| 2 | sam3 | 调用 SAM3 adapter 产出视觉 regions | SAM3 warning 会中断；缺少 Edit-Banana 风格 prompt group 主线和 per-group 输出 |
| 3 | text | PaddleOCR 文本识别 | 对本地模型依赖较强；失败会中断；尚未与公式 crop/文本层级形成闭环 |
| 4 | layout | layout 模型 + 规则区域融合 | 可生成 layout_regions，但与 SAM3/OCR 的融合 contract 还不够稳定 |
| 5 | text_layer | 文本行/角色/样式归一化 | 有 TextLayer 雏形，但后续 renderer 中 shape-owned text 归属不足 |
| 6 | table/formula/chart | 特定结构候选 | 能产出候选，但缺少渲染回图后的质量评价与局部补救 |
| 7 | layer_decomposition | 显式分层 background/container/text/asset/connector | 方向正确，但仍需要作为所有 processor 的统一输入/输出约束 |
| 8 | vlm_arbitration | VLM 语义仲裁 | 可选能力；失败路径和置信度落地仍需避免阻塞主流程 |
| 9 | candidate_fusion | 合并为 SlideIR，并生成图片资产 | 当前核心瓶颈：融合逻辑集中、规则多、难以单独评估每组质量 |
| 10 | pptx_render | 使用 python-pptx 输出 PPTX | native shape/connector/style 映射较基础；公式/table/chart 也需更强 Office 原生能力 |

## 3. Edit-Banana 公开流程拆解

Edit-Banana README 与 `main.py` 公开描述的主线可以概括为：

| 顺序 | Edit-Banana 阶段 | 作用 | 对我们的启发 |
| --- | --- | --- | --- |
| 0 | preprocess + output dir | 为每张图建立独立输出目录 | 每个 job 应有完整 debug bundle，不只输出 PPTX/IR |
| 1 | text OCR | OCR/text-only XML，支持 Tesseract/PaddleOCR | 文本应先成为独立可视化/可评估产物，再参与融合 |
| 2 | SAM3 segmentation | fine-tuned SAM3 分割图表元素，可按 prompt group 抽取 | SAM3 应按 group 输出 shape/icon/connector/container 等，而不是仅给泛 regions |
| 3 | shape/icon processing | 对 SAM3 元素做形状/图标处理 | 图标/图片/shape 的边界要在融合前确定，减少 renderer 猜测 |
| 4 | XML fragments | 为各元素生成 XML fragment | 对 PPTX 来说应等价为“元素级 native render plan” |
| 5 | metric evaluation | 评估 pixel coverage、bad regions、overall score | 必须补齐 render-back diff 和质量阈值 |
| 6 | refinement | 对 bad regions 局部补救 | 不应全图重跑；应局部 OCR/SAM/VLM 或 residual patch fallback |
| 7 | XML merge | 合并 DrawIO XML | 对我们是 SlideIR/PPTX render，需保留层级和关系 |

Edit-Banana 的公开特点：

- 强调 fine-tuned SAM3、fixed multi-round VLM scanning、local OCR、Pix2Text formula、crop-guided strategy。
- 输出 DrawIO XML，所有元素可拖拽、改样式、替换模板。
- 明确保留中间输出：SAM3 visualization、metadata、text-only DrawIO、metric/refinement 结果。
- 支持 `--refine` 与 `--no-text` 这类明确开关。
- README 明确提示 GitHub 版本落后于线上服务，因此这里只能参考公开架构，不应假设线上能力可直接复现。

## 4. 差异对比矩阵

| 维度 | 当前 image2pptx | Edit-Banana | 影响 | 改进方向 |
| --- | --- | --- | --- | --- |
| 产品目标 | 图片/PDF 页到 PPTX，可编辑与还原并重 | 静态图到 DrawIO XML，聚焦图表可编辑 | 当前范围更广，评估标准不够聚焦 | 先以流程图/架构图作为 MVP 场景 |
| 输出模型 | SlideIR → python-pptx | ElementInfo/XML fragment → DrawIO XML | PPTX native mapping 更难 | 增加 PPTX render plan，显式记录 shape/connector/text/table/chart 渲染策略 |
| SAM3 使用 | adapter 输出 `sam3_regions`，warning 中断 | SAM3 是主分割路径，可按 PromptGroup 抽取 | 当前 SAM3 结果对融合约束弱 | 引入 `ElementGroup` 与 group prompt 输出目录 |
| OCR/文本 | PaddleOCR 主路径，输出 text/text_layer | OCR 先生成 text-only XML，再与 SAM3 merge | 当前文本质量难单独评估 | 输出 `text_debug.json`、text overlay、文本召回 proxy |
| 公式 | 有 FormulaProcessor | crop-guided Pix2Text/LaTeX | 当前公式与 OCR crop 关系弱 | 把公式作为 OCR crop 的子流程，保存 crop 与 latex/provenance |
| 候选融合 | CandidateFusion 汇总多源候选 | SAM3 + OCR 空间 merge 后 XML | 当前融合集中复杂，难定位问题 | 分 group fusion：text/formula → shape/container → connector → asset/residual |
| connector | OpenCV Hough + renderer connector | 强调箭头样式、线宽、虚线、层级 | PPTX 中箭头端点/样式弱 | 端点吸附、arrowhead/dash/line width 样式估计 |
| 背景/残差 | blurred raster underlay + assets | 可编辑元素 + refinement 补坏区 | 当前容易“看着像但不可编辑” | native editability ratio 与 residual patch ratio 作为质量指标 |
| 质量评估 | 有 metrics/quality_report 雏形，但未成为主流程 | metric evaluator + bad region refinement | 不能量化“效果不好” | 每次输出 render preview、diff heatmap、quality report |
| 人工修复 | 输出 SlideIR/PPTX 后缺少修复协议 | manual repair/save locally | 用户无法闭环纠错 | 增加 SlideIR patch schema 与 rerender API |
| 降级策略 | 多阶段 warning 可能中断 | README 有 optional deps 与 skip 开关 | 无模型环境体验不稳 | 失败不阻塞时转为 low-confidence/residual，并写入 report |

## 5. 改进计划

### Phase 1：Debug Bundle 与质量报告先行

目标：先回答“哪里效果不好”。这是后续所有改进的基础。

交付内容：

1. 每个 job 输出 `debug/index.json`，列出所有中间产物。
2. 保存 overlay 图：geometry boxes、SAM masks、OCR boxes、layout regions、fused SlideIR boxes。
3. PPTX render-back preview：将 PPTX 或 SlideIR 渲染回图片。
4. diff heatmap：原图 vs render preview。
5. `quality_report.json`：
   - visual_score / mae / edge_score；
   - native_editability_ratio；
   - residual_patch_area_ratio；
   - text_block_count / missing_text_proxy；
   - connector_endpoint_score；
   - top bad regions。

验收标准：

- 对同一输入，能明确看到失败来自 OCR、SAM3、fusion、renderer 还是层级。
- 不改变默认 PPTX 输出效果，只新增可观测产物。

### Phase 2：ElementGroup + Provenance Contract

目标：把 Edit-Banana 的 prompt group 思路迁移到 SlideIR 前的统一候选协议。

建议新增中间候选 schema：

```python
class CandidateElement(BaseModel):
    id: str
    group: ElementGroup  # background/container/shape/text/connector/asset/formula/table/chart/residual
    bbox: Rect
    mask_path: Path | None = None
    text: str | None = None
    style: dict[str, Any] = {}
    score: float
    source: str  # sam3/ocr/layout/opencv/vlm/refinement/manual
    provenance: dict[str, Any] = {}
```

实施要点：

1. SAM3、layout、OCR、geometry 都输出 `CandidateElement` 或兼容 adapter。
2. 每个 group 有独立 score 和 required fields。
3. 保留原始 source payload，便于 debug 和人工修复。
4. CandidateFusion 不再直接读取各种松散 dict，而是消费统一 candidates。

验收标准：

- 任意候选都能追溯来源、置信度、mask/crop、group。
- 单元测试覆盖 text/shape/connector/asset 的冲突规则。

### Phase 3：分组融合重构

目标：把 CandidateFusion 从“大杂烩融合器”改成可评估的分组流水线。

推荐顺序：

1. Text/Formulas first：文本与公式优先锁定，避免被 shape/asset 吞掉。
2. Containers/Shapes second：识别承载文本的 shape/container。
3. Connectors third：端点吸附到最近 shape anchor 或文本 group。
4. Assets fourth：logo/icon/image/chart/table 确认是否 raster/native。
5. Residual last：只对无法 native 化区域生成 residual patch。

关键规则：

- 文本 bbox 与 shape bbox 高重叠时，不删除文本；应建立 parent-child。
- connector 与 shape 相交时，不作为 shape 填充；应做 endpoint snapping。
- 大面积低纹理区域优先 container/background，不应作为 image asset。
- residual patch 必须有 bad-region provenance，不能成为默认保底背景。

验收标准：

- 流程图 fixture 中 shape、text、connector 分别可选中。
- native editability ratio 提升，residual patch ratio 不增加。

### Phase 4：PPTX Native Renderer 增强

目标：解决“识别对了但 PPTX 编辑体验差”。

交付内容：

1. Office shape mapping：rectangle、roundRect、diamond、ellipse、parallelogram、cloud、callout 等。
2. Connector mapping：straight/elbow/curve、begin/end arrow、dash、line width、color。
3. Anchor snapping：connector 端点吸附到 shape 的 top/right/bottom/left anchor。
4. Text ownership：shape 内文本优先写入 shape text_frame，而不是独立 textbox；必要时保留独立 textbox。
5. Style extraction：fill、stroke、font、alignment、bold/italic 的置信度记录。

验收标准：

- 输出 PPTX 中主要图形不是背景截图，而是 Office 原生 shape/connector/text。
- 用户能移动 shape 时保留内部文字，拖动 connector 时端点关系更合理。

### Phase 5：残差驱动 Refinement

目标：学习 Edit-Banana 的 metric/refinement 闭环，用失败区域驱动局部修复。

流程：

1. render-back diff 生成 bad regions。
2. 对 bad regions 聚类并分类：missing text、missing connector、style mismatch、unclassified raster。
3. 局部重跑 OCR/SAM3/VLM 或规则检测。
4. 仍失败则生成 residual patch，但在 report 中标注不可编辑。

验收标准：

- refinement 后 bad region area 下降。
- 低置信区域不会静默变成“看似成功”的 raster 背景。

### Phase 6：人工修复协议

目标：补齐 Edit-Banana manual repair 的产品闭环。

交付内容：

1. `slide_ir_patch.json` schema：add/update/delete/reorder/retype/link_connector。
2. `image2pptx render --ir slide_ir.json --patch patch.json`。
3. API：上传 patch 后重渲染 PPTX。
4. 简易 debug HTML：展示元素框、类型、置信度、source。

验收标准：

- 用户可在不改代码的情况下修正误识别元素并重新导出 PPTX。

## 6. 建议 PR 拆分

1. **PR-1：debug bundle/index + overlay 输出**  
   只加观测产物，不改识别逻辑。

2. **PR-2：quality_report 接入主流程**  
   增加 render preview/diff heatmap 与质量 JSON。

3. **PR-3：CandidateElement/ElementGroup schema**  
   让所有 processor 输出统一候选协议。

4. **PR-4：CandidateFusion 分组化**  
   按 text/formula、shape/container、connector、asset、residual 分阶段融合。

5. **PR-5：connector snapping + style mapping**  
   先解决流程图最影响编辑体验的连线问题。

6. **PR-6：PPTX shape/text ownership 改造**  
   让 shape 内文本成为 shape 的文本，而不是漂浮 textbox。

7. **PR-7：residual-driven local refinement MVP**  
   用 bad regions 触发局部补救。

8. **PR-8：manual repair patch schema + rerender**  
   补齐用户闭环。

## 7. 优先级建议

如果只能先做一件事：做 **PR-1 + PR-2**。因为没有 debug bundle 与质量报告，就无法判断后续改动是变好还是变差。

如果目标是尽快提升用户观感：做 **PR-5 + PR-6**。流程图/架构图中 connector 与 shape text ownership 是最容易被用户感知的编辑体验差异。

如果目标是对齐 Edit-Banana 架构：做 **PR-3 + PR-4**。统一候选协议与分组融合是长期架构基础。

## 8. 风险与边界

- Edit-Banana GitHub README 明确提示公开仓库落后于线上服务，因此不能把线上效果等价为开源代码可直接复现能力。
- Edit-Banana 输出 DrawIO XML；本项目输出 PPTX，Office shape、connector、字体、EMU 坐标和层级模型都不同。
- SAM3、PaddleOCR、Pix2Text/VLM 都可能缺依赖或模型；必须保留 CPU/无模型降级路径。
- 任何效果改进 PR 都应附带 debug 输出或至少固定 fixture 对比，避免主观判断。
