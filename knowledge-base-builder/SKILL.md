---
name: knowledge-base-builder
description: 把本地原始资料（Markdown / 妙记逐字稿 / PDF / 网页剪藏）按「工作流 → 环节」建成个人知识库：问卷定制目录、高价值块拆原子笔记、环节总览、多维标签与检索。用于从零建或重建第二大脑、补齐工作流目录与原子笔记、按环节一键拉取知识。不用于单纯下载飞书文档（用 feishu-doc-copy）、单篇摘要、没有本地资料的纯概念问答。
---

# Knowledge Base Builder · 工作流驱动知识库构建器

## 这个 Skill 做什么

把一批"已下载到本地、但未经提炼"的原始资料，通过**问卷引导 → 工作流/环节建模 → 高价值块原子笔记 → 环节总览 → 样板闭环 → 质量门禁 → 批量入库**，建成一个**物理层直接体现工作流、逻辑层可按环节/子分组聚合、辅助层带标签与知识单元**的个人知识库。

**主轴是工作流（flow）→ 环节（stage）→ 子分组（substage）**，不是标签。六维标签和 units 保留为辅助检索层，不决定目录。

**运行环境**：`scripts/*.py` 只用标准库、零第三方依赖（**唯一例外**：`convert_sources.py` 的转换分派器，
是可选依赖、按需 import，不装就整格退回"登记 + 不深抽"，其余脚本一律不吃第三方包——清单见文末「可选依赖」一节），
但**要求 Python ≥ 3.7**——每个脚本入口用
`sys.stdout/sys.stderr.reconfigure(encoding="utf-8", errors="replace")` 把两条流钉成 UTF-8（3.7 起才有
`reconfigure`），否则 Windows GBK 控制台下中文与 ✅/❌ 会抛 `UnicodeEncodeError`。低版本上跑会直接
`AttributeError: 'TextIOWrapper' object has no attribute 'reconfigure'`，这是有意的下限，不做兼容分支。

执行铁律（不可跳过）：

1. **先只读盘点，再动手**——没看过资料不建模。
2. **先出方案，用户确认后才写文件**——AI 不直接生成或搬运。
3. **原始资料只读、只存一份**——知识层放原子笔记与路径引用，不复制原文正文。
4. **物理层即工作流**——打开文件夹就能看到工作流和环节；环节是物理目录，不是标签组合视图。
5. **笔记按语义单元原子化**——高价值块只是**输入容器**，不定义笔记粒度；每块按语义单元拆 N 篇（N≥1），每篇对应一个可独立回答的问题/结论，归到 1 个主环节。一篇文档讲 3 个环节就出 ≥3 篇。
6. **每个环节有 `_总览.md`**——子技巧/案例/工具/坑分组，20 篇笔记不再平铺。
7. **先跑 5 篇样板闭环 + 质量门禁达标，再批量**。

## 执行总览（8 步状态机）

```
Step 1  只读盘点       scan_sources.py → sources_manifest.json
Step 2  引导问卷       intake_questionnaire.md（工作流/环节/粒度/辅助层）→ answers.json
Step 3  算配置         build_profile.py + render_config.py（融合 taxonomy.json）→ config.json
Step 4  方案评审       展示工作流树 + 环节/子分组 + 笔记粒度 + 辅助层 + 默认项，用户确认
Step 5  生成骨架       render_templates.py（工作流/环节目录 + 流程/总览/原子笔记/来源模板）
Step 6  两阶段深抽     doc_map.py 出文档地图(章节/密度/高价值块) → tag_documents.py 辅助标签
                       → 刷新可引名单 → AI 读高价值块、按语义单元写原子笔记(flow/stage/substage frontmatter)
                       → 来源笔记 + 回填 coverage_audit → build_flows → build_topics → search build → verify
Step 7  批量入库        高价值块处理率 100%；每批重跑 build_flows；validate 必跑；抽检 <95% 回滚
                       → 分批：可引名单→深抽→原子笔记→build_flows→build_topics→索引→verify
Step 8  使用与维护      按 flow/stage/substage 一键拉取、关键词/主题检索、环节总览更新
                       → 工作流/环节/标签/units 演化、stale 处理、更新同步
```

各步进入条件、动作、产出与验收见 `references/04_pipeline.md`；工作流与环节模型见 `references/09_workflow_model.md`；多属性辅助模型见 `references/05_multidim_model.md`；内容主题/units 见 `references/08_topics_pipeline_units.md`。

## 核心概念

### 三层结构

