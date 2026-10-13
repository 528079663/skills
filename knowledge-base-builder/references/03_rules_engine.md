# 03 · 规则引擎（画像 → 配置）

> 本文件把"问卷答案 → 用户画像 → 渲染配置"的全过程定义为可执行规则，供 `build_profile.py` 与 `render_config.py` 直接实现。
> 包含：数据 schema、逐题转换规则、决策规则、冲突仲裁、兜底分支。
> 凡阈值/默认值，均为**工程默认可配置项**，不是原文数字（原文唯一有依据的数字：【Blake】Skills 重复 3 次）。

## 目录
1. answers.json schema（问卷原始输入）
2. profile.json schema（结构化画像）
3. answers → profile 逐题转换
4. config.json schema（渲染配置）
5. profile + manifest → config 决策规则
6. 冲突仲裁
7. 兜底分支
8. 标签集生成规则

---

## 1. answers.json schema

```json
{
  "q1_goals_ranked": ["b", "a", "c"],
  "q2_first_task": "字符串，半年后第一件事",
  "q3_painpoints": ["a", "b"],
  "q4_doc_types": ["a", "b", "d"],
  "q5_ingest_scope": {"md": true, "minutes": true, "pdf": false, "media": false, "images": false},
  "q6_unsorted": "a",
  "q7_collab": "b",
  "q8_note_depth": "b",
  "q9_batch_size": "b",
  "q10_output_targets": ["a", "b"],
  "q11_taxonomy": "d",
  "q12_privacy": ["a", "c"]
}
```

字段约定：
- 选择题取值为题本中的选项字母；多选为数组；排序题数组顺序即优先级（index 0 最高）。
- 漏答 / "你建议"：该字段为 `null`；多选全漏为 `null`（不用空数组，空数组表示"明确都不选"）。

---

## 2. profile.json schema

```json
{
  "archetype_weights": {"learn": 0.0, "create": 0.0, "project": 0.0},
  "primary_archetype": "create",
  "is_mixed": true,
  "first_task": "字符串",
  "painpoints": ["retrieval", "forgetting", "direction", "workflow", "scattered"],
  "doc_types": ["case", "minutes", "tutorial", "prompts", "sop", "links"],
  "ingest_scope": {"md": true, "minutes": true, "pdf": false, "media": false, "images": false},
  "unsorted_policy": "suggest_table | skip | handpick",
  "collab_level": "conservative | balanced | aggressive",
  "note_depth": "card | topic | deep",
  "batch_size": 5,
  "output_targets": ["local", "feishu", "notion_pub", "rag"],
  "taxonomy_preference": "topic | project | material | mixed",
  "privacy_exclusions": ["income", "accounts", "internal"],
  "defaults_applied": ["字段名: 默认值: 理由"]
}
```

---

## 3. answers → profile 逐题转换

### q1 → archetype_weights / primary_archetype / is_mixed

- 按 `02_archetypes.md` 第 5 节规则 5.1–5.4 计算：
  - 显式排序：位次权重 `weight(rank) = (N - rank)/Σ(N-j)`。
  - 目标归并：a→learn；b→create；c→project；d→create 与 project 各计半权；e→learn。
  - 同形态多目标命中：权重相加后整体归一化。
- `primary_archetype` = 权重最高者；`is_mixed` = 无任一形态权重 ≥ 0.6。
- q1 为 null：见第 7 节兜底 D1。

### q2 → first_task

- 原样保留字符串；用于方案中校验"目录与模板是否支撑这件事"。
- 若 q2 描述含明确项目/产品名，抽取为 `project_hint`（附加字段），供形态 C 与 projects 目录使用。

### q3 → painpoints

- 映射：a→retrieval，b→forgetting，c→direction，d→workflow，e→scattered。
- 用途（影响配置，非仅展示）：
  - retrieval 高频 → 强化 `文件目录.md` 与标签体系（规则档中"补标签"降为 L0）。
  - forgetting 高频 → 默认笔记档至少 topic（速读卡信息不足）。
  - direction 高频 → 学习型加 `学习路径.md` 的优先级提高。
  - workflow 高频 → 提示词/SOP 目录与后期 Skills 路径重点标注。
  - scattered 高频 → 主题地图与双向链接作为 P1 必做项。

