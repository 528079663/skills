# 06 · 组合检索与项目配方

> 本篇定义"项目配方 → 维度过滤 → FTS5（→ 可选向量）→ 融合排序 → top-k"的确定性检索流水线。
> 目标：项目制使用时**一键、稳定、可复现**地拉出一组知识，不手敲条件、不靠 AI 临时翻文件。
> 配套脚本：`scripts/search_index.py`。

## 目录
1. 项目配方 schema（recipe.yaml）
2. 组合逻辑（OR / AND / NOT）
3. 检索流水线总览
4. FTS5 索引设计与中文处理
5. 打分、排序与融合
6. 统一拉取入口与输出格式
7. 命名视图（模块）
8. q_hooks：口语问法（录入侧生成、检索侧优先）
9. 查询路由 JSON（大模型 → 脚本契约）
10. recall：四通道合并检索
11. 向量检索预留

---

## 1. 项目配方 schema（recipe.yaml）

存放于 `projects/<项目>/recipe.yaml`：

```yaml
project: AI自媒体
filters:
  domains: [AI]
  forms: [自媒体]
  types: [教程, 案例, 复盘, 素材]
keywords: ""            # 可选；为空则纯维度过滤
exclude: [过时, 草稿]
rank: [相关度, 时间]
limit: 50
```

字段：
- `filters`：维度 → 期望标签值（可多值）；只写需要约束的维度。
- `keywords`：可选关键词，存在时叠加 FTS5 全文匹配。
- `exclude`：排除标签；`过时` 同时映射到 frontmatter `stale: true`。
- `rank`：排序键，**按顺序级联生效**（列表越靠前优先级越高）；可选 `相关度 / 时间 / 类型优先级`，由 `search_index.run_query` 真正参与排序。
  - `相关度`：有 `keywords` 时按 bm25（越小越相关）；无关键词时记中性、不改变顺序。
  - `时间`：按 `updated`（或 `created`）降序。
  - `类型优先级`：按 `TYPE_PRIORITY`（教程/SOP/案例 > 复盘/问答/观点/素材）降序。
  - 未配置 `rank` 时保持默认：有关键词按 bm25 主序，无关键词按标签匹配度主序。
- `limit`：返回条数（top-k，默认 50）。

配方种子见 `assets/taxonomy/taxonomy.json -> project_seed_recipes`，向导阶段按形态预选，用户改后落地。

---

## 2. 组合逻辑（OR / AND / NOT）

把配方/查询翻译成对文档的布尔条件：

| 情形 | 运算 | 含义 |
|---|---|---|
| **同一维度多值** | OR | `tools: [Codex, 剪辑]` → 文档 tools 含**任一**即可 |
| **跨维度** | AND | `domains=AI` 且 `forms=自媒体`，须**同时**满足 |
| **排除** | NOT | 不含 exclude 标签，且 `stale=false` |

形式化：文档 `d` 通过当且仅当
```
对 filters 中每个维度 dim：  d.tags[dim] ∩ filters[dim] ≠ ∅      （同维 OR）
且 对所有维度条件同时成立：   ∀dim 上式为真                          （跨维 AND）
且  d.tags[*] ∩ exclude = ∅  且 d.stale = false                   （NOT）
```

示例：
- AI自媒体：`domains∋AI AND forms∋自媒体`
- Codex剪辑：`domains∋AI AND (tools∋Codex OR tools∋剪辑)`
- 同一篇《用 Codex 自动剪 AI 口播视频》两个项目都命中。

---

## 3. 检索流水线总览

```
recipe.yaml / 用户查询
   │
   ├─ 解析为维度条件（同维 OR / 跨维 AND / NOT）
   ├─ ① 标签维度过滤 → 候选集合（高精度，缩小范围）
   ├─ ② FTS5 关键词匹配（keywords 非空时；对候选打分）
   ├─ ③ 可选向量语义检索（见第 11 节，默认关闭）
   ├─ 融合去重（多通道结果合并，按文档唯一路径去重）
   ├─ 按 rank 级联排序（相关度 / 时间 / 类型优先级；未配置则用默认序）
   └─ 返回 top-k（标题 + 一句话 + 维度 + 来源 + 分数）
```

要点：
- 纯项目拉取（无 keywords）：① 即可产出，按时间/类型排序。
- 关键词查询：① 缩小范围后 ② 精排；也允许只给关键词、不约束维度（此时 ① 为全集）。
- 整条流水线由脚本确定性执行，结果可复现；AI 只负责理解自然语言并生成配方/条件，不负责逐篇翻找。

> **explicit 边（笔记正文里的 `[[双链]]`）是可选增强，检索不依赖它。**
> 本条链路的"一跳候选"来自 **topics 扩展与 units 的 relation 断言**（第 10 节 recall 的第 3、4 步），
> 从不读 `[[ ]]`：`search_index.py` 全文没有任何 wikilink 解析。
> - 有 explicit 边：它只是给人读的引用跳转，顺带被 `audit.py` A1 当诊断指标数一数；
> - 没有 explicit 边：检索照旧走 topic 桥接，**不会因此召回变少**。
>
> 所以加不加链、库里有几个孤岛，都不改变检索行为。链的取舍是建模层的事，
> 见 `08_topics_pipeline_units.md` 第 3.6 节；不要为了"让检索多一条通道"而去补链。

---

## 4. FTS5 索引设计与多语言分词

