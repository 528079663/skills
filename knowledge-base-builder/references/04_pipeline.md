# 04 · 入库流水线、变更同步与演化

> 本文件定义知识库的**目标物理结构**、**笔记粒度规则**、资料从进入知识库到归档的完整流水线、`_流程.md`/`_总览.md` 生成规则、原文变更同步、双向演化、**旧库迁移路径**，以及各 Step 验收清单。
> 配套脚本（**只列核心**；权威清单在 `SKILL.md` 的资源索引）：`scan_sources.py`、`doc_map.py`、
> `split_boundaries.py`（块内候选边界，深抽前）、`convert_sources.py`（docx/epub/odt → `_meta/converted/*.md`）、
> `autolocate.py`（定位符计算 + 笔记定位复核，门禁）、`tag_documents.py`、`build_flows.py`、`build_topics.py`、
> `search_index.py`、`render_templates.py`、`verify.py`。

## 目录
1. 目标物理结构
2. 笔记粒度规则（核心）
3. 资料类型分流总表
4. 各类资料入库细则
5. `_流程.md` 与 `_总览.md` 生成规则
6. 未归桶资料处理流程
7. 变更 / 更新同步流水线
8. 双向演化机制
9. 旧库迁移路径（加法，非重写）
10. 各 Step 验收清单
11. verify.py 检查项
12. 进度与续跑（progress.py）

---

## 1. 目标物理结构

```
<kb>/
├── 工作流/
│   └── <flow>/
│       ├── _流程.md                 ← 流程总览（环节顺序 + 关键 SOP）
│       ├── 1_<stage>/
│       │   ├── _总览.md             ← 环节索引（子技巧/案例/工具/坑）
│       │   └── <原子笔记>.md
│       └── 2_<stage>/
├── 概念索引/                        ← units 产物（跨工作流概念/SOP/关系）
├── 素材库/
│   └── _来源地图/                   ← 来源笔记（文档级，指向衍生原子笔记）
├── 00_导航/（主题地图/文件目录/模块视图）
├── 99_收件箱/
├── projects/（跨工作流一键拉取 recipe）
├── _meta/（doc_maps/coverage_audit/search.db/模板/日志）
├── AGENTS.md
└── README.md
```

**主轴铁律**：
- 每篇原子笔记归 **1 个 flow、1 个 stage、1 个 substage**；
- flow+stage 决定物理目录，substage 决定环节内分组（在 `_总览.md` 聚合）；
- 源文件可在根目录或任意子目录，脚本不要求固定层级；
- 六维标签和 units 是辅助层，不决定目录。

---

## 2. 笔记粒度规则（核心）

### 2.1 从"一篇文档一篇笔记"改为"按语义单元拆篇"（块只是输入容器）

- `doc_map.py` 先按标题切块、估算知识密度、标记高价值块；
- **每个高价值块 → N 篇原子笔记（N≥1）**，粒度单位是**语义单元**（一个可独立回答的问题/结论），不是块：
  一块里装了 6 件事就拆 6 篇，一块只有一件事就是 1 篇；**"一块一篇"不是要求，也不许把多件事塞进一篇**；
  一个语义单元也可以跨块——跨块时**以主块为主来源**，其余块依次列进 `source_locator` 列表（见 §2.3），
  frontmatter 带 flow/stage/substage；
- **文档级 → 1 篇来源笔记**，放 `素材库/_来源地图/`，指向所有衍生原子笔记；
- 低密度块不深抽，在 doc_map 里记 skip 原因；
- **提交单位＝一篇文档一批**：一篇文档的全部候选段（带 `dense`／`oversized_fence`／`media_table` 标记）
  一次性给模型、**一次返回 N 篇**，**不要一块一往返**。省的是会话往返次数与每轮重复注入的上下文，
  **不是 API 折价**（本库无模型客户端）。细则见 `08` §3 第 9 条末。

> **为什么改**：块长由"原文有没有标题"决定，不由"有几个知识点"决定。真库实测高价值块
> 中位 479 字、p75 813 字、p90 1,401 字、最长 36,424 字，>800 字占 25.5%——
> 按"一块一篇"要么一篇塞六件事，要么丢弃五件。判据见 `08` 第 3 节硬约束 9。

**例**：一篇妙记讲 3 个环节（找素材/写文案/做视频）：
- 产出 ≥3 篇原子笔记（分别归到对应环节目录；同一环节里若有两个可独立回答的结论，就出两篇）；
- 产出 1 篇来源笔记（记录原文档 + 全部衍生笔记链接）。

### 2.2 flow/stage/substage 怎么判定

- **规则脚本（tag_documents.py）只打六维辅助标签**，不判 flow/stage；
- **flow/stage/substage 由 AI 读高价值块正文判定**：
  - flow：该块主要服务于哪件"要做的事"；
  - stage：该块属于该工作流的哪个环节；
  - substage：该块是"总览/子技巧/案例/工具/坑"中的哪一类；
- 判定不了的块进 `99_收件箱`，不硬判；
- 一个语义单元若跨多个环节，以"主要教什么"归 1 个主环节，**不重复建笔记**；
  其余环节的可发现性靠 frontmatter 六维标签 / `topics` 与 units 的 `relation` 单元表达，
  **不为此写 `[[链接]]`**——双链只表示正文的引用跳转，见 `08_topics_pipeline_units.md` 第 3.6 节。

### 2.3 原子笔记 frontmatter

```yaml
---
title: 笔记标题
flow: 视频制作
stage: 1_找素材
substage: 子技巧
domains: [商业]
forms: [自媒体]
tools: []
types: [方法]
projects: [AI自媒体]
topics: [选品, 关键词]
q_hooks:               # 3–5 条口语问法（用户会怎么问这件事），录入时顺手生成；检索优先匹配
  - 视频爆款分析
  - 热门内容怎么归因
sources: [素材库/.../原文.md]
source_locator:            # 引用定位符列表：每项贴紧一处 quote；**首项所在的块 = 主块**；
  - §章节#char=起始-结束   # 语义单元跨块时，其余块的定位符按引用顺序往下列
  - §另一章#char=起始-结束
confidence: high
status: confirmed
---
```