**第一层：物理层——按工作流 → 环节分目录**
```
工作流/
└── <flow>/
    ├── _流程.md              ← 流程总览（环节顺序 + 关键 SOP）
    ├── 1_<stage>/
    │   ├── _总览.md          ← 环节索引（子技巧/案例/工具/坑）
    │   ├── <原子笔记>.md
    │   └── ...
    └── 2_<stage>/
```

**第二层：逻辑层——三个视图**
- 流程视图：`工作流/<flow>/_流程.md`
- 环节视图：`工作流/<flow>/<stage>/_总览.md`
- 概念索引：`概念索引/`（跨工作流的概念、SOP、关系，units 产物）

**第三层：辅助层——六维标签 + units + 主题地图**
- 六维标签（domains/forms/tools/types/projects/sources）：跨工作流检索，不决定目录
- units：放 `概念索引/`，表达流程步骤/概念关系，不表达"笔记属于哪个环节"
- 主题地图：跨工作流的主题聚合视图

### 笔记粒度规则

**高价值块 = 输入容器；笔记粒度 = 语义单元（一个可独立回答的问题/结论）。每块拆 N 篇（N≥1）→ 每篇归到 1 个主环节。**
- doc_map.py 已切 chunk、标知识密度和高价值块
- 每个高价值块按语义单元产出 N 篇原子笔记（N≥1），frontmatter 带 flow/stage/substage
- 文档级产出 1 篇"来源笔记"，放 `素材库/_来源地图/`，指向所有衍生原子笔记
- 一篇妙记讲 3 个环节 → 3 篇原子笔记 + 1 篇来源笔记

### 环节内子分组（substage，固定 5 值）

每个环节的笔记按 5 类分组，在 `_总览.md` 里聚合：
- `总览`（环节本身的方法论）
- `子技巧`（可独立操作的具体技巧）
- `案例`（真实项目/复盘）
- `工具`（工具/资源/提示词）
- `坑`（注意事项/失败教训）

## 逐步操作

**两个目录参数的口径（易错，先记这两句）**：

| 写法 | 含义 | 谁用它 |
|---|---|---|
| `--notes-dir <路径>` | **目录本身**（相对 cwd 或绝对路径）；KB 根＝它的父目录，除非再给 `--kb` | `progress` / `check_hooks` / `check_verbatim_lite` / `backfill_hooks` / `audit` |
| `--notes <名字>` | **相对 `--kb` 的目录名**，默认 `工作流`（可由 `config.notes_dir` 提供） | `verify` / `build_flows` / `build_topics` / `search_index` |

一句话记法：**用 `--kb` 的那批脚本传"名字"，用 `--notes-dir` 的那批传"路径"**；两边都支持
`--kb`（缺省＝笔记目录父目录），优先级统一为 **CLI > config（`kb_root`/`notes_dir`）> 兜底**。
路径键的完整口径见 `references/03_rules_engine.md` 第 4 节末尾。

### Step 1 · 只读盘点

- 向用户确认**源资料目录**与**知识库目标目录**（目标目录由用户指定，不要建到源资料目录内部）。
- 运行：
  ```
  python scripts/scan_sources.py --source <源资料目录> --out <工作目录>/sources_manifest.json
  ```
- 产出 md / pdf / txt / srt + 可直读的其他正文（vtt/ass/html/htm/rtf）+ 需转换的正文（docx/epub/odt）
  + 媒体 / 压缩包 / 其他清单与统计，自动做配对检测。**后两类只登记、受只读保护，不进深抽**（`doc_map` 只吃 `.md`）。
- 源文件可在根目录或任意子目录，脚本不要求固定层级。
- 通读结果，识别正文、附属物、孤儿 PDF、无精华逐字稿。

### Step 2 · 引导问卷

- 打开 `intake_questionnaire.md`，一次展示全部题目（允许"你建议"兜底）。
- 重点确认：工作流清单（Q1）、每个工作流的环节（Q2）、笔记粒度（Q6）、辅助层（Q14 六维标签/主题层、Q16 units）。
- 保存为 `<工作目录>/answers.json`。漏答记 `null`，由 Step 3 兜底，并在方案中**显式标注默认项**。

### Step 3 · 算配置

- 运行：
  ```
  python scripts/build_profile.py --answers <工作目录>/answers.json --out <工作目录>/profile.json
  python scripts/render_config.py --profile <工作目录>/profile.json --manifest <工作目录>/sources_manifest.json --taxonomy assets/taxonomy/taxonomy.json --out <工作目录>/config.json
  ```
- 配置含：工作流清单与每个 flow 的 stages、substage 启用、目录骨架（工作流/概念索引/素材库/导航/收件箱）、原子笔记模板档、AGENTS 规则档、六维辅助标签、来源笔记策略、特殊资料处理、冲突仲裁、兜底清单，以及 extraction 配置（units 开关、confidence 阈值、locator 格式、切块参数）。
- 权重/仲裁/兜底逻辑见 `references/03_rules_engine.md`。