索引对象：`工作流/` 下每篇原子笔记一行（`_流程.md`/`_总览.md` 等 `_` 前缀聚合页不入索引），字段：
- `path`（主键，相对路径）、`title`、`body`（正文）、`dimtext`（辅助标签 `domains/forms/tools/types/projects` + `topics` 拼成的文本，便于标签/关键词同体检索；`sources` 不入 dimtext）、`qhooks`（口语问法，单独成列，见第 8 节）。
- `meta` 表：`schema_version`（当前 **v4**；v2＝中文 2-gram 索引，v3＝+ `q_hooks` 列，v4＝分词改多语言分流）、`notes_indexed`；`verify.py` C12 既校验该版本，也把 `notes_indexed` 与**磁盘实际笔记数**比对（目录口径同 `DEFAULT_NOTES_DIR` = `工作流`，跳过 `_` 前缀聚合页），不符须 `--rebuild`。

> 索引/主题层的**分布诊断**（relation 连通性、topic 结构、q_hooks 覆盖、泛化 bigram、stale）走 `scripts/audit.py`，见 `references/10_audit.md`。分工：`verify` 判 PASS/FAIL 给 CI，`audit` 只给分布与信号、只读、不改任何文件。

分词（**零依赖默认方案**，实现见 `search_index.gram_units()`）：A1 起**按脚本切段、按段类分流**，
切段与 n-gram 一律按 **Unicode 码点**（不是 UTF-8 字节）——所以谚文、带变音的拉丁一个字符就是一格。
- 为什么不用 FTS5 自带的：`unicode61` 对连续中文会整段成一个 token，`trigram` 又要求查询 ≥3 字符（"剪辑"等 2 字词漏召回）。
- **段类 → 产什么 gram**：

| 段类 | 码位 | 索引侧（`to_index_text`，`sizes=(1,2)`） | 查询侧（`sizes=(2,)`） |
| --- | --- | --- | --- |
| 汉字 + 扩展A + 平/片/半角假名 | U+4E00–9FFF、U+3400–4DBF、U+3040–30FF、U+31F0–31FF | **单字 + 2-gram**（单字档兼容 1 字查询） | **2-gram** |
| 韩文（音节/jamo/兼容字母）+ 泰文 | U+AC00–D7A3、U+1100–11FF、U+3130–318F、U+0E00–0E7F | **只 2-gram**（单字不开：谚文/泰文字母单独成 gram 无检索价值） | **2-gram** |
| 字母词段 | 全脚本字母 + 数字 + `_` + 组合变音符（段类正则见 `search_index._WORD_TOKEN_RE`） | **整词**：`lower()` + 轻量词干 | **整词**（同一函数） |

  - 例：`Codex剪辑教程` → `codex 剪 辑 教 程 剪辑 辑教 教程`；`키워드 선정` → `키워 워드 선정`；`動画企画の` → `動 画 企 画 の 動画 画企 企画 画の`
  - **两段 n-gram 分属两段**：`关键词คัดค้น` 不产「词ค」这种跨脚本 gram；`AI选题` 照旧切成 `ai` + `选题`
    （实现是「先按 n-gram 段切开、剩下的才当词处理」，所以变音拉丁 `vidéos` 也不会被拆成 `vid`+`éos`）。
- **轻量词干** `stem_light`：后缀表 `ies→y / ing / ed / es / s`，**剥完至少留 3 个码点**，**无例外表**；
  只作用于 ASCII 词段（西里尔/希腊等**不剥**，俄文词形变化仍是整词精确匹配＝已知边界）。
  索引侧与查询侧共用本函数，所以「同一个词」永远自配：剥错最多是两个形态没并上，**不会把原来能命中的查询弄成命不中**。
  例：`doc_maps.jsonl` → `doc_map jsonl`；`videos` → `video`。
- **停用词** `STOP_WORDS`（**en 50 条 / ru 30 条**）：**只在字母词段生效**，中文单字仍走 `STOP_CHARS`。
  不做语言识别——en 全拉丁、ru 全西里尔，两表按码位天然不相交，查一次并集即可。只收**无歧义虚词**：
  `may/will/can/now/key` 这类同时是检索词的词不收，人称代词族（`i/you/he/they…`）也不收（"I" 在个人品牌类库里能当内容词）。
  日/韩/泰停用词本批未收＝已知边界。词干先于停用词，故 `does/doing` 这类剥不动的形态直接列进表。
  - **索引侧不删**（`to_index_text` 走 `drop_stopwords=False`）：停用词照旧进索引，纯停用词查询也仍有召回；
  - **查询侧删**（`fts_hits` / `cmd_recall` / `matched_hooks` 走 `drop_stopwords=True`），两条护栏：
    ① 整段查询**全是**停用词时不删（否则查询退化成空 MATCH、静默 0 结果）；
    ② `matched_hooks` 的 **gram 分母也用删过的集合**（红线：虚词不占分母，见第 8 节）。
- 用**滑动窗口**（步长 1）而非不重叠切分：不重叠会让「关键词选品检索」中的「选品」落在错位边界而无法被索引，滑动窗口保证任意相邻双字都可召回。
- 旧单字 OR 会让「内容/归纳/资料」这类模板常用字命中全库（BM25 对 df=100% 的词给 0 分，表现为一排 `-0.000` 噪声）；改为按**查询 gram**匹配（第 4 节分流：汉字段查询侧只出 **2-gram**、索引侧另留单字兼容 1 字查询，字母词段出**整词**）后消除该问题。
- 升级路径（可选，非默认）：环境允许时改用 SQLite `trigram` 分词器，或引入 `jieba` 做词级切分；**当前 P0 明确不引入 jieba / 向量**。