### q4 → doc_types

- 映射：a→case，b→minutes，c→tutorial，d→prompts，e→sop，f→links。
- 用于校验 q5 入库范围是否覆盖了资料主体（见冲突 C3）。

### q5 → ingest_scope

- 原样转布尔；缺省按 D3 处理。

### q6 → unsorted_policy

- a→suggest_table，b→skip，c→handpick（handpick 时需用户另给篇名，未给则降级为 suggest_table 并记录默认项）。

### q7 → collab_level

- a→conservative，b→balanced，c→aggressive；null→balanced（D4）。

### q8 → note_depth

- a→card，b→topic，c→deep；null→topic（D5）。
- 若 q3 含 forgetting 且 q8=a：不自动改档，但在方案中提示"速读卡可能不足以解决看完就忘"。

### q9 → batch_size

- a→5，b→20，c→100；null→20（D6）。

### q10 → output_targets

- 映射：a→local，b→feishu，c→notion_pub，d→rag。
- 影响：
  - 含 feishu/notion_pub → 生成的 README/笔记避免平台不兼容语法（HTML 表格保留但提示），并在 AGENTS 中加"输出平台适配副本，不改本地原文"（【Blake】附录 B）。
  - 含 rag → frontmatter 字段规范化（tags 只用主标签池），并在方案中把"向量化/RAG"列为后期路径。

### q11 → taxonomy_preference

- a→topic，b→project，c→material，d→mixed；null→mixed（D7）。

### q12 → privacy_exclusions

- 映射：a→income，b→accounts，c→internal；null→空数组。
- 含任意项：AGENTS 增加排除规则，笔记生成时对命中内容跳过或脱敏；`internal` 命中时整个库标记为"私有，禁止对外分享"（【Blake】附录 C）。

---

## 4. config.json schema

```json
{
  "archetype": "create",
  "archetype_weights": {"learn": 0.0, "create": 0.0, "project": 0.0},
  "source_root": "<源资料目录的绝对路径>",
  "kb_root": "<知识库根目录的绝对路径>",
  "notes_dir": "工作流",
  "directories": [
    {"path": "00_导航", "create": true, "reason": "..."},
    {"path": "01_案例库/B站", "create": true, "reason": "manifest 中命中 N 篇"}
  ],
  "files": [
    {"template": "README.template.md", "target": "README.md", "vars": {"archetype_name": "创作型"}},
    {"template": "AGENTS.template.md", "target": "AGENTS.md", "vars": {}}
  ],
  "note_template": "note_topic.template.md",
  "rules": {"new_note": "L0", "fix_format": "L0", "add_tags": "L0", "move_in_inbox": "L1",
            "edit_source": "L2", "delete": "L2", "batch_20plus": "L2", "rename_topic": "L2",
            "write_rules": "L2"},
  "tags": {"primary": ["..."], "candidate": ["..."], "aliases": {"youtube": ["YouTube", "YPP"]}},
  "special_handling": {
    "unsorted": {"policy": "suggest_table", "index_target": "00_导航/待分拣索引.md"},
    "orphan_pdfs": [{"path": "...", "action": "register|extract", "reason": "..."}],
    "essenceless_minutes": [{"path": "...", "action": "generate_essence|skip"}],
    "card_pdfs": [{"path": "...", "action": "extract_cards|register_only"}],
    "needing_convert": [{"path": "...", "action": "convert_then_register|register_only", "reason": "..."}]
  },
  "sample_notes": [{"source": "...", "topic": "...", "reason": "..."}],
  "conflicts_resolved": [{"id": "C1", "rule": "...", "original": "...", "decision": "..."}],
  "defaults_applied": ["..."]
}
```

**三个路径键的口径**（`04 §12` 与 `SKILL` 的资源索引以这段为准）：

- `source_root`：**必填**才能跑 `verify` 的 C14 与 `check_verbatim_lite`。缺了它 `verify` 会
  `KeyError` 整工具崩（**发现 34**，第三批处理；本批只登记事实：跑通 verify 的 config 至少要
  有 `source_root` / `rules` / `directories`，`sample_notes` 可为空数组）。