### Step 4 · 方案评审

- 若问卷 Q1 为空（用户选"你建议"）：执行 AI 先读 Step 1 扫描结果，归纳候选工作流写入 `profile.json` 的 `flows_candidates`，再进入评审。
- 用 `references/09_workflow_model.md` 第 5 节的展示格式输出**定制方案**：
  - 工作流目录树（flow → stage → substage）
  - 每个工作流的环节顺序与关键 SOP
  - 笔记粒度（按语义单元/粗粒度/你建议）
  - 辅助层（六维标签、units、主题地图）开关
  - 将生成文件 + 样板原文选择 + 所有默认项
- 用户提意见 → 改 answers/profile/config → 重新展示，直到明确确认。未确认前不在目标目录写任何文件。

### Step 5 · 生成骨架

- 用户确认后运行：
  ```
  python scripts/render_templates.py --config <工作目录>/config.json --templates assets/templates --target <知识库目标目录>
  ```
- 生成 README、AGENTS、工作流目录（每个 flow 的 `_流程.md`、每个 stage 的 `_总览.md`）、概念索引、素材库/_来源地图、导航、收件箱、PROGRESS、问题资产库。
- **建源目录基线（骨架生成后立刻做，一次性）**：
  ```
  python scripts/verify.py --kb <知识库目标目录> --config <工作目录>/config.json --snapshot-source
  ```
  写 `_meta/source_snapshot.json`（资料文档逐篇 sha256 + 媒体计数）。此后**任何** verify 都会比对——
  源文件被改/被删即 `C14 FAIL`。基线**永不自动重建**：用户正常补下新资料后，先确认这批要走 intake，
  再显式重跑一次上面这条命令。实现依据与判定分档见 `references/04_pipeline.md` 第 11.1 节。
- 模板槽位与填充规则见 `assets/templates/` 各文件头部注释。

### Step 6 · 两阶段深抽与样板闭环

1. **先出文档地图**（不要逐块全量深抽）：
   ```
   python scripts/doc_map.py --source-root <源资料目录> --out <知识库目标目录>/_meta/doc_maps.jsonl
   ```
   输出每篇章节切块、知识密度、高价值块标记；只对高价值块深抽，低密度块记 skip 原因。
   高价值判据＝加权分 ≥0.5，特征含：代码围栏 / ≥3 个数字 / 命令行 / 链接 / 标题含概念词 /
   因果词 / 长段落(≥80 字) / **可落地动作词**（命令·步骤·点击·安装·脚本·参数·复制·粘贴·导出·导入·改成·运行）。
   动作词是刻意收窄的：放"工具/方法"会放进方法论空话，放"执行/输入/打开/设置"会被
   "执行力""打开认知"这类中文比喻污染（实测踩过）。
   **块内还要继续拆篇时**（第 5 步的"一块装多件事必须继续拆"，规约见 `08` §3 第 9 条），先跑一张候选边界表：
   ```
   python scripts/split_boundaries.py --doc-maps <知识库目标目录>/_meta/doc_maps.jsonl --source-root <源资料目录> --out <工作目录>/split_boundaries.jsonl
   ```
   只读源料、**只写 `--out`（不写库）**：把每个高价值块内已有的结构列成候选段，并标
   `dense`（段内 ≥2 伪标题，必拆）/ `oversized_fence`（整块代码或提示词模板超长：**≤3,000 字算一篇资产笔记，
   >3,000 字不产笔记、改在来源笔记做资产登记**；整块不许劈）/
   `frag`·`oversized_frag`（超限单位与引子粘连后的产物，仍超的就是按语义再拆的对象）/
   `media_table`（按内容判出的素材索引表，默认不产笔记）。
   **它不裁长度、也不定题**——`doc_map.py` 按标题切块的口径一字未改，定篇仍由 AI 按语义判；
   在无结构处硬切是被禁止的处置。
2. 规则初筛辅助标签：
   ```
   python scripts/tag_documents.py --manifest <工作目录>/sources_manifest.json --taxonomy assets/taxonomy/taxonomy.json --out <工作目录>/tags_pred.json
   ```
   规则只打六维辅助标签；**flow/stage/substage 由 AI 读高价值块正文判定**，不猜；内容主题 topics 由 AI 读高价值块标注（每篇 1–5 个）；`q_hooks` 口语问法（每篇 3–5 条，即"用户会怎么问这件事"）由 **AI 深抽时顺手生成**（生成者是模型，脚本不生成内容），检索优先匹配。
   **q_hooks 生成规约与五条质量红线见 `references/08_topics_pipeline_units.md` 第 3.5 节**，红线简述：禁标题复述、禁关键词堆砌、禁与正文原句雷同、每条须含本篇特有实词（不得只靠泛化 bigram 命中）、至少覆盖 3 个不同角度。