**FTS 通道弱命中门槛**（`--min-bigram-hits`，默认 **2**；常量名/参数名里的 bigram 是历史名，
按 A1 裁决不改，实际数的是「不同**查询 gram**」——汉字/假名/韩文/泰文为 2-gram，字母词为整词）：

- 查询切出 **≥2 个查询 gram** 时，FTS 通道要求结果至少命中 **2 个不同的 gram**；
- 查询只切出 **1 个 gram** 时（如「选题」或单个字母词）**不启用**门槛——否则单字/单词查询会被误杀；
- 门槛**只作用于 FTS 通道**：被滤掉的弱命中若被 q_hooks / topics / relation 通道补回，仍会进结果；
- 被滤条目写入 `_meta/logs/fts_filtered.jsonl`，每行含 `doc_id` / `grams_hit` / `bm25` / `channel`；
- 输出保留 **「FTS 命中数 / 其他通道补回数」**，过滤不是静默的；
- `--min-bigram-hits 1` 关闭门槛（回到纯查询 gram OR）。

> 实测：查询「视频爆款分析」切出 5 个 2-gram，FTS 命中 7 篇 → 保留 2 篇（弱命中过滤 5 篇）。被滤的「剪辑流程SOP」只共用 bigram「视频」、「热门内容归因分析」只共用「分析」，bm25 与头名差 6~18 倍。

索引存储：`_meta/search.db`；笔记新增/变更后增量更新（与变更同步流水线联动，见 `04` 第 4 节）。笔记目录不存在或 0 篇时 `build` 直接非 0 退出，不产出空索引。

---

## 5. 打分、排序与融合

- **相关度**：FTS5 内置 `bm25()`（标题命中权重高于正文）；纯标签过滤无关键词时，相关度记中性。
- **时间**：按 `updated`（或 `created`）降序。
- **类型优先级**：可配置权重，如项目拉取时 `教程/案例/SOP > 素材/观点`。
- **多通道融合**：若启用向量通道，标签/FTS/向量结果按文档路径去重合并；简单加权或 RRF（reciprocal rank fusion）排序。默认仅 FTS，不引入 RRF。
- 最终按配方 `rank` 的顺序级联排序（`search_index.run_query` 实现），取 `limit`；`rank` 为空时用默认排序。

---

## 6. 统一拉取入口与输出格式

脚本用法（详见脚本 `--help`）：
```
python scripts/search_index.py build  --kb <kb> [--notes 工作流] [--rebuild]
python scripts/search_index.py pull   --kb <kb> --recipe <path> [--include-stale]
python scripts/search_index.py search --kb <kb> --query "..." [--dim domains=AI]
python scripts/search_index.py search --kb <kb> --topics 选品,关键词
python scripts/search_index.py search --kb <kb> --flow 视频制作 --stage 1_找素材
python scripts/search_index.py search --kb <kb> --query "..." --rank 时间 --rank 类型优先级
python scripts/search_index.py recall --kb <kb> --query "..." [--route-json '<json>'] [--json]
python scripts/search_index.py search --kb <kb> --query "..." --min-bigram-hits 1   # 关闭弱命中门槛
python scripts/search_index.py units  --kb <kb> --type claim --confidence high
```

`stale` 处理：默认过滤 `stale: true` 的笔记，并在输出中打印被过滤数量（非静默）；加 `--include-stale` 可召回，结果标题后标 `[stale]`。

每条结果输出：
| 字段 | 内容 |
|---|---|
| 标题 / 路径 | 笔记标题与相对路径 |
| 一句话 | 笔记开头摘要，快速判相关性 |
| 命中维度 | 满足了哪些维度条件 |
| 标签 | 六维标签（便于二次筛选） |
| 来源 | `sources` 原文路径 |
| 分数 | bm25 / 时间 / 综合排序分 |

返回前不修改任何笔记；检索为只读操作。

---

## 7. 命名视图（模块）

"知识模块"是保存下来的检索条件，不是文件夹。可在 `00_导航/模块视图.md` 登记，例如：
- AI 模块 = `filters: {domains:[AI]}`
- 自媒体模块 = `filters: {forms:[自媒体]}`
- 工具·Codex = `filters: {tools:[Codex]}`

打开视图即跑同一套流水线；视图与项目配方共用条件格式，项目额外带 `exclude/rank/产出目录`。

---

## 8. q_hooks：口语问法（录入侧生成、检索侧优先）

`q_hooks` 是笔记 frontmatter 里的**口语问法**列表——「用户会怎么问这件事」，每篇 **3–5 条**，由 AI 在深抽录入时顺手生成（不额外跑一趟模型）。它和 `topics` 同属内容层，区别是：`topics` 描述"这篇讲了哪几件事"，`q_hooks` 描述"用户会怎么开口问"。

```yaml
topics: [选题池, 对标拆解]
q_hooks:
  - 新号没有粉丝时怎么定前三十篇内容
  - 对标账号该拆它的哪几个维度
  - 为什么照着爆款抄反而没流量
  - 选题池攒到多少条才算够用
```

> 反面示例（都不合格）：「视频爆款分析」是**关键词堆砌**（那是查询串不是问法）、
> 「爆款选题怎么找」是**标题复述**。两者都只覆盖单一角度，且不含本篇特有实词。

**为什么需要**：用户不会用笔记里的书面词提问。笔记正文写"对标账号高播放内容"，用户问"爆款怎么找"——查询 gram 与 bm25 都可能召不回。q_hooks 把口语说法**显式写进索引**，不必引入 embedding 或 jieba。