> **`source_locator` 是 block 列表，不是标量。** 三条口径写死在这里：
> ① **只用 block 列表（每行一个 `- §…#char=`），不要用内联 `[a, b]`**；
> ② **将来任何要读 `source_locator` 的脚本必须走 `fm_list` 风格自己解析块列表，
> 不能用 `parse_frontmatter`** ——`verify.py` / `search_index.py` 里那份 `parse_frontmatter`
> 是按 `line.split(":", 1)` 行切的，块列表的 `- ` 行不含冒号，会被静默丢掉、读成空值。
> `sources` 的同类教训已经写在 §11 的 C5 行里（多基准路径 + 逐篇非空）。
> ③ **定位符由 `scripts/autolocate.py --compute` 算，不由写的人给区间**：交 quote、拿回
> `§标题#char=a-b`（标题从 `_meta/doc_maps.jsonl` 读）；唯一命中才给，多命中报歧义、零命中 rc≠0 拒绝编造。
> 写完的笔记用 `--check <笔记.md>` 复核（门禁：区间复算不等、或清单行 `[char=a-b]` 贴的不是最贴合的那条
> 已立据区间，即 rc≠0）。口径细则见 `08_topics_pipeline_units.md` §3 第 8 条。
> **读它的脚本**：`progress.py`（用 `source_locator` ＋ doc_maps 反算覆盖率）与
> `check_verbatim_lite.py`（用首项定"主块"、用全部项定"多的参照"）——两者都必须走 `fm_list` 风格自己解析；
> 字段本身**仍不进 C1–C15 门禁**，写错不会红，只会让这两处的读数失真。

> `q_hooks` 的生成规约与质量红线见 `08_topics_pipeline_units.md` 第 3.5 节。**已有 q_hooks
> （人工或模型写的）默认不覆盖**——深抽（增量）路径**没有开关**，是否覆盖由执行 AI 按第 3.5 节
> 规约判定；存量路径要整体重生成只有 `backfill_hooks.py --force`（全局生效，会一并覆盖人工写的 hook）。
> 笔记落盘后跑 `scripts/check_hooks.py` 校验；schema、降级与覆盖
> 细则见 `06_retrieval.md` 第 8 节。

### 2.4 来源笔记 frontmatter

```yaml
---
title: 来源·<原文档标题>
source_doc: <源文件相对路径>
source_doc_id: doc-xxxxxxxx
derived_notes:
  - 工作流/视频制作/1_找素材/xxx.md
  - 工作流/视频制作/2_写文案/yyy.md
status: confirmed
---
```

---

## 3. 资料类型分流总表

| 资料类型 | 识别方式 | 默认去向 | 是否复制本体 |
|---|---|---|---|
| 正文 md | 扩展 `.md`，排除索引类 | 读高价值块、按语义单元提炼为原子笔记（一块可出 N 篇） | 否 |
| 精华笔记 md | 文件名匹配 `·精华笔记.md` | 对应原文存在→引用原文；原文缺失→作为正文提炼 | 否 |
| 妙记 txt | `妙记` 路径下 `.txt` | 引用精华笔记；无则按 config 的 `essenceless_minutes` 动作（见 4.2） | 否 |
| 逐字稿 transcript | `.transcript.txt` | 无精华时生成精华或按正文提炼 | 否 |
| srt | `.srt` | 与 txt 配对，仅留路径 | 否 |
| PDF | `.pdf` | 有同名 md→跳过；孤儿→按 4.3 节孤儿 PDF 处置 | 否 |
| 可直读的非 md 正文 | `.vtt` `.ass` `.html` `.htm` `.rtf`（`.md/.txt/.srt` 见上面各行） | **只登记 + 受 C14 只读保护**；`doc_map` 本批不解析它们 → **不深抽**；要抽必须先转成 md/txt 再走 intake | 否 |
| 需转换的正文 | `.docx` `.epub` `.odt` | 同上：登记 + 保护 + 不深抽；转换后才是正文 | 否 |
| 图片 | jpg/png/webp/gif/heic | 笔记内相对路径引用 | 否 |
| 视频 | mp4/mov/webm | 登记到资源清单 | 否 |
| 压缩包/安装包 | zip/rar/exe/apk | 登记资源清单 | 否 |
| 数据/脚本 | xlsx/csv/py/json/jsonl | 不进知识层（扫描类清单除外） | 否 |

总原则：知识层只新增"提炼物 + 路径索引"，源目录只读。

---

## 4. 各类资料入库细则

### 4.1 正文 md → 原子笔记

1. 跑 `doc_map.py` 出章节地图（切块/密度/高价值块）。
2. 对每个高价值块：先切**语义单元**（一个可独立回答的问题/结论算一个），再逐个成篇——
   产出 N 篇原子笔记（N≥1），不是固定 1 篇：
   - AI 判定该语义单元的 flow/stage/substage；
   - 按原子笔记模板写笔记（三段分标：`evidence.quote` 原话 / 主字段归纳 / `inference` 推断）；
   - 数字/命令/代码带 `§章节#字符` 定位，逐字保留。
3. 文档级写 1 篇来源笔记，指向所有衍生原子笔记。
4. 同批回填 `_meta/coverage_audit.jsonl`（每 chunk 一行）。
   `coverage_audit.jsonl` 记录块级跳过原因；进度事实以 `progress.py` 反推为准。
   **两者冲突时 progress 赢，`coverage_audit` 标过期**（它不是进度权威源，见第 12 节）。
5. 若开 units：按 `references/08` 第 3 节产出 `_meta/units.jsonl`，跑 `validate_extraction.py`。
6. 已有同名笔记：不覆盖；原文更新走第 7 节，否则跳过。

### 4.2 精华笔记 / 妙记 / 逐字稿

- **精华笔记**：
  - 对应原文 md 存在 → 作为引用，不独立提炼（原文已被 doc_map 处理）；
  - **对应原文缺失（已删/未下载）→ 精华笔记作为正文进入 doc_map**，不能丢主题。
- 妙记 txt 有精华 → 引用精华；无精华 → 按 config 的 essenceless_minutes 动作。
- srt 仅用于回溯时间轴，不进入提炼。

