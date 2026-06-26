# Edit-Banana 对标分析与改版规划

> 日期：2026-06-26  
> 目标：在撤回上一版大范围格式化/删减改动的基础上，参考 Edit-Banana 的公开设计，重新规划 `image2pptx` 的高保真可编辑重建路线。

## 1. 结论摘要

上一版改动主要集中在“删除冗余代码”和全仓格式化，属于代码整洁层面的改动；它没有直接解决用户感知到的核心问题：**转换效果、高保真还原、可编辑结构质量、以及失败区域的闭环修复**。因此本次应把工作重心从“清理代码”转为“结果质量导向的 pipeline 改造”。

Edit-Banana 的公开 README 将目标定义为把静态图像转换为可编辑资产，强调保留图形细节与逻辑关系，并以 SAM3、多轮 VLM 扫描、OCR/公式识别、DrawIO XML 生成和人工修复闭环为核心。我们的项目目标是 PPTX 输出，不能简单照搬 DrawIO 生成逻辑，但可以借鉴其分层、分组识别、质量评估和 refinement 思路。

## 2. Edit-Banana 可借鉴点

### 2.1 产品目标更聚焦：先保证图表/流程图高保真可编辑

Edit-Banana 的公开说明强调：

- 输入是 PNG/JPG/BMP/TIFF/WebP 等静态图像。
- 输出是可编辑 DrawIO XML。
- 重点场景是 flowchart、architecture、technical schematic、formula。
- 转换亮点包括布局逻辑、层级、颜色、线条、箭头样式、文字识别与独立可选元素。

对 `image2pptx` 的启示：短期不应追求“一张任意图片全部转成完美 PPTX”，而应优先定义高成功率场景：

1. 流程图/组织结构图；
2. 架构图/技术示意图；
3. 含少量公式或表格的学术图；
4. 背景相对干净、形状边界清晰的页面截图。

### 2.2 Pipeline 更偏“分组抽取 + 合并”

Edit-Banana README 描述的核心 pipeline 是：

1. 输入图像；
2. SAM3 分割；
3. 并行文本抽取，本地 OCR 定位文本，高分辨率 crop 交给公式引擎；
4. 合并 SAM3 与 OCR 空间结果并生成 DrawIO XML。

对 `image2pptx` 的启示：当前 pipeline 虽然已有 preprocess、layout、OCR、SAM3、fusion、render 等阶段，但需要把“分组抽取”明确为一等概念：

- background/container；
- shape；
- connector/arrow；
- text；
- image/icon/logo；
- chart/table/formula；
- residual patch。

每一组都应有独立候选、置信度、几何关系和回退策略，最后再做跨组融合，而不是让下游 renderer 被迫处理混杂元素。

### 2.3 人工修复与质量评估是关键闭环

Edit-Banana 明确展示了 manual repair 和 save locally。它还在 CLI 中提供 refinement 开关，并公开提到 metric evaluation/refinement 的方向。

对 `image2pptx` 的启示：要让效果变好，必须把输出质量拆解为可观测指标：

- 元素覆盖率：可编辑元素覆盖原图的面积比例；
- 残差热区：渲染回图后与原图差异最大的区域；
- 文本召回与文本位置误差；
- connector 端点吸附质量；
- 样式还原误差：fill、stroke、font、dash、arrowhead；
- 可编辑率：native PPTX 元素占比，而不是 raster patch 占比。

## 3. 与当前 `image2pptx` 的主要差距

| 维度 | Edit-Banana 公开方案 | 当前项目现状 | 差距 |
| --- | --- | --- | --- |
| 输出目标 | DrawIO XML，面向图形编辑 | PPTX，面向演示文稿编辑 | PPTX renderer 更复杂，需要 EMU 坐标、层级、字体与 Office shape 映射 |
| 分割策略 | SAM3 驱动，分组 prompt | 已有 SAM3/segmentation 相关模块 | 需要把 prompt group、候选 provenance、置信度策略固定下来 |
| 文本/公式 | OCR + crop-guided formula | 已有 text/formula processor | 缺少统一的 crop 归档、公式回填和文本块 merge 评价 |
| 融合 | SAM3 + OCR 空间 merge | 已有 candidate_fusion | 需要围绕 element group 做更严格的冲突消解和层级规则 |
| 质量闭环 | metric/refinement、人修展示 | 已有 evaluation/refinement 雏形 | 缺少可执行阈值、失败区域再识别和用户可理解报告 |
| 产品闭环 | 在线体验 + 人工修复 | API/CLI 输出文件 | 需要输出 debug bundle 和人工校正入口/JSON patch 格式 |