3. 对 `needs_review=true` 的文档，AI 读**标题 + 开头约 500 字**做语义补标；仍不确定的留 `99_收件箱` 待人工，不硬判。
4. **刷新可引名单**（深抽前，每批一次）：只读扫描 `工作流/` 现有笔记，取每篇的
   `doc_id` / **stem（加链用它）** / 标题 / topics / 一句话摘要，作为深抽提示词的输入上下文注入；
   超过阈值（**默认 200 篇，可配**）时按 topic 相关性分层筛选、总条数封顶。
   名单是**可引名单、不是必引名单**。字段口径、回退规则、分层策略与「目标名用 stem」见
   `references/08_topics_pipeline_units.md` 第 3.6 节。**不写脚本、不加 CLI 参数**，由执行 AI 用只读手段扫。
5. 从用户最关心工作流生成 **5 篇样板**：
   - **提交单位＝一篇文档一批**：把该篇全部候选段（含 `dense` / `oversized_fence` / `media_table` 标记）
     一次性给模型，一次返回 N 篇，**不要一块一往返**；成本口径两句写死——省的是**会话往返次数**与
     **每轮重复注入的上下文**，**不是 API 折价**（本库无模型客户端，深抽的执行者就是会话里的 AI）。
     规约出处：`08` §3 第 9 条。
   - 每个高价值块按语义单元拆 1–N 篇原子笔记（一块装多件事时**必须继续拆**，不要把多件事塞进一篇；按 `_meta/模板/note_atomic.template.md` 填写；模板中的 `<标题>`/`<日期>` 等占位由 AI 深抽时替换，非 render 槽位；flow/stage/substage + 六维 + topics + q_hooks frontmatter；三段分标；数字/命令/代码带 `§章节#字符` 定位——**定位符由 `scripts/autolocate.py --compute` 算、只交 quote**；**正文里的 `[[双链]]` 按第 3.6 节规约写——只在确实引用且需跳转时才加，没有就不加，允许孤岛**）
   - 对应 1 篇来源笔记（素材库/_来源地图/，指向所有衍生原子笔记）
   - 同批回填 `_meta/coverage_audit.jsonl`（每 chunk 一行）
   - 若开 units：同时产出 `_meta/units.jsonl` 样板，跑 `validate_extraction.py`
6. **校验 q_hooks（必须在建索引之前）**：
   ```
   python scripts/check_hooks.py --notes-dir <知识库目标目录>/工作流 --warn-log <知识库目标目录>/_meta/logs/q_hooks_warnings.jsonl
   ```
   只读校验，**不生成内容、不写笔记**。报告分两栏：**不合格**（数组形态 / 条数 3–5 / 每条 6–40 字 / 去重含仅标点差异 / 不含换行）与**待生成**（缺失或空数组）。
   - 有不合格 → 按降级规约处置：把该笔记 `q_hooks` 置空 `[]` 重落盘（**由执行 AI 做**，脚本对笔记零写入权），warning 已进日志；**不阻塞入库**；
   - 有待生成且刚深抽完 → 按第 2 步的生成规约补生成一次。
   > 为什么卡在 build 之前：`search_index.py build` 会把 q_hooks 切 gram 写进 `fts.qhooks` 列，脏 hook 一旦进索引只能靠 rebuild 清。
7. 聚合并建索引、自检：
   ```
   python scripts/build_flows.py --kb <知识库目标目录>
   python scripts/build_topics.py --kb <知识库目标目录>
   python scripts/search_index.py build --kb <知识库目标目录> --rebuild
   python scripts/verify.py --kb <知识库目标目录> --config <工作目录>/config.json
   ```
   > `--config` **不能省**：C2 的目录清单、C5 样板源路径、C7 规则档一致都从 config 取；
   > 不带它这几项只会 `[WARN] 无 config，跳过`，"verify 全绿"永远达不到，C5 里那条
   > "来源路径可达"也等于从来没验过（C14 的源目录同样靠 `config.source_root` 解析）。
   连同报告交用户验收；不满意回 Step 4。

### Step 7 · 批量入库（个人抽检制 + 抽取校验）