### 4.3 PDF

- 同名 md 存在 → 跳过。
- 孤儿 PDF：
  - 卡片型（如 505 知识卡片）→ 提取卡片文本为独立卡片；
  - 问答整理 → 提取为问答笔记；
  - 无解析能力时降级登记路径，列入问题资产库。
- **推广到所有非 `.md` 正文（A4，发现 32）**：`.docx/.epub/.odt`（需转换）与 `.vtt/.ass/.html/.htm/.rtf`
  （可直读）一律**降级登记 + 列入 `_meta/问题资产库.md`**，由人或外部转换工具转成 md/txt 后再走 intake 深抽。
  **扩清单 ≠ 可深抽**：`doc_map.py` 至今只吃 `.md`，`TEXT_BODY_EXT` 变宽只带来两件事——
  manifest 里多两档登记（`documents.other_readable` / `documents.needs_convert`）和 C14 的只读保护面变宽。
- **转换有脚本了（`scripts/convert_sources.py`）**：按扩展名显式分派（`.docx`→`partition_docx`、
  `.epub`→`partition_epub`、`.odt`→`partition_odt`；`magic` 只当"扩展名与真实类型不符"的兜底核验，
  且放在子进程里跑），**转换产物的路径以 `<kb>/_meta/converted/` 为根**——那是**第二个源根**，
  笔记 `sources` 写 `_meta/converted/<相对路径>.md`（C5 认 `<kb>/<rel>` 这一档），quote/char 定位符
  也一律对**产物**算。产物是**派生物**，与 `doc_maps.jsonl` / `search.db` 同级，可删可重建；
  转换时间等易变量记在边车 `_meta/converted/_manifest.json` 里，不进产物头部——头部**只留原文件名＋源 sha256
  前 12 位**（unstructured 版本、`converted_at`、元素统计、字数都在边车），保证同样输入两次转换**逐字节相同**。
  三条守卫：`--source-root` 落在 kb 内直接拒（防无限套娃）／只写 `_meta/converted/`、源目录一字不动／
  `--dry-run` 零写盘。缺依赖 → rc≠0 ＋ stderr 点名缺哪个包，不静默跳过；`.pdf` 本轮明确不接。
  写完自动调 `doc_map.py --append`，把产物按 `path` 并进同一份 `_meta/doc_maps.jsonl`（同名覆盖、其余保留）。
  **硬规则：转换产物的头部是产物字节的一部分；定稿后不许改，改了必须重算全部引用该产物的定位符。**
  理由（实测）：头部一变，产物内的 char 区间**整体位移**——把 `｜unstructured 0.27.16` 挪进边车那一次改动，
  同一句话在 docx 产物里的区间就从 `91-103` 变成 `70-82`。重算办法不是估：把该产物所有既有 evidence 的 quote
  逐条喂 `autolocate.py --compute` 拿回新区间，再对改写后的笔记跑 `--check`（门禁，rc≠0 即没算完）。
  另一个连带：**`doc_map.is_body` 的 200 字节门槛吃的也是含头部的总字节**（同一次改动让一个 39 字正文的 epub 夹具
  从 220B 掉到 198B，于是它不再进 doc_maps——真文档远大于这个数，但**小产物会不会被登记取决于头部**这件事是真的）。

### 4.4 图片 / 视频 / 安装包

- 图片：笔记需要时用相对路径 `![](<...>)`，不搬运。
- 视频/安装包/压缩包：登记到资源清单（名称/路径/类型/用途一句话）。

---

## 5. `_流程.md` 与 `_总览.md` 生成规则

由 `build_flows.py` 从原子笔记 frontmatter 聚合生成，**每批原子笔记写完后必须重跑**。

### 5.1 `_流程.md`（每个 flow 一份）

- 位置：`工作流/<flow>/_流程.md`
- 内容：
  - 该工作流的环节顺序（按目录序号 1_、2_…）；
  - 每个环节一句话 + 链接到该环节 `_总览.md`；
  - 跨环节的关键 SOP（从 substage=总览 的笔记聚合；**当前 build_flows.py 输出占位，待后续版本自动提取**）。

### 5.2 `_总览.md`（每个 stage 一份）

- 位置：`工作流/<flow>/<n>_<stage>/_总览.md`
- 内容：按 substage 5 组列出该环节下所有笔记链接：
  - **总览**：环节方法论；
  - **子技巧**：可独立操作的技巧；
  - **案例**：真实项目/复盘；
  - **工具**：工具/资源/提示词；
  - **坑**：注意事项/失败教训。
- 空分组标"（暂无）"，不删除分组。

---

## 6. 未归桶资料处理流程

### 阶段 A · 只读扫描

1. 枚举未归桶区所有文件（排除 `.trash`/`__MACOSX`）。
2. 每篇读取：文件名 + 开头约 500 字。
3. 生成待分拣索引：编号/标题/一句话/建议桶（源目录物理归档）/信心度。

### 阶段 B · 信心度判定

- **高**：标题与开头指向同一明确主题，且该主题在源目录已有桶中有对应。
- **中**：可判但跨桶 → 按"主要教什么"定主桶，其余以标签覆盖。
- **低**：标题党/信息不足 → 列"待人工判断"，不自动归。

### 阶段 C · 按 policy 执行

- `suggest_table`：用户审表 → 确认后批量移动（移动 md 时保持 md+assets 同夹）→ 更新台账。
- `skip`：索引保留，文件不动。
- `handpick`：仅处理用户圈定篇目。
- 批量移动前生成 `操作前清单_<时间戳>.md`，移动后核对文件总数守恒。

---

## 7. 变更 / 更新同步流水线

### 7.1 检查项

| 检查对象 | 方法 |
|---|---|
| 源文件新增 | 重新 scan，与上次 manifest 比对（路径 + 修改时间） |
| 源文件内容变更 | 对比修改时间/大小；命中则标记对应笔记/单元待复核 |
| 源路径变动 | 笔记 `sources` 路径回读，失效路径标记并重新定位 |
| 笔记与规则不一致 | README/AGENTS/目录与实际比对 |
| 笔记孤立 | sources 全部失效或 flow 已废弃的笔记 |

### 7.2 处理