**索引侧**：`q_hooks` 单独成列（`fts.qhooks`），不混进 `body`；每条 hook 与正文用同一套 `gram_units()` 切分（口径见第 4 节：汉字/假名段出单字 + 2-gram，韩文/泰文段只出 2-gram，字母词段出整词）。**hook 列在索引侧不删停用词**（`to_index_text` 的 `drop_stopwords=False`），删的一侧是查询与分母，见下面的红线。

**命中判定**（实现见 `search_index.matched_hooks()`，常量 `HOOK_GRAM_RATIO` / `HOOK_GRAM_FLOOR`），
满足其一即算命中：

1. 查询串与 hook 串**互相包含**（`q in hook or hook in q`）——覆盖"视频爆款分析"这类与原问法近乎一致的情形；
2. **查询 gram 重合度 ≥ 50%，分母 = 查询**（交集 ÷ 查询的 gram 数；gram 口径见第 4 节）——覆盖"热门内容怎么归因"这类只差虚词的情形。
   **代价要交代**：分母是查询长度，所以**问句越长越容易被摊薄**——一句 19–43 字的自然问话切出 16–34 个
   2-gram，任何一条 hook 都到不了 50%，这条判据单用时长问句恒 0 命中。③ 就是为它补的。
3. **查询 gram 重合度 ≥ 35%，分母 = hook**（交集 ÷ hook 的 gram 数），**且共同 gram ≥ 2**
   ——覆盖"用户整句开口问"：短句对长 hook 的摊薄不该让口语问法失效。

**红线（A1）：停用词不进 ②③ 的分母**。②③ 两侧的 gram 都由 `gram_units(..., drop_stopwords=True)` 产出（实现见 `matched_hooks()`）——否则虚词会同时撑大分母、又充当"共同 gram"。这条判定由 **P12 lang⑨** 守住（含"虚词占分母必假阳性"的对照分支），实测读数：
hook=`what is the price` × 查询 `who can help me with the price of the course`，分母不删停用词时是 4 个 gram（`is/price/the/what`）、共同 2 个 → 0.5 ≥ 0.35 **假阳性命中**；删掉虚词后分母 2 个（`price/what`）、共同 1 个 < 地板 2 → **不命中**。真命中不受影响（hook=`how do I get started` 两侧都命中）。

②③ 是**并列**关系不是替换：只做 ③ 会把路由切出来的短 keywords（"免费诊断 收钱"＝4 个 gram 对
8–16 个 gram 的 hook）打到 0.5 以下，实测 3 条短语查询全灭；只做 ② 则长问句 0 命中。
`共同 gram ≥ 2` 的地板仍然防"只共用一个常见 bigram（如「内容」）就误命中"。

> **阈值出处**：真库首批 8 篇 / 32 条 hook 的阈值扫描（0.5 长问句全灭；0.30 起出现跨笔记误报；
> 0.35 = 长问句开始命中且 4 条无关查询仍 0 命中）。**两个数由 P9 的断言守住**
> （长问句必须 >0、无关查询必须 0、短 keywords 路径不得回归）——**改数必须连探针一起改**，
> 别把这里当自由参数。

**排序优先**：命中的笔记进 `hook` 通道，`hook_paths` 作为**最外层排序键**——先按"是否命中 q_hooks"分组，再比相关度/时间/类型，即 hook 命中**压过** bm25 更高的笔记。同时 bm25 的列权重给 `qhooks` **3.0**（`body` 1.0、`title` 1.0、`dimtext` 0.6、`path` 0.0），未命中时 hook 列也不干扰打分。

> 实测（探针库 12 篇）：查询"视频爆款分析"时，"视频爆款分析方法论"bm25 = **-10.19**（更负更相关），"视频爆款选题方法"bm25 = **-9.62** 但命中 hook，最终后者排第 1。

`q_hooks` 缺失或为空数组时一切照旧、不报错——旧笔记不迁移也能用。

### 8.1 定位：同义召回的口语入口，不是关键词别名表

`q_hooks` 存的是**用户会怎么开口问**，不是「这篇讲了哪些词」。关键词归 `topics` 与六维标签；
把它当别名表填，等于往索引里灌一批和正文同分布的词，起不到同义召回的作用。

生成者是**深抽时的执行 AI**，不是脚本；脚本只校验。完整生成规约与质量红线见
`08_topics_pipeline_units.md` 第 3.5 节。

### 8.2 schema 与校验规则

| 项 | 规则 | 违反时原因码 |
| --- | --- | --- |
| 形态 | 数组（块列表 `- 值`，或内联 `[a, b]`） | `not_array` |
| 条数 | **3–5** 条 | `too_few` / `too_many` |
| 条目 | 纯字符串 | `not_string` |
| 长度 | **6–40 字**（`strip()` 后按 **Unicode 码点**计数；中/英/日/韩任何文字都按 1 字，不折算英文单词。A1 提示：脚本不做 NFC 归一，NFD 写法下每个组合变音符各占 1 格，同一英文词的两种写法可能差 1 格） | `too_short` / `too_long` |
| 去重 | 完全相同**或仅标点差异** | `dup` |
| 换行 | 不含换行 / 换行转义（`\n`） | `newline` |
| 逗号 | 条目内不含 `,` / `，`（内联写法下会被静默切成两条） | `comma_in_item` |
| 空项 | 无空条目 | `empty_item` |
| 角度 | 至少覆盖 3 个不同角度 | **不硬判**，靠规约约束 |

```
python scripts/check_hooks.py --notes-dir 工作流 --warn-log _meta/logs/q_hooks_warnings.jsonl
```