- `notes_dir`：笔记目录名，**相对 `kb_root`**，缺省＝`工作流`（即 `search_index.DEFAULT_NOTES_DIR`）。
  它决定 `verify --config` 时 C2/C4/C5/C9/C10/C11/C12/C15 扫哪个目录，也决定 C12 的磁盘篇数按哪儿数。
- `kb_root`：**可缺省**。缺省时各脚本沿用「笔记目录的父目录」；库是嵌套布局
  （如 `kb/content/notes`）时显式给出，或用 CLI 的 `--kb` 覆盖。
- **读取优先级统一为：CLI（`--kb` / `--notes` / `--notes-dir`）> config 的 `kb_root` / `notes_dir` > 兜底**
  （父目录推导 + `DEFAULT_NOTES_DIR`）。无参数 + config 不带这两键时，行为与从前**逐字节相同**。
- **special_handling 各键的产出状态**（A4 补，免得文档吹过头）：`unsorted` / `orphan_pdfs` /
  `essenceless_minutes` 由 `render_config.build_special()` 从 manifest 真产出；
  **`needing_convert` 本批只登记字段形状（结构对齐 `orphan_pdfs`），`render_config` 尚未写它**——
  数据源已经就位（`manifest.documents.needs_convert`），产出它属下一档活；在它被产出之前，
  需要处理 docx/epub/odt 时按 `04 §4.3` 走"降级登记 + 进问题资产库"的人工路径。
- `render_config.py` **目前不写** `notes_dir` / `kb_root`（本批决定：不动 `build_directories()`），
  所以新建库的 config 里没有这两键属正常——它们靠缺省生效。将来要写，得连
  `directories` 的生成口径一起对齐，属另起一批的活。

### 4.1 真库有、上面示例未登记的 19 个键（丙批补录）

示例顶层 14 键，真库 `config.json` 顶层 28 键，差集 19 个。逐个列清「谁读它／缺了会怎样」，
**不要照着示例写 config**——示例是形状说明，不是必填清单（必填见 4.2）。

| 键 | 谁读 | 缺了会怎样 |
| --- | --- | --- |
| `flows` | `render_templates`（`.get`） | 环节聚合页与 `_流程.md` 的环节顺序失去来源，只能靠目录名倒推；不崩 |
| `first_task` | `render_templates`（`.get`） | README/AGENTS 的「当前任务」段落失去初值；不崩 |
| `output_targets` | `render_templates`（`.get`） | 交付目标段失去初值；不崩 |
| `privacy_exclusions` | `render_templates`（`.get`） | 隐私排除项为空（**注意：不崩不等于没影响**，脱敏约定会静默消失） |
| `projects` | `render_templates` **硬下标** | **KeyError 崩**（属渲染必填档，见 4.2） |
| `_run_note` | 无脚本读 | 纯人工记录位；缺省无害 |
| `aux_tags_enabled` / `topics_enabled` / `extract_units` / `extraction` / `retrieval_mode` / `note_depth` / `granularity` / `scale` / `batch_size` / `topic_policy` / `primary_axis` / `dimensions` / `existing_kb` | **无脚本读取**（纯约定） | 由执行 AI 遵守；`extract_units` 决定走不走 units 路径、`extraction.chunk_size` 是切块上沿参照、`dimensions`/`primary_axis` 是标签词表——**写了是给 AI 看的，删了脚本不会报错**，所以这类键的失效是**静默的**，靠抽检 |

**示例里有、真库没有的 5 键**：`archetype` / `archetype_weights` / `tags` 属**早期示例位**
（现库不写也能跑），`kb_root` / `notes_dir` 是 A2+A3 参数化后的新键、真库确实没写（靠缺省生效）。
**本批只在文档里标注"可不写"，不从示例里删**——删会牵动 §4 示例结构与 `render_templates` 的形状说明。

### 4.2 config 必填集（两档必填，发现 34 的前置定义）