1. 输出"更新建议表"：对象/变更类型/建议动作/是否需确认。
2. 路径修复：可自动定位的更新引用（报告后改）；无法定位的列入待确认。
3. 内容变更：对应笔记/units 标 `stale: true`，重新提炼前不改写结论；旧 units 保留来源 hash，不物理删除。
4. 文档更新：文件目录可直接重建；README/AGENTS 修改走 L2。
5. 同步结果写入 `_meta/生成日志.md`。

---

## 8. 双向演化机制

### 8.1 工作流/环节的生长

- 新工作流：用户提出或 AI 从资料归纳（≥3 篇文档指向同一新 flow）→ 人工确认后建 `工作流/<flow>/`。
- 新环节：某 flow 下出现 ≥3 篇笔记无法归入现有 stage → 提议新环节，人工确认后建目录。
- substage 固定 5 值，不自由生长。

### 8.2 合并、拆分、废弃

| 动作 | 触发条件 | 流程 |
|---|---|---|
| 环节合并 | 两 stage 内容长期重叠 | 列方案 + 影响笔记 → 确认 → 移动并更新链接 |
| 环节拆分 | 单 stage 过大且内部出现 ≥2 清晰子主题 | 列子主题与归属 → 确认 → 拆分 |
| 工作流废弃 | 长期无新增、笔记全部失效 | 移入归档区（不删除），更新导航 |
| 标签回收 | 辅助标签长期 0 引用 | 降级为 candidate，不直接删 |

### 8.3 主题层与 units 演化

- topics 归并：近义主题累计 ≥3 篇 → AI 给候选，人工确认。
- units 冲突：同一 claim/procedure 多来源不一致 → 建 conflict，保留全部来源。
- units 合并：同 doc concept/relation 合并保留多 locator；跨 chunk procedure 按 steps.order 拼接。

---

## 9. 旧库迁移路径（加法，非重写）

旧库（标签驱动、notes 平铺）不用推倒重来，按以下顺序迁移：

1. **盘点现有笔记**：逐篇读 frontmatter 和正文，判断属于哪个 flow/stage/substage；
   - 判定不了的进 `99_收件箱`，不硬判。
2. **移动到工作流目录**：
   - 移到 `工作流/<flow>/<n>_<stage>/`；
   - 移动前生成清单，移动后核对文件守恒、链接更新。
3. **补齐来源笔记**：对每篇原文档建立 `素材库/_来源地图/` 来源笔记，指向已迁移的原子笔记。
4. **生成总览**：跑 `build_flows.py` 生成 `_流程.md` 和 `_总览.md`。
5. **六维标签不动**：继续支持跨工作流检索，不强制重打。
6. **建笔记地图**：跑 `search_index.py build`，SQLite 索引（`_meta/search.db`）即记录每篇笔记 ↔ flow/stage/substage；笔记的 `sources` 路径仍在笔记 frontmatter 里，通过 path 反查得到。无需额外 `_meta/笔记地图.json`。
7. 旧的 `notes/` 目录在全部迁移完成、用户确认后再清空，不提前删除。

**原则：加法，不是重写；每步可回退；移动/删除必须人工确认。**

---

## 10. 各 Step 验收清单

**标注口径**：标 `[verify Cx]` / `[progress]` / `[check_hooks]` / `[check_verbatim_lite]` /
`[validate_extraction]` 的项**有机器对应、可自动验**；标 `[人工]` 的项**须人判断**，不得因为"脚本跑绿了"
就免检；标 `[xxx 打印]` 的项**只有输出、没有校验**（打印 ≠ 判据，仍需人看一眼）。
注明「**承诺超实现**」的行是**实现缺口**（文档承诺了、脚本没做），不是验收缺口。**一条都没删，只做了拆分。**

| Step | 验收项 | 机器对应 |
|---|---|---|
| Step 1 | manifest 可解析 | `[scan_sources]`（写出即 JSON；解析失败在 `build_profile` 读取时抛错） |
| Step 1 | 文件计数与磁盘一致 | `[人工]`（`scan_sources` 只**自述**计数，没有第二次磁盘核对） |
| Step 1 | 配对检测完整 | `[scan_sources 打印]`＋`[人工]`（打印孤儿 PDF / 无精华妙记 / 孤儿 srt 三类，完整性无人判） |
| Step 2 | answers 覆盖题本 | `[人工]`（无脚本比对题本与 `answers.json` 的键集） |
| Step 2 | null 项已标记 | `[人工]`（`build_profile` 对 null 走推断，**不把 null 清单单列**） |
| Step 2 | 工作流/环节字段已记录 | `[build_profile 打印]`＋`[人工]` |
| Step 3 | profile 字段完整 | `[人工]`（无 schema 校验） |
| Step 3 | config 含 flows/stages/substages/目录/标签/默认项 | `[render_config 打印]`（目录一致性由 Step 5 的 `C2` 兜） |
| Step 3 | 冲突全部记录 | `[render_config 打印]`＋`[人工]`（只报**条数**，内容要人复核） |
| Step 4 | 用户已看到工作流目录树、环节顺序、粒度、辅助层、默认项 | `[人工]` |
| Step 4 | 获得明确确认 | `[人工]` |
| Step 5 | 实际目录与 config 一致 | `[verify C2]` |
| Step 5 | 工作流/环节目录已建 | `[verify C2]` |
| Step 5 | 无方案外文件 | `[人工]`（**承诺超实现**：§11 写"无多余/缺失"，`C2` 代码只算 `missing_dirs`） |
| Step 6 | 5 篇样板原子笔记可打开 | `[人工]`（`C4` 只验 frontmatter，"可打开"是主观） |
| Step 6 | flow/stage/substage frontmatter 完整 | `[verify C4]`＋`[verify C11]`（位置与字段一致） |
| Step 6 | sources 可达 | `[verify C5]` |
| Step 6 | 来源笔记已建 | `[人工]`（无校验；`C10` 只判 `[[ ]]` 目标存在，`素材库/_来源地图` 存在性无人查） |
| Step 6 | `_流程.md`/`_总览.md` 已生成 | `[人工]`（**承诺超实现**：§11 承诺 100%，C1–C15 里没有对应项） |
| Step 6 | coverage_audit 回填 | `[人工]`；units 开启时 `[validate_extraction]`（**它是唯一读者，只覆盖 units 路径**） |
| Step 6 | 开 units 时 validate 通过 | `[validate_extraction]`（units 关闭 → **N/A**，不要跑它） |
| Step 6 | **可引名单已刷新，正文 `[[ ]]` 逐条能对应到"正文确实引用了那篇"（无链、孤岛均合法，不作为缺陷项）** | `[人工]`（`08` §3.6 规约；`C10` 只判目标存在、不判"确实引用"） |
| Step 6 | verify 全绿 | `[verify C1–C15]` |
| Step 7 | 高价值块处理率 100% | `[progress 读数]`＋`[人工判定]`（progress 只给 done/partial/todo 与"已抽 N / 未抽 M"，**不判百分比**；**这条不进 `--gate`**） |
| Step 7 | inbox 占比 ≤20%（小批次 <10 块人工判断） | `[人工]`（无脚本；`PROGRESS` 模板只留填空） |
| Step 7 | 每批重跑 build_flows | `[人工]`（`_流程.md` 与笔记是否一致不查；audit A5 只管原文变更） |
| Step 7 | validate_extraction 通过 | `[validate_extraction]`；units 关闭 → **N/A**，替身 `[check_verbatim_lite]`（warn only） |
| Step 7 | 抽检条目通过率 ≥95% | `[人工]`（`_meta/抽检记录.md` 无校验） |
| Step 7 | 失败已入问题资产库 | `[verify C8]`＋`[人工]`（`C8` **只验文件存在**，空文件照 PASS） |
| Step 7 | **结构性不一致归零**（本轮新增） | `[progress --gate]`（唯一显式门禁；判**本视图内**的 `ghost_locator` / `unmapped_source`，默认关） |