- **默认质量闸**：高价值块处理率 100%（coverage_audit 回填，high_value=true 必须 extracted 或 inbox；**与 `progress.py` 冲突时 progress 赢、coverage_audit 标过期**，且这条是**百分比**判据、**不进 `--gate`**）；inbox 占本批 high_value chunk >20% 视为没抽出来、本批不放行（小批次 <10 块改人工判断）；**开了 units 时 `validate_extraction.py` 必跑、有错不放行**（units 是可选辅助层：没开 units 就别跑它，它不是非 units 路径的放行依据；它现在在 `units.jsonl` 缺失/0 条时直接 exit 1，不会空跑报「通过 ✓」）；引用可定位、无来源不进事实、低信心进收件箱。
- **每批原子笔记写完后必须重跑 build_flows.py** 同步 `_流程.md` 和 `_总览.md`，保证环节总览与笔记一致。
- units 策略按 Q16.2 显式优先；未选按 Q4 痛点（含 c"不知学啥"）和 Q13.1 输出（含 d"以后做 RAG"）推断。开 units 后深抽写 `_meta/units.jsonl`，跑 `build_units.py` + `validate_extraction.py`。
- 按批量规模分批：**刷新可引名单（每批一次，非每篇一次，口径见 Step 6 第 4 步）** → 高价值块深抽 → 原子笔记 → 来源笔记 → **`check_hooks.py` 校验 q_hooks** → **units 关闭时跑 `check_verbatim_lite.py`（数值/命令逐字的替身，warn only）** → `build_flows.py` → `build_topics.py` → `search_index.py build` → `verify.py`，每批人工抽 5–10 条核对引用（覆盖子技巧/案例/工具/坑）。
- **双链不做批量补链**：`[[ ]]` 只在深抽写正文时按 `references/08_topics_pipeline_units.md` 第 3.6 节规约逐篇判断；没有明确引用就允许孤岛。抽检时**不因"这篇没有出链"判不合格**。
- **抽检（条目级）通过率 <95% → 本批回 99_收件箱**、记问题资产库、改提示词/切块后重跑。
- **续跑起点**（只读派生，**默认不是门禁**）：每批收尾跑
  `python scripts/progress.py --notes-dir 工作流 --emit-todo --path-prefix <当前批次前缀>`，
  拿"范围内第一个未完成的高价值块"当下一次起点。两类不一致（`ghost_locator` /
  `unmapped_source`）是 warn 级事实报告、不判失败；`doc_maps` 的 `coverage.chunks_processed` /
  `high_value_done` 是**已作废的历史字段**，不由任何脚本维护、progress 也不读，进度一律以
  `progress.py` 从笔记反推为准。**要"这一批能不能收"的显式判红就加 `--gate`**：它只看**本视图内**
  这两类结构性错误（**不判处理率百分比**，也不吃 `check_hooks` / `check_verbatim_lite` 的 warn），
  stdout 一字不变、理由走 stderr；带 `--path-prefix` 时**范围外的不一致不拦**（缩小视图的代价）。
  schema 与断点工作流见 `references/04_pipeline.md` 第 12 节（`--gate` 见 §12.5），
  **不新增手工账本、不做自动拦**。
- `evaluate.py`（F1/Recall/MRR/nDCG）保留为可选质检，不卡冷启动。失败先读报错根因，禁止盲目重试。

### Step 8 · 使用与维护

- 按工作流/环节一键拉取：
  ```
  python scripts/search_index.py search --kb <知识库目标目录> --flow 视频制作
  python scripts/search_index.py search --kb <知识库目标目录> --flow 视频制作 --stage 1_找素材
  python scripts/search_index.py search --kb <知识库目标目录> --flow 视频制作 --stage 1_找素材 --substage 子技巧
  ```
- 跨工作流按主题/关键词检索：
  ```
  python scripts/search_index.py search --kb <知识库目标目录> --topics 选品
  python scripts/search_index.py search --kb <知识库目标目录> --query "..."
  python scripts/search_index.py search --kb <知识库目标目录> --query "..." --include-stale
  ```
  > 关键词检索按 **查询 gram** 匹配（多语言分流：汉字/假名/韩文/泰文段出 **2-gram**，汉字段另给单字，
  > 字母词段出**整词**并做词干归一；口径见 `references/06_retrieval.md` 第 4 节）；`stale: true` 笔记默认不返回并提示被过滤数量，`--include-stale` 可召回。