| 档 | 键 | 依据（实测） |
| --- | --- | --- |
| **事实必填**（跑通 `verify` 的最少集） | `source_root` / `directories` / `rules` | `verify.py` 对这三个是**硬下标**。实测：只喂这三键跑真库 → **pass=17 fail=0 warn=0、rc=0**；再删 `rules` → 崩在 `config["rules"]` 的 `KeyError` |
| **渲染必填**（Step 5 才炸的第二档） | 再加 `files` / `projects` / `special_handling` | `render_templates.py` / `render_config.py` 对它们是硬下标。**只给三键的 config 能过 verify，却会在渲染阶段才失败**——这就是"跑通"必须分档的原因 |
| **推荐** | `flows` / `sample_notes` / `notes_dir` / `first_task` / `output_targets` / `privacy_exclusions` / `extraction` / `extract_units` / `topic_policy` / `topics_enabled` / `aux_tags_enabled` / `granularity` / `note_depth` / `retrieval_mode` / `scale` / `batch_size` / `primary_axis` / `dimensions` / `existing_kb` / `link_target_dirs` | 有默认值或只被执行 AI 遵守，缺了能跑但**行为会变**（其中"只被 AI 遵守"的那批，变了是**静默的**）。`link_target_dirs`（乙批 B7）是 C10 目标全集的**追加档**：**只有 config 一档、没有 CLI 开关**，不写＝今天口径逐字节相同；它只能追加，改不动 `工作流` 与 `素材库/_来源地图` 这两段（`P12-dir⑨` 钉着） |
| **可缺省** | `_run_note` / `kb_root` / `notes_dir`（参数化新键，CLI > config > 兜底已覆盖）＋ `archetype` / `archetype_weights` / `tags`（示例位） | 真库就没写 `kb_root` / `notes_dir`，verify/audit 全绿 |

> **一句附注（不改代码，只登记）**：事实必填那档缺键时的崩法是 **`KeyError` traceback**，
> 不是「config 缺键 `rules`，请补」这种点名错误。属乙批「响亮失败」家族，本批**不动代码**。

---

## 5. profile + manifest → config 决策规则

### R1 · 目录集合

- 基础目录集来自主导形态骨架（`02_archetypes.md` 2–4 节）。
- 混合形态按 02 第 6 节并入；并入阈值默认 0.2（可配置 `mix.merge_threshold`）。
- 每个叶子目录的 `create` 判定：
  - manifest 中存在可承接资料 → `true`；
  - 无资料承接 → `false`，列为预留（不落地）。
- projects 目录：仅当 profile 有 `project_hint` 或用户能命名项目时创建。

### R2 · 文件集合

- 必备：README、AGENTS、`_meta/问题资产库.md`、`00_导航/文件目录.md`（占位，由扫描/脚本生成内容）。
- 按形态加：学习→学习路径；创作→素材地图/选题池占位；项目→每个项目 PROGRESS。
- 笔记模板：按 `note_depth` 选对应模板文件，复制到 `_meta/模板/`（供后续批量统一格式）。

### R3 · 规则档（rules）

基线按 collab_level：

| 动作 | conservative | balanced（默认） | aggressive |
|---|---|---|---|
| new_note / fix_format | L1 | L0 | L0 |
| add_tags | L1 | L0 | L0 |
| move_in_inbox | L2 | L1 | L1 |
| edit_source / delete / rename_topic / write_rules | L2 | L2 | L2 |
| batch_20plus | L2 | L2（先预览方案） | L1（先预览） |

- L0=直接做、事后汇报；L1=提示/预览后做；L2=先方案+确认。
- 无论哪档，edit_source / delete 恒 L2（安全底线，不可被激进档放开）。

### R4 · 特殊资料处理

- 孤儿 PDF：
  - 内容型（如问答整理、卡片本体）→ `extract`（提取文本入库为笔记/卡片）；
  - 无法判定 → `register`（只登记路径，列入待确认）。
  - 卡片型 PDF（505 卡片类）→ 默认 `extract_cards`（PDF 文本提取 → 卡片文件）；若环境无 PDF 解析库，降级 `register_only` 并在问题资产库记录。
- 无精华逐字稿（`.transcript.txt` 类）：
  - q5. minutes=true → `generate_essence`（生成精华笔记）；
  - 否则 `skip`，只登记。
- 未归桶资料：按 unsorted_policy 配置；suggest_table 的索引目标路径固定写入。

### R5 · 样板笔记选择