---

## 11. verify.py 检查项

| 级别 | 检查项 | 通过标准 |
|---|---|---|
| 结构 | 必备文件存在（README/AGENTS/问题资产库/导航） | 全部存在 |
| 结构 | 工作流/环节目录与 config 一致 | 无多余/缺失 |
| 主轴 | 每篇原子笔记含非空 flow/stage/substage | 100%（仅检查 `工作流/` 下，不检查来源笔记） |
| 主轴 | 笔记物理位置与 frontmatter 的 flow/stage 一致 | 100%（仅检查原子笔记） |
| 来源 | **C5**：样板源路径可达 **+ 全库每篇原子笔记逐篇 `sources`** | sources 非空且路径存在 → PASS；**有空或缺 → FAIL**；拿不到 `source_root`（不带 `--config`）时只验非空，可达性记 **WARN** 不硬 fail。路径基准两种都认：`source_root/<rel>` 与 `<kb>/<rel>`（模板写前者、本篇 §2.3 示例写后者，只认一种会把合法笔记整批判红） |
| 内容 | **C9**：笔记含"资料/归纳/推断"三段分标 | 100%；**缺任一即 FAIL**（以前两分支都返回 warn，等于从来没拦住过；现在对齐本节末尾那句"error 未清零不得宣布完成"） |
| 信心 | **C15**：原子笔记的 `confidence` | low / 缺失 / 值域非法 → **WARN**，列出篇目并提示按 `08` §3 硬约束 5 进 `99_收件箱`。**这是流程约束不是门禁，绝不 FAIL**——是否挪走去留由人定 |
| 总览 | 每个 flow 有 `_流程.md`、每个 stage 有 `_总览.md` | 100% |
| 标签 | 辅助标签均在受控词表或标记 candidate | 100% |
| 链接 | **C10**：`[[ ]]` 双链目标存在 | 失效链接列入报告（warn，不 fail）。**两个口径分家**（`verify.py` 的 `SCAN_DIRS` / `STEM_SOURCE_DIRS`）：被检内容仍只扫 `工作流/`；**目标解析全集扩到 `工作流/` + `素材库/_来源地图/`**——模板「关联」节要求留 `来源：[[来源笔记链接]]`（`08` §3.6.5 明写"来源指向是真引用"），只收 `工作流/` 会把这条合法链判成失效链（发现 28）。**判据本身一字未改**：仍只判"目标存在"，改的是在哪儿找目标；来源笔记**自己正文里的出链**仍不在被检范围（残留部分见发现 25）。**追加档（乙批 B7）**：`config.link_target_dirs`（列表）可在这两个目录之后**追加**目标目录，**只有 config 一档、无 CLI 开关**；第一段仍跟 `notes_dir`，第二段 `素材库/_来源地图` 是字面常量，**config 覆盖不了也删不掉**（`P12-dir⑨` 钉着它） |
| 安全 | **C14 源目录只读**：对 `_meta/source_snapshot.json` 基线比 sha256（口径来自 `scan_sources.TEXT_BODY_EXT` = md/pdf/txt/srt），媒体只比数量 | 删除/内容变 → **FAIL**；新增未纳管文档、媒体计数变化 → **WARN**（不是 FAIL，见下）；无基线 / 基线路径不存在 / 无源目录可解析 → **WARN**；全部一致 → PASS。**FAIL 时顺带出 stale 工单**（见 11.1 末） |
| 安全 | 不比 mtime、不做实时监控、**不自动重建基线** | 变化只在跑 verify 时抓；基线只能 `--snapshot-source` 显式建 |
| 检索 | `_meta/search.db` 的 `meta.schema_version` 与脚本一致（C12） | 相等；旧索引须 `--rebuild` |
| 检索 | 索引笔记数 > 0（C12） | **0 篇不能 PASS** |
| 检索 | 索引 `meta.notes_indexed` = 磁盘实际笔记数（C12，目录口径 `工作流`） | 不等即 FAIL，须 `--rebuild` |
| 主题 | `_meta/topics.json` 主题数 > 0（C13） | **0 个主题不能 PASS** |
| 逐字（units-off） | **`check_verbatim_lite.py`**：units 关闭路径的正文数值/命令逐字 | **「多」warn＝主判据**（笔记有、本篇引用的块里没有）；**「缺」warn＝参考信号**（主块有、笔记没有 → 1:N 的拆篇候选）。**warn only、exit 0，不作门禁**；units 开着（`_meta/units.jsonl` 有行）时自动让位 `validate_extraction.py` 并明写"未做任何校验"；笔记目录不存在 / 0 篇 → **exit 1**，绝不打印通过。豁免按 `08` §3.1 前缀白名单（只免 `作者未提、我的推论：`）；`not_checked` 逐条列出它检不了什么 |