- **阈值写死**在脚本常量里，不提供 `--min-len` 这类放宽开关——红线不为了通过而放宽；
- 校验器**读 raw frontmatter**，不看 `parse_frontmatter` 的归一化结果。原因：检索侧对
  `q_hooks: a, b` 这类非数组写法是**故意宽容**的（按逗号切成列表，见本节上文），校验侧要判
  「模型没按数组输出」就必须看原文——**检索侧宽容、校验侧严格**，这个分工是有意的；
- **退出码**：`0` = 无不合格（`missing` / `empty` 是「待生成」信号，不算失败——降级允许空数组，
  存量笔记按本节上文不迁移）；`1` = 存在不合格；`2` = 用法错误；
- 角度覆盖**不做机械判定**：角度标记不进 frontmatter（一旦落标记就要改 schema、动检索侧），
  由深抽规约约束 + 人工抽检兜底。

### 8.3 降级与覆盖

**降级**（不阻塞入库）：

- 模型生成失败 / 输出非 JSON / 校验不过 → `q_hooks` 写空数组 `[]`，记一条 warning 到
  `_meta/logs/q_hooks_warnings.jsonl`（`doc_id` + 原因码 + 明细）；
- **不允许因为 q_hooks 失败让整篇笔记入库失败**；
- 置空动作由**深抽 AI 执行**：`check_hooks.py` 对笔记零写入权（与 `verify` / `audit` 同族，
  唯一的写动作是 `--warn-log` 指定的日志）。

**覆盖**：

- 笔记入库时 `q_hooks` 缺失或为空数组 → 生成 3–5 条；
- 已有 `q_hooks`（人工或模型写的）→ **默认不覆盖**；
- **增量路径（深抽时）没有开关**——是否覆盖由执行 AI 按 `08` 第 3.5 节的规约判定，不存在
  `--regenerate-hooks` 这个 flag。存量路径要整体重生成，唯一的实体开关是
  `backfill_hooks.py --force`：该开关**全局生效**，本批所有笔记的已有 hooks 都会被覆盖，
  **包括人工写的**——要保住人工 hook 就别开。

**存量回填**（`scripts/backfill_hooks.py`，给旧笔记补齐问法）：

```
python scripts/backfill_hooks.py --notes-dir 工作流 --dry-run        # 只报告，不生成、不写
python scripts/backfill_hooks.py --notes-dir 工作流 --emit-tasks _meta/hooks_tasks.json
python scripts/backfill_hooks.py --notes-dir 工作流                  # 校验 + 写入
python scripts/backfill_hooks.py --notes-dir 工作流 --force          # 覆盖已有
```

- **只补缺**：`q_hooks` 缺失或为空的笔记才处理，已有非空的**默认跳过**；`--force` 才覆盖
  （`--force` 是这个语义在脚本里**唯一真实存在**的开关）；
- **生成者仍是深抽 AI**：脚本用 `--emit-tasks` 导出待补清单（`doc_id` + 标题 + `topics` + 正文），
  模型按 `08_topics_pipeline_units.md` 第 3.5 节生成 hooks 写成 `<kb>/_meta/hooks_backfill.json`，
  脚本再校验落盘——沿用本 skill 既有的「大模型出 JSON、脚本校验后执行」契约（同 `recall --route-json`）；
- **校验复用 `check_hooks.validate_items`**（同一实现，不重写规则）；
- 校验不过 → 该篇置空 `[]` + warning；**单篇失败不阻塞其他篇**；
- 缺 hooks JSON 时 exit 3 并提示先由 AI 生成，不写任何笔记。

> ⚠️ `backfill_hooks.py` 是本 skill 里**第一个会写笔记 frontmatter 的脚本**（只写 `q_hooks` 这一个
> 字段）。增量路径（深抽时）的置空仍由执行 AI 做——脚本零笔记写入权那条边界只对增量路径成立；
> 存量批量回填手改笔记不现实，所以单独开这条路径并在此显式声明。

---

## 9. 查询路由 JSON（大模型 → 脚本契约）

### 9.1 定位与契约

自然语言查询先由大模型转成一份 JSON「路由」，**脚本负责校验和执行**；大模型不直接拼 FTS/SQL。目的：把"意图理解"和"检索执行"分开——大模型可以猜错，但猜错的东西必须被脚本拦住，而不是变成一条能跑通却答非所问的查询。

```json
{
  "keywords": ["视频", "爆款", "分析"],
  "topics": ["爆款分析", "热门内容归因"],
  "flow": null,
  "stage": null,
  "unit_type": null,
  "include_stale": false,
  "need_relations": true,
  "top_k": 10
}
```

### 9.2 字段 schema

**8 个字段全部可选**，缺省取 `ROUTE_DEFAULTS`（下表"默认"列）；没有必填字段，也不接受表外的字段。

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `keywords` | `string[]` | `[]` | 检索关键词；由脚本切**查询 gram**（汉字/假名/韩文/泰文 2-gram，字母词整词），**不要**在大模型侧预切 |
| `topics` | `string[]` | `[]` | 内容主题；**必须是库内已存在的主题**，脚本对照 `_meta/topics.json` 校验 |
| `flow` | `string` \| `null` | `null` | 主轴·工作流过滤；对照索引 `DISTINCT flow`；不确定填 `null` |
| `stage` | `string` \| `null` | `null` | 主轴·环节过滤；对照索引 `DISTINCT stage`，**且与 `flow` 做组合校验**（见 9.3）；不确定填 `null` |
| `unit_type` | `string` \| `null` | `null` | **目前只影响 relation 结果的取舍，不过滤笔记**——填 `claim` 不会把结果收窄到 claim 类笔记，只会让非 `relation` 的取值清空关系输出（第 10 节第 4 步）。真过滤需 join `units_index`，属检索层改动，本轮不做。取值见 `08`；不确定填 `null` |
| `include_stale` | `bool` | `false` | 是否召回 `stale: true` 笔记 |
| `need_relations` | `bool` | `true` | 是否跑 relation 图遍历 |
| `top_k` | `int` | `10` | 1–100 |