- 从 manifest 选 5 篇，规则：
  1. 优先覆盖 primary_archetype 下最高频的 3 个主题；
  2. 1 篇覆盖次形态主题；
  3. 1 篇选信息密度高、可验证性强的代表作（避免选纯资源链接帖）；
  4. 原文为妙记时，优先选已有精华笔记的（样板阶段不新增逐字提炼）。
- 选不出 5 篇（资料过少）→ 按实际数量生成并在方案中说明，不凑数。

---

## 6. 冲突仲裁

总原则：**安全 > 可用 > 效率**；无法自动消解的冲突，不替用户决定，列入方案"待你拍板"。

| ID | 冲突情形 | 仲裁 |
|---|---|---|
| C1 | q7=conservative 且 q9=100 | 安全优先：批量降为 20，记录 conflicts_resolved，方案中说明 |
| C2 | q8=deep 且 q9=100 | 深度档单批上限 20（工程约束：深度笔记体量）；或建议改 topic——默认取前者并说明可改 |
| C3 | q4 主体是 minutes，但 q5.minutes=false | 资料主体被排除：默认改为"妙记引用/生成精华笔记"（轻量入库），不整体放弃；方案中提示 |
| C4 | q11=project 但无 project_hint/项目名 | projects 目录暂不建，一级分类暂按 topic，项目明确后再演化 |
| C5 | q12=internal 且资料几乎全是内部手册 | 库可建，整体标记"私有禁分享"；方案中提示该库不具备对外用途 |
| C6 | q6=skip 但 q1 主目标依赖最新案例 | 不冲突但缩范围：在方案中注明"20260929 不处理，创作素材仅来自已归桶资料" |
| C7 | q5 全 false（什么都不提炼） | 与建库目标根本矛盾：列入"待你拍板"，不自动生成空库 |

---

## 7. 兜底分支

| ID | 情形 | 默认处理 |
|---|---|---|
| D1 | q1 缺失 | 创作型单形态（weights create=1.0），defaults_applied 记录"目标未明，暂按创作型" |
| D2 | q2 缺失 | first_task=null；方案中不虚构任务，改为列"建议的首个真实任务"候选 |
| D3 | q5 缺失 | md=true、minutes=true（引用精华）、pdf/media/images=false |
| D4 | q7 缺失 | balanced |
| D5 | q8 缺失 | topic |
| D6 | q9 缺失 | 20 |
| D7 | q11 缺失 | mixed |
| D8 | 选项值非法（不在题本内） | 该值按 null 处理，记录 defaults_applied |
| D9 | 源目录扫描为空/不可读 | 停止流程，报告"未找到可处理资料"，不生成任何目标文件 |
| D10 | 目标目录已存在且非空 | 不覆盖、不合并：报告差异，请用户选择新目录/由用户自行清理后继续 |
| D11 | 目标目录位于源目录内部 | 拒绝并说明（知识库不应建在源资料内），重新确认目标目录 |
| D12 | 脚本依赖缺失（如 PDF 解析库） | 相关动作降级（register_only），在问题资产库记录"缺依赖/影响/补装命令"，不静默跳过 |

所有兜底触发都必须：①写入 profile 的 `defaults_applied`；②在 Step 4 方案第 7 节"替你默认的事项"中逐条公示。

---

## 8. 标签集生成规则

1. **基线来源**：manifest 中若源目录自带分类清单（如 `主题分类清单.csv`），读取其标签列；同时统计所有 md frontmatter 的 tags。
2. **归一化**：
   - 大小写统一（`youtube/YouTube`）；
   - 同义词按 aliases 表合并（默认表在 config.tags.aliases，可由用户增改）；
   - 中英文同义合并（如 `claude/Claude Code`）。
3. **分级**（阈值可配置 `tags.primary_min_count`，工程默认 5）：
   - `primary`：归一化后频次 ≥ 阈值；
   - `candidate`：频次 < 阈值，保留观察，不进 frontmatter 主选。
4. **新增标签规则**：批量生成中出现的新标签，累计出现 ≥3 次（沿用【Blake】"重复 3 次"口径）才升级进 primary。
5. 未归桶资料（如 20260929）纳入标签统计，保证新主题不被遗漏。