- 自然语言一句话召回（大模型先出路由 JSON，脚本校验后执行；不存在的 topic/flow 一律丢弃、不编造）：
  ```
  python scripts/search_index.py recall --kb <知识库目标目录> --query "视频爆款分析"
  python scripts/search_index.py recall --kb <知识库目标目录> --route-json '{"keywords":["视频","爆款","分析"],"topics":["爆款"],"flow":null,"stage":null,"unit_type":null,"include_stale":false,"need_relations":true,"top_k":10}'
  python scripts/search_index.py recall --kb <知识库目标目录> --query "..." --json    # 机器可读，供大模型组织答案
  ```
  排序为 **q_hooks 命中 > FTS > topics 扩展 > relation 关联**；FTS 通道默认带弱命中门槛（`--min-bigram-hits`，默认 2，只压 FTS 不压其他通道，被滤明细写 `_meta/logs/fts_filtered.jsonl`）。细节见 `references/06_retrieval.md` 第 8–10 节。
  路由 JSON 的生成规约见 `references/06_retrieval.md` §9.4（模型侧红线 + 降级责任）。
- 新增/修改笔记后重建工作流总览与主题层：
  ```
  python scripts/build_flows.py --kb <知识库目标目录>
  python scripts/build_topics.py --kb <知识库目标目录>
  ```
- **诊断度量（只读，不改任何文件）**——库「健不健康、往哪看」，看分布不看结论：
  ```
  python scripts/audit.py --notes-dir 工作流                          # 人读（markdown）
  python scripts/audit.py --notes-dir 工作流 --format json --out _meta/audit.json   # 机器可读，便于追踪趋势
  python scripts/audit.py --notes-dir 工作流 --bigram-df-threshold 0.4 --min-q-hooks 3 --top-n 5
  python scripts/audit.py --notes-dir 工作流 --graph-mode explicit     # 只看「笔记之间有没有真连线」
  ```
  A1 relation 连通性（**`--graph-mode` 拆两张图，默认 both、分别统计不合并**：`explicit` = `[[ ]]` 双链 ∪ relation 端点指向笔记，`concept` = relation 断言 × topic 命中；各自报度数分布 / 孤岛 / 连通分量）、A2 topic 结构（独占 / 共享 / 倒排）、A3 q_hooks 覆盖率、A4 泛化 bigram（DF 占比 ≥ 阈值）、A5 stale、A6 索引一致性（引用 verify 的 C12，索引缺失标 N/A 不 FAIL）。
  **audit 是 skill 自带的 X 光机，不负责开药方**：只报「是什么」，不报「该补哪条边」，也**不判 PASS/FAIL**——放行与否是 `verify.py` 的活。细节见 `references/10_audit.md`。
  > **A1 explicit 是诊断指标，不是通过条件**：边数 0 / 孤岛多都不报错、不告警、不影响 exit。笔记间双链按 `references/08_topics_pipeline_units.md` 第 3.6 节走——只在正文确实引用时加链，**允许孤岛**，不补链、不设连通性要求。
  > `--notes-dir` 指**笔记目录本身**（默认 `工作流`），KB 根取其父目录；换库就换这个参数。报告抬头会注明扫的是哪个目录。
- **存量 q_hooks 回填（只补缺，默认不覆盖）**——给旧笔记补齐问法，不动已有的：
  ```
  python scripts/backfill_hooks.py --notes-dir 工作流 --dry-run        # 只报告哪些笔记缺，不生成、不写
  python scripts/backfill_hooks.py --notes-dir 工作流 --emit-tasks _meta/hooks_tasks.json
  #   ↑ 脚本导出待补清单（doc_id + 标题 + topics + 正文）；由深抽 AI 按 references/08 第 3.5 节
  #     的规约生成 hooks，写成 _meta/hooks_backfill.json
  python scripts/backfill_hooks.py --notes-dir 工作流                  # 校验 + 写入（已有非空跳过）
  python scripts/backfill_hooks.py --notes-dir 工作流 --force          # 覆盖已有（本 skill 里唯一真实存在的覆盖开关）
  ```
  **生成者仍是深抽 AI，脚本不生成内容**——脚本只做「扫描 → 校验（复用 `check_hooks.py`）→ 落盘」。
  校验不过的篇目置空 `[]` + warning，**单篇失败不阻塞其他篇**；缺 hooks JSON 时 exit 3 并提示先由 AI 生成。
  > ⚠️ `backfill_hooks.py` 是 skill 里**第一个会写笔记 frontmatter 的脚本**（只写 `q_hooks` 这一个字段）——
  > 批量回填手改笔记不现实。增量路径（深抽时）的置空仍由执行 AI 做。
- （选做）units 校验/聚合：`python scripts/build_units.py --kb <知识库目标目录>`、`python scripts/validate_extraction.py --kb <知识库目标目录> --source-root <源目录>`。
- 原文变更后 units 按 `references/04_pipeline.md` 第 7 节标 `stale`，不物理删除。
- 更新同步、工作流/环节/标签/配方的双向演化按 `references/04_pipeline.md`、`references/09_workflow_model.md` 执行；向量检索在 FTS 用顺、证明确有必要时再按 `references/06_retrieval.md` 引入。