`stage` 填什么**以索引里的实际取值为准**（`SELECT DISTINCT stage`）：`render_config.py` 给环节**目录**加
序号前缀（`1_找素材`），而 verify C11 的判定是"目录名以 frontmatter 的 stage 结尾"
（`path_stage_dir.endswith(fm_stage)`），所以 `1_找素材` 和 `找素材` 两种写法都可能合规地出现在库里。
**只有"序号半边"可以省**（乙批 B6）：`render_config` 给目录加序号，库里 `stage` 存的是带序号写法，'
            '所以 `1_找素材` 与 `找素材` 在**校验与过滤两处都等价**（同一个 `_stage_key()`：剥成对引号 → 剥前导序号）；'
            '`flow` / `substage` 仍精确比，**不跟着放宽**。但**仍然别靠猜前缀**——猜错名字照样 `stage_not_found`，'
            '被丢后那层过滤静默消失（好在不再静默空结果，见 9.3）。verify C11 那侧同样先剥成对引号再比（乙批 B5）。

### 9.3 校验规则与原因码

实现见 `search_index.load_route()` / `validate_route()`。**每个失败分支都有稳定原因码**（snake_case，与 `check_hooks.py` 的 `not_array`/`too_few` 一套命名对齐）：

| 级别 | code | 情形 | 处理 |
|---|---|---|---|
| 硬错 | `json_parse_error` | JSON 解析失败；**路由文件不存在** | stderr + **exit 2**，不执行检索 |
| 硬错 | `type_error` | 顶层不是对象；字段类型错；`top_k` 越界或非整数 | stderr + **exit 2**，不执行检索 |
| 硬错 | `route_empty` | `keywords`、`topics`、`--query` 三者全空 | stderr + **exit 2**，不执行检索 |
| 软错 | `unknown_field` | 表外字段 | 忽略该字段，其余照常 |
| 软错 | `topic_not_found` | `topics.json` 里没有该主题 | 丢弃该值，**绝不编造** |
| 软错 | `topics_unverifiable` | `_meta/topics.json` 不存在，无从比对 | **整个 `topics` 丢弃** + warning |
| 软错 | `flow_not_found` | 库内无此 flow | 丢弃，回落为不按 flow 过滤 |
| 软错 | `stage_not_found` | 库内无此 stage（**带/不带序号视为同一**，B6） | 丢弃，回落为不按 stage 过滤 |
| 软错 | `stage_flow_mismatch` | stage 存在、flow 也存在，但**该 flow 下没有这个 stage** | **丢 stage、保留 flow**，warning 里附该 flow 的真实 stage 列表 |
| 软错 | `unit_type_invalid` | 不在受控 units 类型里 | 丢弃该值 |

**退出码口径（不得漂移）**：

- 软错 **rc=0**——降级是设计里的成功路径，不是失败。丢了 5 个字段也还是 0；调用方**靠 `warnings` 判读，不靠退出码**；
- 硬错 **rc=2**，与 argparse 用法错误同源；
- 未给路由 JSON 时的**退化路由**（只拿 `--query` 切查询 gram）**不走校验**，因此也不会产生 warning。

**软错落盘**：`_meta/logs/route_warnings.jsonl`，每行
`{"ts","query","code","detail","severity"}`，`sort_keys`、**追加不覆盖**；
`ts` 用**带时区的 ISO**（同 `build_topics.py` 的 `generated_at`），不用无时区本地时间——
跨机器/跨时区 diff 需要可比的时间戳。

> ⚠️ **硬错一行都不落**，这条是刻意的：落盘点位于「`route_empty` 硬错检查之后、检索执行之前」，
> 所以「软错 + 硬错并存」时硬错赢、整条不执行、日志里**不会留下那次软错的痕迹**。
> 语义是"没执行就没有可追溯的降级结果"。别把它"修"成先落盘再退出。
> 无 warning 时不建文件、不产生空文件（与 `fts_filtered.jsonl` 同惯例）。

软错之所以只丢不报错，是因为大模型的"猜测值"最典型：主题名靠印象拼（"爆款分析" vs 库里的"爆款"）。丢掉它，2-gram 与 q_hooks 通道仍能召回；报错则会让一次本可用的检索直接失败。

**flow × stage 为什么要组合校验**：两个值各自查存在性时，`flow=视频制作 + stage=1_开场`（`1_开场` 属于另一个工作流）会双双通过校验，而过滤是 AND——结果恒为 0 条且**不带任何提示**，看起来像"库里没有相关内容"。组合不存在时丢 stage 留 flow，宁可少一层过滤，也不要静默空结果。

```
$ search_index.py recall --kb kb --query "视频爆款分析" --route-json '{ ... "topics": ["爆款分析","热门内容归因"] ... }'
[recall][校验] (topic_not_found) 丢弃不存在的 topic ['爆款分析', '热门内容归因']（topics.json 无此项，不编造）
[recall] 校验日志：kb/_meta/logs/route_warnings.jsonl
```

### 9.4 生成规约（深抽/问答时的执行 AI 遵守）

路由 JSON 的**生成者是模型**，脚本不生成、不猜、不补。本节是写给模型看的约束，与 9.3 写给脚本看的校验互补。