verify 输出机器可读 JSON + 人读报告；任何 error 级项未清零，不得进入批量/宣布完成。
C12/C13 是 Step 6 之后的硬门禁（索引与主题层必须真实产出且非空）；C12 另比对索引自述篇数与磁盘实际篇数——**笔记增删后忘了 `--rebuild` 会在这里暴露**，不会因为索引还留着旧数据就 PASS。

**空库不误报（按磁盘笔记数判，不是按索引篇数判）**：磁盘 **0 篇笔记**＝还停在 Step 1–5，没有内容可索引，C12/C13 直接 PASS（消息注明「空库…Step 6 产出笔记后须跑 build」），**不需要任何 flag**。磁盘**有**笔记却没索引/主题层＝忘了 build，照旧 FAIL —— 这条门禁一点没松，判据是「磁盘 0 篇」而不是「索引 0 篇」，两者不能混：按索引篇数判会连「忘了 rebuild」一起放过。

Step 1–5 之外的场景（有笔记但想临时跳过这两项）仍可用 `verify.py --allow-empty-index` 降级为 warn。

> ⚠️ `--allow-empty-index` **不跳过**比对，只是把 C12/C13 的 fail 降级为 warn——等于绕过这两道门禁（含 C12 的磁盘篇数比对）。**该 flag 仅供探针/CI 使用，交付验收与生产环境不要开**，否则「忘了 rebuild」会被静默放过。

### 11.1 C14 源目录只读（兑现 AGENTS 的承诺）

**实现依据**：每个 KB 的 `AGENTS.md` 都写了「源目录所有文件只读：不删、不改、不重命名」和
「批量任务前重新扫描源目录，**比对新增/变更/路径失效**」——这两句过去**没有任何脚本兑现**，
C14 就是它的载体。

```
python scripts/verify.py --kb <KB> --config <工作目录>/config.json --source-root <源资料目录> --snapshot-source   # 建基线
python scripts/verify.py --kb <KB> --config <工作目录>/config.json                                                  # 常规自检，含 C14 比对
```

- **源目录解析两档**：`--source-root` > `config.source_root`（`scan_sources` 写的是绝对路径）。
  两档都没有 → **warn 跳过**，不 fail——Step 1–5 尚无 config 时不该挡住自检。
  *没有第三档*：KB 内的 `99_收件箱`/`素材库/` 装的是**笔记**不是源资料，拿它们当源目录会把日常写笔记误判成事故。
- **基线格式**：`_meta/source_snapshot.json` = `created_at`（带时区 ISO）+ `source_root`（绝对）+
  **`text_body_ext`（建线时用的资料文档清单，排序快照）** + `files{相对路径: {size, sha256}}` +
  `media_counts{分组: 数量}`。
- **清单口径比对（A4）**：`text_body_ext` 与当前 `DOC_EXT` 不一致（含旧基线**没这个键**的情况）→
  **warn**，文案「基线是旧清单口径（基线 N 类 → 当前 12 类），需重跑 `--snapshot-source` 重建后才可比」，
  并且**只赦免 `added`**（那些文件是清单变宽的后果，不是有人动了源）。
  `deleted` / `modified` / `unreadable` / 媒体计数变化**一律照旧判**，该 FAIL 还是 FAIL——
  **赦免不能变成放松校验**。口径一致时 `added` 仍是「新增未纳管」warn，两类文案可区分。
- **判定**：
  | 变化 | 结果 | 理由 |
  |---|---|---|
  | 基线有、现状无 | **FAIL**「源文件被删除」 | 违反只读 |
  | 基线有、现状有、sha256 不同 | **FAIL**「源文件被修改」 | 违反只读 |
  | 现状多出资料文档 | **WARN**「新增 N 个未纳管，请重建基线并走 intake」 | 用户补下新资料是**正常动作**；判红会让每次补资料都卡门禁、逼人先重建基线 |
  | 现状多出媒体 | **WARN**，只报计数（`images 3→5`） | 媒体不逐篇哈希，避免大库跑不动 |
  | 只改 mtime、内容不变 | **PASS** | 明确不比 mtime；复制/同步/挪盘造成的时间戳变化不是改动 |
  | 无基线 / 基线路径不存在 | **WARN** | 换机器、挪盘是常态，不是事故；判红只会让人不信这个门禁 |
- **基线永不自动重建**：`verify` 常规跑绝不写基线。补完新资料要**人显式**再跑一次 `--snapshot-source`——
  这一步是"我知道源目录变了，并且我接受它"的确认动作，脚本不能替人做。
  `--snapshot-source` 但解析不到源目录 / 路径不存在 → **直接非 0 退出**，不会 warn 了事（否则你以为基线已经在了）。

> 同名覆盖不在"新增"这一档：**同名 + 内容变** 已被 sha256 那条抓住（FAIL）；"新增"指的是基线里没有的路径。

**C14 FAIL 时顺带出 stale 工单**（`AGENTS §7` 那句「内容变更对应笔记标 `stale: true`」的下半段）：
拿着被改/被删的源文件清单去扫全库原子笔记的 `sources`，命中即列出。

```
[FAIL] C14 源目录只读（对基线） — 源文件被修改 1 个：选品方法.md。源目录按规则只读；1 篇笔记依赖已变更的源资料（工单见下）
...
[C14 工单] 以下笔记依赖已变更源资料，请确认是否标 stale: true
  - 工作流/视频制作/1_找素材/选品四象限判需求与竞争.md
[C14 工单] 本工单只列不改：verify 不写任何笔记，stale 由人确认后落。
```