## 资源索引

| 需要什么 | 去哪 | 何时读 |
|---|---|---|
| 问卷题本 + answers.json 结构 | `intake_questionnaire.md` | Step 2 |
| 底层规律、三篇原文映射、术语表 | `references/01_methodology.md` | 首次执行 / 理论存疑 |
| 三形态骨架、目录模板、混合比例 | `references/02_archetypes.md` | Step 3、Step 4 |
| 画像 schema、决策规则、冲突仲裁、兜底 | `references/03_rules_engine.md` | Step 3 |
| 入库流水线、变更同步、双向演化、迁移路径、验收 | `references/04_pipeline.md` | 全程，重点 Step 1/6/7/8 |
| 六维辅助标签模型、打标流程 | `references/05_multidim_model.md` | Step 4、Step 6 |
| 组合检索、FTS5、向量可选路径 | `references/06_retrieval.md` | Step 6、Step 8 |
| 黄金集、F1/Recall/MRR/nDCG（可选质检） | `references/07_evaluation.md` | Step 7（可选） |
| 内容主题层、units、深抽硬约束、引用校验、**笔记间双链规约与可引名单（3.6）** | `references/08_topics_pipeline_units.md` | Step 6、7、8 |
| **工作流/环节/子分组模型、原子笔记粒度、迁移路径** | `references/09_workflow_model.md` | Step 3、4、6、8 |
| **audit 检查项、阈值、输出 schema、与 verify 的边界** | `references/10_audit.md` | Step 8、库健康巡检 |
| 受控词表（主轴 + 六维辅助 + 同义词 + 种子配方） | `assets/taxonomy/taxonomy.json` | Step 3、Step 6 |
| 流程/总览/原子笔记/来源笔记/辅助模板 | `assets/templates/` | Step 5（脚本读取） |
| 扫描/画像/配置/渲染/自检脚本 | `scripts/` | Step 1–5 |
| 文档地图/打标/工作流聚合/主题聚合/检索/units/校验/质检脚本 | `scripts/doc_map.py`、`tag_documents.py`、`build_flows.py`、`build_topics.py`、`search_index.py`、`build_units.py`、`validate_extraction.py`、`evaluate.py`（可选） | Step 6–8 |
| 诊断度量（只读，分布 + 信号，不判 PASS/FAIL） | `scripts/audit.py` + `references/10_audit.md` | Step 8、库健康巡检 |
| units-off 的数值/命令逐字替身（warn only，不作门禁） | `scripts/check_verbatim_lite.py` + `references/08_topics_pipeline_units.md` §3.1 | Step 6/7 深抽后（units 关闭时） |
| **拆篇候选边界（只读源料、只写 `--out`；提示器，不是第二套切块口径）** | `scripts/split_boundaries.py` + `references/08_topics_pipeline_units.md` §3 第 9 条 | Step 6 深抽前（块内需按语义拆篇时） |
| **二进制正文转换（只写 `_meta/converted/`，源目录一字不动；产物是派生物、可重建）** | `scripts/convert_sources.py` + `references/04_pipeline.md` §4.3 | Step 6 深抽前（manifest 的 `needs_convert` 那档：docx/epub/odt） |
| **定位符计算器 + 笔记定位复核（门禁：区间/标题不符即 rc≠0，与 warn-only 的 verbatim-lite 分开）** | `scripts/autolocate.py` + `references/08_topics_pipeline_units.md` §3 第 8 条 | Step 6 深抽时算 locator；Step 7 每批笔记落盘后复核 |
| 进度派生 / 续跑起点（只读；warn 级不判失败，**`--gate` 才显式判红**） | `scripts/progress.py` + `references/04_pipeline.md` 第 12 节 | Step 7 每批收尾、跨会话续跑、CI 判绿 |
| **q_hooks 内容合规校验（只读，不生成、不写笔记）** | `scripts/check_hooks.py` + `references/06_retrieval.md` 第 8 节 | Step 6、7 笔记落盘后 |
| **q_hooks 存量回填（只补缺；唯一会写笔记 frontmatter 的脚本）** | `scripts/backfill_hooks.py` + `references/06_retrieval.md` 第 8.3 节 | Step 8、存量维护 |
| **十二套探针 P1–P12（只读面回归自检，跑在临时库里，非交付物）** | `probes/README.md` + `probes/wikilink_rules/probe.py` | 改深抽规约 / 检索 / audit / verify / 切块口径之后各跑一次 |

## 可选依赖（只服务 `convert_sources.py`）