**输入上下文**：用户原话（一句话查询）。**不要**只看自己印象里的库结构就填值。

**出路由前该知道的两份事实**：主题取值以 `_meta/topics.json`（渲染版 `00_导航/主题地图.md`）为准；flow/stage 取值以索引实际值为准。warning 的 `detail` 里也会附上可选值列表——那是**上一次猜错时的纠正依据**，不是第一次凭空填值的借口。

**输出格式**：9.2 的 8 字段对象，一次给全（不确定的显式写 `null`）。

**红线（逐条遵守）**：

1. **不确定的字段填 `null`**，**禁止编造不存在的 topic / flow / stage / unit_type**——填错只会静默扩大结果，填 `null` 是安全侧；
2. **禁止凭印象拼名字**：主题名"爆款分析"而库里实际是"爆款"这类，是软错的头号来源；
3. **`keywords` 给实词，不给泛化词**：`分析/内容/视频/方法` 这类高频泛化词命中一切又什么都不指向（同 A4 泛化 bigram 的判据），一篇里特有的实词才值得进 `keywords`；
4. **口语问法不塞进 `keywords`**——那是 `q_hooks` 的活，由脚本匹配（第 8 节）；把问句塞进 keywords 等于绕过 q_hooks 通道；
5. 关键词**交给脚本切查询 gram**（口径见第 4 节），模型侧不预切；
6. 模型**只产出 JSON，不产出 FTS 查询串、不产出 SQL**。

**降级路径**：硬错 exit 2（整条不执行）；软错丢值继续（rc=0）。两级的定义见 9.3。

**责任分工（warning 出现后谁做什么）**

判据只有一条，**不是按 code 名字点名**：**看降级之后，被这条 warning 质疑的那个过滤器还在不在生效。**
底层是两类完全不同的字段——

- `flow` / `stage` 是**硬过滤**：`d["flow"] != route["flow"]` 直接把笔记**排除**。填错的后果是结果集**来自错语境**，而且表面看不出问题；
- `topics` / `unit_type` 是**扩展与取舍**：命中就往该通道里**加**。填错的后果只是**少一路召回**，主干 FTS / q_hooks 命中不受影响，不会误导。

于是：被质疑的值**被丢掉** → 结果只是变小 → 接受降级；被质疑的半边**仍然生效** → 答案会静默收窄到可能错的语境 → 必须重出。

| 情形 | 判据落点 | 做什么 |
|---|---|---|
| `topic_not_found` / `topics_unverifiable` / `flow_not_found` / `stage_not_found` / `unit_type_invalid` | 被质疑的值已经丢掉，没有可疑过滤器残留 | **接受降级结果直接作答**，并说明"按 X 收窄未生效"。**禁止**为了凑一个 topic 去猜近义名——那正是 9.5 第 1 条拒绝的模糊匹配，会把用户显式的收窄条件静默换成另一个主题 |
| `stage_flow_mismatch` | **唯一一条**"被质疑的半边（flow）在降级后仍然生效"：模型一边填 `flow=视频制作`、一边填了属于别的工作流的 stage，说明这两半到底哪半错它自己也不知道 | **必须重出**：要么按 `detail` 给的该 flow 真实 stage 列表改 stage，要么把 flow 改成该 stage 所属的工作流。**不要**拿 flow-only 的结果作答——那比 0 命中更危险，0 命中至少还会逼调用方回头 |
| `unknown_field` | 整个字段被忽略 = 少表达一层意图，但通常不改变结果集 | 结果正常就照答；**结果偏少或为 0** 时按 `detail` 里的合法字段名列表重出。（带 `--query` 时 `keywords` 丢失一般无感；不带 `--query` 会直接撞 `route_empty` 硬错，那时必须重出） |
| 结果为 0 条且 `warnings` 非空 | 任何软错把结果打到空 | 按 `detail` 的可选值列表**重出一版**；仍 0 条才回退到纯 `--query` 自然语言 |
| 硬错 exit 2 | 整条未执行 | 读 stderr 的 code + 原因，**改正后重跑**；不盲目重试 |
| 重试 | — | 脚本**不重试、不重问模型**，也没有重试次数配置——重试归**调用方**（模型/上层流程） |

### 9.5 一致性说明与不做的事

**为什么 topics 严格匹配、relation 端点却允许子串模糊匹配**（下轮别当成不一致来"修"）：

| | `topics`（路由键） | relation 端点（内容匹配） |
|---|---|---|
| 角色 | **用户/模型显式指定的过滤条件** | 图遍历的**触达判断**，两端本来就由自然语言短语写成 |
| 匹配 | **精确相等**，比对 `_meta/topics.json` | **子串包含**（`s in node or node in s`） |
| 模糊的后果 | 静默把用户的收窄条件换成另一个主题的召回，且看起来像本来就该这样 | 扩大触达面正是目的——"爆款和热门内容什么关系"要能匹配到节点"爆款" |

一句话：**路由键必须精确，内容匹配允许子串**。同一条链路上还有第三处口径——`search_index.py search`
的 `--flow/--stage/--substage` **目前不做存在性校验**（拼错即静默 0 条、无 warning），与 recall 不同源；
这是**已登记的缺口**，见本节末尾"留待下一轮"，别把它当成"recall 也会拦"来依赖。

**不做的事（写死，防止下一轮被当缺口补）**：