## 4. 改版路线图

### Phase 0：撤回无效大范围清理，恢复可评审基线

- 已撤回上一版“全仓格式化 + 冗余删除”的提交，避免把格式改动和效果改进混在一起。
- 后续每个 PR 只做一个目标明确的效果改进，便于评估输入/输出差异。

### Phase 1：建立 Edit-Banana 风格的 debug bundle 与质量指标

目标：先能量化“效果不好”在哪里。

交付物：

1. 每次转换输出 `debug/`：normalized image、SAM masks、OCR boxes、fused elements、render preview、diff heatmap、quality report JSON。
2. 新增或完善质量指标：coverage、residual area、native editability ratio、text recall proxy、connector endpoint score。
3. CLI/API 增加 `--debug` 或配置项，不改变默认输出。

验收：给同一张 fixture 图，能定位是文本、形状、箭头还是图层顺序导致失败。

### Phase 2：分组候选抽取与融合重构

目标：让 pipeline 的中间表示更接近“可编辑图形结构”。

交付物：

1. 定义 `ElementGroup` 或复用现有 `ElementType`，明确 background/shape/text/connector/image/formula/table/residual。
2. SAM3/layout/OCR 结果都带 provenance、source score、group score。
3. fusion 按 group 分层处理：先 text 与 formula，再 shape/container，再 connector，最后 residual patch。
4. 冲突规则明确化：文本不被 shape 覆盖、connector 不吞成 icon、container 低层级。

验收：流程图 fixture 中矩形、菱形、箭头、文本分别可编辑，且不互相覆盖。

### Phase 3：PPTX renderer 的图形映射增强

目标：把识别结果尽量输出为 native PPTX，而不是图片贴片。

交付物：

1. shape taxonomy 到 Office shape 的映射表。
2. connector endpoint snapping：线端吸附到最近 shape anchor。
3. stroke/fill/dash/arrowhead 样式还原。
4. text box 与 shape text 的归属规则。

验收：输出 PPTX 中主要流程图元素可单独选中、拖动、改文字、改颜色。

### Phase 4：残差驱动 refinement

目标：针对转换失败区域做局部补救，而不是全图重跑。

交付物：

1. render-back preview 与原图 diff。
2. bad region clustering。
3. 对 bad region 重新触发 OCR/SAM3/VLM 局部识别。
4. 低置信度时以 residual patch 保底，同时在 report 中标记不可编辑区域。

验收：复杂图上 native editability ratio 提升，且 residual patch 面积下降。

### Phase 5：人工修复协议

目标：让用户能修正模型判断，形成稳定可复用的编辑闭环。

交付物：

1. 输出 `slide_ir.json` 的 patch schema：移动、删除、改类型、改样式、关联 connector。
2. API 接受 patch 后重新 render PPTX。
3. debug HTML 或轻量前端展示元素框和类型。

验收：用户无需改代码即可修正误识别元素并重新导出 PPTX。

## 5. 下一步建议 PR 拆分

1. **PR-1：debug bundle + quality report**  
   只新增诊断输出，不动核心识别逻辑。

2. **PR-2：ElementGroup/provenance schema**  
   统一中间表示，减少 processor 之间的信息丢失。

3. **PR-3：connector endpoint snapping**  
   单点优化箭头/连线，这是流程图可编辑体验的关键。

4. **PR-4：render-back diff heatmap**  
   为 refinement 和量化评估打基础。

5. **PR-5：局部 refinement MVP**  
   用 bad region 做局部再识别或 residual patch fallback。

## 6. 风险与边界

- Edit-Banana 当前公开仓库说明其 GitHub 版本落后于线上服务，因此只能借鉴公开架构思路，不能把线上效果当成本地代码可直接复现的基准。
- Edit-Banana 输出 DrawIO，而本项目输出 PPTX；PPTX 的 shape、connector、字体和层级模型不同，需要做专门映射。
- SAM3、OCR、公式识别、VLM 均是可选依赖，应保持 CPU/无模型环境下的降级路径。
- 不建议再做大范围纯格式化 PR；这会掩盖真正影响效果的逻辑改动。