**不装也能跑完整条流水线**：`needs_convert` 那一档（`.docx/.epub/.odt`）就退回今天的行为——
manifest 里登记 + 列入 `_meta/问题资产库.md`、不深抽。装了才把这一档走通。
**缺哪个包，脚本就 rc≠0 并点名那个包**，绝不静默跳过（实测：把 `unstructured` 用空包遮蔽后转 `.docx`
→ rc=1、stderr 打「未安装 unstructured：pip install …」、`_meta/converted/` 零写盘；同夹具不加遮蔽即 rc=0 出产物）。

| 用途 | 包 | 本机实测版本 | 备注 |
| --- | --- | --- | --- |
| 分区器总入口（docx/epub/odt） | `unstructured` | 0.27.16 | 只装本体，**不装 `unstructured[all-docs]`**（实测 112 个包，且其中 `pdf` 分支还要 poppler 外部二进制——本轮不接 PDF） |
| `.docx` 解析 | `python-docx` | 1.2.0 | `partition_docx` 的实现依赖 |
| `.docx`/`.odt` 内的 HTML 片段 | `markdown`（`Markdown`） | 3.11 | 把 HTML 块转成 md |
| `.epub` 读取 | `EbookLib` | 0.20 | `partition_epub` 的实现依赖 |
| 扩展名/真实类型兜底核验 | `python-magic-bin` | 0.4.14 | **Windows 必装**：只装 `python-magic` 时 `magic.loader` 找不到 DLL，`partition.auto` 是 **native access violation**（进程内 try/except 抓不住），所以核验放在**子进程**里跑 |
| epub/odt 的 pandoc 后端 | `pypandoc-binary` | 1.17 | 自带 pandoc 可执行文件 |

> **`.odt` 未验证**：分派表里挂着 `partition_odt`，但本库没有 odt 样本、没跑通过，
> `convert_sources.py` 的 `DISPATCH` 里就地标注了「本库未验证」。要用 odt 先补一个真样本再放开。

装法（一次装齐，本库实测通过 docx＋epub 两档）：

```bash
./env/Scripts/python.exe -m pip install unstructured python-docx Markdown EbookLib python-magic-bin pypandoc-binary
```

## 硬性规则（写入生成的 AGENTS.md，本 Skill 同样遵守）

1. 源资料目录所有文件**只读**：不删、不改、不重命名；唯一例外是问卷明确授权、方案逐文件确认过的"未归桶资料归位"。**这条有机器把关**——Step 5 建 `_meta/source_snapshot.json` 基线后，每次 `verify.py` 的 **C14** 都会比 sha256：被改/被删即 FAIL，新补的资料只是 WARN（等人工确认走 intake 后重建基线）。详见 `references/04_pipeline.md` 第 11.1 节。
2. 知识层**不复制**原文正文、图片、PDF、视频、安装包；笔记用相对路径引用源文件。
3. **主轴是 flow/stage/substage**：每篇原子笔记必须归到 1 个主工作流和 1 个主环节；环节是物理目录，不是标签视图。
4. 六维辅助标签用于跨工作流检索；同义词先归一，长尾新标签人工确认后才生效，不自动决定目录。
5. 同名文件不覆盖、不自动合并，遇同名先报告差异。
6. 每条结论挂 `sources`；三段写死：`evidence.quote`=资料原话（逐字，validate 严格子串）、各类型主字段=归纳结论、`inference`=AI 推断；数字/日期/命令/代码逐字保留、不归一。**这两条现在有机器把关**：逐篇 `sources` 非空且可达 = verify **C5（缺即 FAIL）**；三段分标齐全 = verify **C9（缺即 FAIL）**。
7. 检索只读，工作流/环节拉取以物理目录和 `_流程.md`/`_总览.md` 为入口；批量移动/删除/重命名/写规则前先出方案并等待确认，并**生成 `操作前清单_<时间戳>.md`（篇名 / 原路径 / 目标路径）**，事后核对文件总数守恒——这份清单是唯一的回滚依据，别省。
8. 每批生成后实际回读、重跑 build_flows 与 verify、validate_extraction（verify 的 C12/C13 要求索引与主题层非空、且索引篇数与磁盘一致，0 篇或忘 rebuild 都不放行；`confidence` 为 low 或缺失会被 **C15 WARN** 点名，按 `08` §3 硬约束 5 该进 `99_收件箱`）；高价值块处理完、**inbox 占比 >20% 不放行、抽检条目 <95% 回滚**（这两条是**人工闸，无脚本把关**，自己算）；每批人工抽 5–10 条核对；evaluate 为可选质检；文件存在不等于正确。
9. 深抽遵守 `references/08` 第 3 节硬约束；无来源写 null，禁止编造 locator/引文。
10. 单元合并保留全部 evidence（转数组）；冲突不合并，建 conflict 单元。