1. **不做 topic 模糊匹配 / 别名自动归一**：会静默扩大召回，正面违背"绝不编造"。主题归并候选已由 `build_topics.py` 的 `merge_candidates` + **人工确认**承担（`08` 第 1 节），检索侧不再猜第二遍；
2. **不在脚本里自动重问模型**（脚本内起子进程/循环调模型重出路由）：脚本无生成权是全局边界，破了它路由契约就退化成"脚本兜底猜测"。重试归调用方（9.4 责任表）；
3. **不引入 JSON Schema / jsonschema 依赖**：零依赖是硬约束（`10_audit.md` 第 5 节），`validate_route()` 手写校验足够；要的是把 9.2/9.3 两张表写全，不是换校验引擎；
4. **不把 `unit_type` 做成真正的笔记过滤**：需 join `units_index`，属检索层改动。当前它只是 relation 输出的取舍开关，9.2 的表述就是唯一事实。

> 与本次同批登记、**本轮不做**的两项（留待下一轮）：`search` 子命令的 `--flow/--stage` 同口径校验；字段名拼错时给相近字段建议。另：`fts_filtered.jsonl` 的 `ts` 是无时区本地时间，属**待统一格式**——不在本轮改，旧日志里已是本地时间，直接切换会造成新旧格式混杂，需要一次专门迁移。

---

## 10. recall：四通道合并检索

```
search_index.py recall --kb <kb> --query "视频爆款分析" [--route-json '<json>'] [--json] [--hops 1]
```

一条命令跑完整条链路：

| 步 | 动作 | 产出通道 |
|---|---|---|
| 0 | 读路由 JSON；未给 `--route-json` 时退化为"仅用原查询切查询 gram" | — |
| 1 | FTS 查询 gram OR 检索（`keywords` + `--query`）+ 弱命中门槛（第 4 节） | `fts` |
| 2 | q_hooks 匹配（第 8 节） | `hook` |
| 3 | topics 扩展：种子 = 路由 `topics` ∪ 核心笔记的 topics | `topic` |
| 4 | relation 图遍历（`units.jsonl`，默认 1 跳） | `relation` |
| 5 | 合并去重、排序，输出笔记 + 关联结果 | — |

**通道权重**：`hook 4 > fts 3 > topic 2 > relation 1`；一篇笔记取**所命中的最高通道权重**作为 `weight`。

**排序链**：`weight` 降序 → `bm25` 升序（更负更相关）→ `updated` 降序。

**第 3 步的种子只取"核心笔记"**（q_hooks 命中 + FTS 前 2 名）的 topics，不取全部 FTS 命中的 topics。否则尾部弱命中（例如只靠 `forms: 视频` 命中的剪辑类笔记）会把主题扩展带偏——实测在 11 篇探针库上，放宽后"剪辑"会混进种子，多带出无关笔记。

**第 4 步图遍历**：只读 `_meta/units.jsonl` 里 `type: relation` 的单元，**不读笔记正文的 `[[ ]]`**
（explicit 边不是检索通道，见第 3 节的说明）。从种子（路由 topics ∪ keywords ∪ 核心笔记 topics）出发，沿 `units.jsonl` 中 `type: relation` 的单元走 `hops` 跳；端点匹配用**子串包含**（`s in node or node in s`），因此查询串"爆款和热门内容什么关系"能直接匹配到节点"爆款"/"热门内容"。命中的 relation 单元按其 `doc_id` 映射回笔记，该笔记进 `relation` 通道。末尾「关联概念」只列 **relation 边端点**，不含种子词本身——否则原始关键词会被误当成"关联概念"。

**输出**：按通道标记 `[hook+fts+topic+relation]`，命中的笔记额外打印「命中问法」与「主题命中」；末尾给「关联结果」（命中的 relation 边）与「关联概念」。加 `--json` 输出机器可读结构（`route` / `warnings` / `hits[].channels/weight/bm25/matched_hooks/matched_topics` / `relations`），供大模型二次组织答案。

**`warnings[]` 每项是结构化对象** `{code, detail, severity}`（原因码见第 9.3 节；文本模式下渲染为
`[recall][校验] (code) detail`）；同一批 warning 会追加落 `_meta/logs/route_warnings.jsonl`。
**软错不改退出码**——`rc=0` 时也可能带 warning，调用方必须读 `warnings` 判读，不能只看 rc。

```
$ search_index.py recall --kb kb --query "视频爆款分析"
 1. 视频爆款选题方法  [hook+fts+topic+relation]  [-4.969]
     命中问法: 视频爆款分析; 怎么做爆款视频
     主题命中: ['爆款', '选题']
 2. 视频爆款分析方法论  [fts+topic]  [-4.997]

## 关联结果（relation 图遍历 1 跳，1 条）
- 爆款 —依赖→ 选题   [doc-1-relation-1]
```

`need_relations: false` 时跳过第 4 步；`include_stale: true` 时 stale 笔记参与召回并标 `[stale]`。

第 1 步的弱命中门槛只压 FTS 通道：被滤掉的弱命中若命中 q_hooks、或落在 topics 扩展/relation 端点里，仍会被补回并进入结果（输出里报「其他通道补回 N 条」）。

---

## 11. 向量检索预留（渐进式，默认关闭）

- 触发：FTS5 用顺后，出现"换个说法/近义词召回不到"的明确痛点再启用。当前 P0 明确不引入向量。
- 做法：对笔记 `title+摘要+正文` 生成 embedding，存 `_meta/vectors.db`（或向量库）；作为流水线第 ③ 通道，与 FTS 结果融合重排。
- 依赖：需要本地模型或 embedding API、可能的额外包；启用前评估成本与隐私（内部资料不外发）。
- 不因为"上 RAG 更高级"而默认启用；以黄金查询集（`07`）的实测收益作为是否引入的依据。