- **只列不写**：verify 绝不碰任何笔记文件（P8 有断言用 mtime 差分钉这条）；`stale` 是否要标、标哪几篇，由人判断。
- 命中口径：`sources` 的相对路径全等，或文件名（basename）相同——后者兜住模板写 `选品.md`、源目录里叫 `子目录/选品.md` 的写法差异。
- JSON 报告里是 `c14_stale_ticket: [...]`，机器可直接取。

### 11.2 verify 的写范围（边界，别误读）

- verify **只写 `_meta/` 下的两样东西**：`--out` 指定的 JSON 报告、`--snapshot-source` 写的源目录基线。
- **verify 没有 `--fix` 这个 flag**（`--help` 只有 `--kb / --config / --out / --source-root / --snapshot-source / --allow-empty-index`）。
  它**永不写笔记、units、topics.json、检索索引，更不碰源资料**——"修"永远是执行 AI 的活，脚本只报告。

### 11.3 verify 与 validate_extraction 分工

- **verify.py**：结构 / 主轴一致性 / **来源可达（C5：样板 + 全库逐篇 sources）** / 三段分标（C9，缺即 FAIL） / **信心与归属（C15，只 WARN）** / 双链 / 安全（C14 + stale 工单）。
- **check_verbatim_lite.py**：**units 关闭路径**的数值/命令逐字替身（warn only、exit 0）。
  参照系是"本篇引用落在的那些块"，不是整篇文件——实测用整篇会漏检（源里别处恰有同一个数），
  用贴紧的 quote 区间会成片误报（笔记合法复述本块里的其它数字）。块边界复用 `doc_map.split_chunks()`。
- **validate_extraction.py**：quote 严格子串、数值/命令/代码逐字不归一、procedure 步骤连续、conflict 双源、high 必有证据、高价值块无漏抽、**合并留痕的三种可检形态**（见 `08` 第 8 节第 7 项）。
- 两者都跑，任一 error 未清零不放行：**两个脚本现在都真用退出码**——verify 有 fail 即 exit 1；
  validate 有错 exit 1，且 **`units.jsonl` 缺失/0 条直接 exit 1 并拒绝打印「通过」**（不再空跑报绿）。
- ⚠️ validate 是 **units 路径的门禁**：units 是可选辅助层（`08` 第 11 节），**没开 units 的库不要拿它的红绿当放行依据**。
- 能力边界要认：validate 检不了"合并前声明条数"（units 不记 alias），verify 的 `--allow-empty-index` 会绕过 C12/C13 两道门禁——两者都不假装全检。

---

## 12. 进度与续跑（progress.py）

**定位**：只读的**进度派生器**。不新增账本、不要求人维护任何字段，只把库里已有的两样东西
（`工作流/` 笔记的 `source_locator` + `_meta/doc_maps.jsonl` 的块清单）对起来，反算
"哪些高价值块已成篇、哪些还没有、下一个该抽谁"。**默认不是门禁**：两类不一致全是 warn 级，
退出码只区分「跑完了」(0) 与「输入不可用」(1：笔记目录不存在 / doc_maps 缺失或 0 行 / 笔记 0 篇)。
**唯一的显式开关是 `--gate`**（默认关；开了之后"本视图内有不一致"才 exit 1）——见 §12.5。

**为什么是派生而不是账本**：账本要人手工回填就会漂（发现 17）。笔记里的定位符本身就是
"这块抽过了"的天然凭证，且已被 C5 与逐字校验间接检查过——再加一份手工账本只是**多一个会漂的东西**。

```
python scripts/progress.py --notes-dir <KB>/工作流                    # 人读
python scripts/progress.py --notes-dir <KB>/工作流 --format json      # 机器读（逐字节确定）
python scripts/progress.py --notes-dir <KB>/工作流 --emit-todo        # 只吐一行续跑起点
python scripts/progress.py --notes-dir <KB>/工作流 --path-prefix 04_  # 只缩小视图
python scripts/progress.py --notes-dir <KB>/工作流 --gate             # 显式门禁（默认关）
```

### 12.1 输出 schema（`progress-v1`，字段固定）

```json
{ "schema": "progress-v1", "doc_maps": "…", "notes_dir": "…", "path_prefix": "",
  "summary": { "total_docs": 295, "done_docs": 1, "partial_docs": 0, "todo_docs": 294,
               "no_hv_docs": 0, "total_chunks": 12005, "total_high_value_chunks": 5226,
               "done_chunks": 8, "undone_high_value_chunks": 5218,
               "notes_total": 11, "inconsistencies": 0 },
  "next_todo": { "doc": "…", "chunk_id": "doc-…-1",
                 "reason": "高价值块未成篇｜块长 1089 字｜density 0.8｜特征 numbers,link,…" },
  "docs": [ { "path": "…", "doc_id": "…", "total_chunks": 13, "high_value_chunks": 8,
              "done_chunks": 8, "status": "done", "note_paths": ["…"] } ],
  "inconsistencies": [ { "type": "…", "doc": "…", "chunk_id": "…", "note": "…", "msg": "…" } ] }
```

三条口径写死在这里：
- **进度只在高价值块上算**（`done / partial / todo`）；`no_hv` 单列一档——没有高价值块的文档
  永远做不到 done，不给这一档它会被当成长期欠债。
- **分母两栏都给**：只报 `total_chunks` 会误导估工，只报高价值块会丢掉块结构。
- **确定性**：`sort_keys=True` + `ensure_ascii=False`，`docs` 按 path 排、`note_paths` 与
  `inconsistencies` 也排序 → 同一输入两次 `--format json` **逐字节一致**（P10 钉住）。

### 12.2 两类不一致

| 类型 | 含义 | P10 怎么造 |
|---|---|---|
| `ghost_locator` | 定位符 `#char=a-b` 的 `a` 落不进该文档任何块（源被改过 / 偏移写错 / 旧笔记没 locator） | 把某篇的 char 改成 `999999-999999` |
| `unmapped_source` | 笔记 `sources` 指的文档**不在 doc_maps 里** → doc_map 过期、新补资料没重建 | 改 `sources` 指向一个没进地图的路径 |

> **`coverage.chunks_processed` / `high_value_done` 是 `doc_map.py` 生成时的快照，不由任何脚本维护，
> progress 也不读；进度以 `progress.py` 为准。** 这两个字段的状态是**已作废**，不是"待回填"：
> 留在输出 schema 里只是为了不动 `doc_map.py` 的字段结构（schema 不动），任何脚本、任何文档都不得
> 再把它当进度依据，也不得再打印"下一步回填"。**字段已作废 ≠ 字段删除。**

> **为什么连"声称 × 派生"的交叉验证都不做**（发现 29，也是发现 17 的根因）：`doc_map.py` 的 chunk
> 记录里**没有 status 字段**（实测只有 `chunk_id / heading / char_start / char_end / char_len /`
> `overlap_start / features / density / high_value / candidate_topics / skip_reason`），声称粒度却只
> 存在于**文档级** `coverage`（真库实测：`status` 恒 `mapped`、`high_value_done` 恒 false、
> `chunks_processed` 恒 0）。**任何块级声称都无法回填到文档级计数器** → 声称与派生交叉比对只会
> 产出"结构性必然矛盾"的噪声（原来的 `claimed_but_empty` / `claim_understated` 两类就是这么来的：
> 一个 295 篇全 0 的字段，撞上从笔记反推的真实进度，怎么报都是假警）。整类删除、不保留开关。
> **别照着"chunk 有 status"去写判据，那是幻觉字段。** 从笔记反推是**唯一可信进度源**。

### 12.3 匹配口径（不写清必踩）

1. **join key = 笔记 `sources[0]` ↔ `doc_maps.path`**（都是相对源根的路径）；`doc_id` 不做 join key。
2. **`§标题` 不参与定位**，只有 `#char=起-止` 用来落块。真库 11 篇的 § 段写的都是**文档标题**，
   而 `chunk.heading` 只有第 0 块恰好等于文档标题——按 § 标题匹配会把 100% 的合法定位符判成 ghost。
   § 段给人看，char 给机器用。
3. `source_locator` 是 block 列表，必须走 `fm_list` 风格解析，**不能用 `parse_frontmatter`**（§2.3）。

### 12.4 断点恢复工作流（人决定范围，脚本报事实）

```
补完一批笔记 →（新补过资料就）重跑
    python scripts/doc_map.py --source-root <源资料目录> --out <KB>/_meta/doc_maps.jsonl
             → python scripts/progress.py --notes-dir <KB>/工作流 --emit-todo \
               --path-prefix <当前批次前缀> [--gate]
```
- `--path-prefix` **只缩小视图**，不传时与全局一致（默认不过滤）。脚本只报"范围内下一个是谁"，
  **不替你决定该做哪个批次**——不做自动续跑。
- 加 `--gate` 才判红（默认关）。**它与 `--path-prefix` 同口径**：判的是**范围内**的不一致，
  范围外的不拦——主动缩小视图的代价，详见 §12.5。
- 传了前缀时 markdown 把**全库与范围内两份计数都给**：只给范围内的会伪装成全库，
  只给全库的会让人以为过滤器没生效。
- `partial`（半抽）的文档单独成段列出——最危险的一档：整体看着在推进，实际在漏块。
- 换机器 / 挪盘后 `_meta/doc_maps.jsonl` 不在？重跑一次
  `python scripts/doc_map.py --source-root <源资料目录> --out <KB>/_meta/doc_maps.jsonl` 即可——实测确定性：
  同一源目录两次输出 sha256 逐字节一致（真库 295 篇 / 3,803,680B 那份）。

### 12.5 `--gate`：默认关的显式门禁

- **判据**：`inconsistencies` 非空 → `exit 1`；空 → `exit 0`。不加 `--gate` 时**行为与从前逐字节一致**
  （P11-②⑥ 钉住；真库实测加/不加 gate 的 stdout 同为 591B、一字不差，且与加 gate 之前那轮的输出也相同）。
- **只看结构性错误**：定位符落不进块（`ghost_locator`）、笔记指的文档不在地图上（`unmapped_source`）。
  **不是进度百分比**——全库 5,226 块只抽了 8 块也照样绿，"抽了多少"永远不由它判。
- **判的是本视图**：给了 `--path-prefix` 就只判范围内的不一致。**代价必须写清**：范围外的真实不一致
  **不触发 gate**——这是主动缩小视图的代价，用的人须知（P11-⑧ 钉：ghost 在 docB 时
  `--path-prefix docA` 判绿、`docB` 判红）。
- **不动 stdout**：gate 的话只走 **stderr**（`GATE FAIL：全库 N 条不一致（类型 …）——判据是结构性错误，
  不是百分比` / `GATE OK：… 0 条`），所以 `--format json` 的消费方与 CI 的 stdout 解析不受污染，
  **退出码才是信号**。
- **可与 `--emit-todo` 叠加**：一次拿到"下一个是谁 + 这一批能不能收"（stdout 仍只有那一行起点）。
- **输入守卫优先**：doc_maps 缺失 / 0 行、笔记目录不存在时，仍是守卫的 rc=1 与守卫文案，
  **不打印 GATE 文案**——"没读到东西"和"读到了脏东西"是两回事（P11-⑨ 钉）。
- **门禁也不许偷偷写**：跑完四种 gate 组合后整库 `.md` 与 `doc_maps.jsonl` 的 mtime+内容一项都没变
  （P11-⑪ 钉）。

### 12.6 明确不做

**默认不做阶段门禁**（`--gate` 是唯一的显式开关，且只判"有没有结构性错误"这一档；
**自动拦 / 每批强制判绿仍不做**——要不要开 gate 由人或 CI 显式决定）；
**`--gate` 只吃 progress 自己的两类不一致**：`check_verbatim_lite` 的 warn、`check_hooks` 的 warn、
audit 的 A1/A3、inbox 占比、高价值块处理率百分比**一概不进 gate**（它们是百分比或启发式判据）；
不做自动续跑、不决定抽谁；不读 `coverage_audit.jsonl`（**它记录块级跳过原因；进度事实以
`progress.py` 反推为准，两者冲突时 progress 赢、`coverage_audit` 标过期**）；
不改 `doc_map.py` 任何字段；**不写任何文件**——
跑完前后整库 `.md` 与 `doc_maps.jsonl` 的内容 + mtime 必须逐字节不变（P10 钉住这条）。
