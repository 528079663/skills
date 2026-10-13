# 10 · audit —— 知识库诊断度量（只读）

> **audit 是 skill 自带的 X 光机，不负责开药方。**
> 它只报「是什么」——分布与信号；不报「该补哪条边」「该完善什么元数据」——那是人 / 下一轮的事。

## 1. 与 verify 的边界（不许互相抢活）

| | `verify.py` | `audit.py` |
|---|---|---|
| 性质 | **二值门禁** | **诊断度量** |
| 输出 | `[PASS]/[WARN]/[FAIL]` 逐项 | 分布 + 信号 + 样例 |
| 给谁看 | CI / 交付验收（exit code） | 人（判断库健不健康、往哪看） |
| 会改文件吗 | **只写 `_meta/` 下两样**：`--out` 的 JSON 报告、`--snapshot-source` 的源目录基线。**没有 `--fix`**，永不写笔记 / units / topics.json / 索引 / 源资料 | **永远不改**，也没有 `--fix` |
| 索引缺失时 | C12 **FAIL**（0 篇不放行） | A6 标 **N/A**（不 FAIL） |
| 会不会给结论 | 会（放行 / 不放行） | 不会（只给度量，不下判断） |

- **audit 不抢 verify 的活**：不判 PASS/FAIL、不设 exit code 语义、不做交付门禁。
- **verify 不揽 audit 的活**：门禁只回答「能不能放行」，不解释分布，也不输出直方图/倒排表。
- 二者**共用同一份** C12 判定实现：`verify.check_index_consistency(kb, notes_dir=None)`。audit 的 A6 直接调它，不重复实现磁盘比对逻辑。

## 2. CLI

```
python scripts/audit.py [--notes-dir DIR] [--format markdown|json] [--out FILE]
                        [--bigram-df-threshold F] [--min-q-hooks N] [--top-n N]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--notes-dir` | `工作流`（`search_index.DEFAULT_NOTES_DIR`） | **笔记目录本身**；KB 根取其**父目录**，`_meta/` 从 KB 根解析。默认值口径与 `build` / `build_topics` 一致。 |
| `--format` | `markdown` | `markdown` 给人看；`json` 机器可读、便于长期追踪趋势 |
| `--out` | 无（写 stdout） | 报告落盘路径；**落在被审计目录内会被拒绝（exit 2）** |
| `--graph-mode` | `both` | A1 的图口径：`explicit`（笔记→笔记显式连线）/ `concept`（relation × topic 命中）/ `both`（**两张图分别统计、不合并**） |
| `--bigram-df-threshold` | `0.5` | A4 泛化 bigram 的 DF / 总篇数 阈值 |
| `--min-q-hooks` | `3` | A3 判定「条数偏少」的门槛 |
| `--top-n` | `5` | 各节样例条数 |

> ⚠️ **布局硬约束（不得漂移）**：audit 假定 `_meta/` 就在**笔记目录的父目录**下。若哪天布局变成
> `kb/content/notes/` + `kb/_meta/`（父目录不再是 KB 根），本推断即失效——此时 A6 会标 `na`（找不到
> 索引）、A1 会退化成空 relation 图。**这是已知边界，不做自动探测**；真要支持该布局，必须显式改
> CLI 契约（加 `--kb`），而不是让「父目录」这句悄悄漂移。

**主库 / 探针库 / 临时库用 `--notes-dir` 显式区分**，报告抬头会注明扫的是哪个目录：

```
python scripts/audit.py --notes-dir 工作流                          # 主库（cwd 为 KB 根）
python scripts/audit.py --notes-dir probe3/kb/工作流                # 探针库
python scripts/audit.py --notes-dir probe3/kb/工作流 --format json --out /tmp/a.json
```

## 3. 检查项（六项独立给分与分布，不合并成单一健康分）

### A1 relation 连通性

A1 拆成**两张互不合并的图**（`--graph-mode`，默认 `both`）。两张图的「孤岛」含义完全不同：
explicit 孤岛只说明**该篇没有引用跳转**；**concept 孤岛＝未经由 relation 端点连接的篇目，
与 topic 是否共享无关**（topic 命中只是建边的**必要条件之一**，见下面第 ② 张图的定义）。
两张图**不合并成一个数**——合并会把两种不同成因混成同一格，失去分辨率。

> **concept 图在 units 关闭时是空读数**（发现 18 定稿）：没有 relation 单元就没有任何建边来源，
> concept 必然**恒 0 边、全部孤岛**。这不是「库里没有概念桥」，而是**定义决定的**。
> 此时要看概念聚合度，请读 **A2 的 topic 共享数**，不要拿 A1 concept 的孤岛数说事。
> 真库实测：A2 有共享主题「DeepSeek」2 篇，而 A1 concept 仍 0 边——就是这个空读数的样子。

> **A1 explicit 是诊断指标，不是通过条件。**
>
> - audit **不判 PASS/FAIL**，exit code 里也不含图的信息（`--format json` 只出数）；边数 0 与边数 100
>   在 audit 眼里只是两个分布，**都不报错、都不告警**；
> - verify 侧也**不看**边数：C10 只校验`[[目标]]`**能不能解析到一篇现有笔记**，一个 `[[ ]]` 都没有时
>   C10 直接 PASS（本文件第 1 节的 verify/audit 边界，以及 `08_topics_pipeline_units.md` 第 3.6 节）；
> - **孤岛是合法状态**。笔记间双链的规约是「只有正文明确引用、且读者需要跳转才加链，
>   不得为每篇主动寻找关联，允许笔记保持孤岛」（`08_topics_pipeline_units.md` 第 3.6 节）。
>   因此"孤岛多"**不等于**"库有病"，也不构成任何补链任务；
> - **禁止**把 A1 explicit 演化成通过条件——不新增「每篇必须有出链/入链」「图必须连通」
>   「边密度低于阈值即告警」这类规则。真要加这种规则，得先推翻第 3.6 节的规约。
>
> explicit 图的正当用途只有一个：当有人怀疑"深抽时该加链没加、或加了一堆无意义链"时，
> 用它看**分布是否反常**（例如边数突然暴涨到每篇都好几条，多半是有人在硬凑关联）。

**① explicit 图 —— 笔记 → 笔记的直接指向**

- 边来源两个，**分别计数、分别列出**：
  1. `wikilink`：正文里的 `[[目标]]` 双链解析到本库笔记（去掉 `|别名` 与 `#锚点`）；
  2. `relation_endpoint`：relation 单元的 `subject` / `object` 解析到本库笔记（≠ 断言方）。
- 名字解析复用 `search_index._unit_doc_path` 的三种匹配：路径 / 文件名（含去后缀）/ 标题。
- **出度** = 该笔记发出的显式指向数；**入度** = 指向它的显式指向数；**度数 = 出 + 入**。
- 回答：**笔记之间有没有真连线**。

**② concept 图 —— relation 断言 × topic 命中**

- 一条 relation 单元 `u`（`doc_id` 所属笔记为 A）在 A 与 B 之间建一条**无向边**，其中 B 是
  **`topics` 里含 `u.subject` 或 `u.object`** 的其他笔记。
- **标题 / 文件名匹配不再参与任何一张图**。它**不是**显式边——除非被 `[[ ]]` 或 relation 端点
  **实际引用**。它原本是 concept 图里的一条弱归属（端点恰好等于某篇笔记的标题/文件名即算命中），
  现已剔除，避免 concept 图被标题字面污染；剔除后 concept 的「归属」只由 topic 承担。
- **出度(A)** = A 作为 `doc_id` 断言的 relation 单元数；**入度(B)** = 端点概念落在 B 的 topic 上的次数。
- 回答：**在 units 开启且存在 relation 单元时**，回答「笔记之间有没有经由 concept relation 的连接」；
  **units 关闭时这张图恒空**（建边来源只有 relation 单元），此时要看「概念桥」请读 **A2 的 topic 共享数**。

两张图各自输出：边数（含来源拆分）、连通分量数与最大分量占比、孤岛数与列表、度数分布直方图（人读）、
每篇 `doc_id` 的度数（json `degrees`）。另有 `doc_id` 解析不到笔记的 relation 单元列表。

> 实测对照（探针库 13 篇）：explicit 孤岛 **13**（全库没有一条 `[[ ]]`、也没有一条端点指向笔记的
> relation——「笔记之间一条真连线都没有」），concept 孤岛 **6**。合成一个数只会得到「6」，把
> 「连真连线都没有」这条更重要的事实盖掉。

### A2 topic 结构

独占 topic（只被 1 篇用）数、共享 topic（≥2 篇）数、无 topic 的笔记数、`topic → 篇数` 倒排表。

### A3 q_hooks 覆盖率

有 q_hooks 的笔记数 / 总篇数、条数分布、**有 q_hooks 但条数 < `--min-q-hooks`** 的笔记列表、完全没有 q_hooks 的笔记列表。

### A4 泛化 bigram

- 口径：每篇笔记取「标题 + 正文 + 六维字段 + q_hooks」里**由 n-gram 段产出的 2 gram** 集合（`search_index.gram_units`，滑动窗口；判据是 `NGRAM_SEG_RE.fullmatch(g)`，与分词口径同源，A1）。覆盖汉字/假名/韩文/泰文四类段；**字母词与数字整段 token 不参与 DF 阈值判定**（长度恰好为 2 的整词如 `ai` 不会被误认成 bigram）。跨脚本相邻不产跨段 gram。
- DF = 含该 bigram 的笔记数；**DF / 总篇数 ≥ `--bigram-df-threshold`** 即判为泛化 bigram。
- 输出：泛化 bigram 表（按 DF 降序）+ 每篇笔记的泛化 bigram 占比。

> 实测意义：模板里的三段分标（`资料原话` / `归纳结论`）会让 `原话`、`归纳`、`料原`、`纳结` 这类 bigram 在**每一篇**都出现（DF = 总篇数）——它们不携带任何区分度，正是门槛该拦的对象。

### A5 stale / 过期

带 `stale: true` 的笔记数、占比、列表（含 `updated`）。

### A6 索引一致性（只读，不 rebuild）

直接引用 `verify.check_index_consistency()` 的结论，**不重复实现磁盘比对逻辑**：

- `pass` / `fail` 的含义与 verify 的 C12 逐字一致；
- **索引不存在 → `na`（N/A），不 FAIL**——这是 audit 与 verify 的口径差异，也是两者边界的关键一条。

## 4. 输出 schema（json，字段名固定，便于 diff 追踪趋势）

```json
{
  "audit_version": 2,
  "notes_dir": "probe3/kb/工作流",
  "kb_root": "probe3/kb",
  "notes_total": 13,
  "thresholds": {"bigram_df_threshold": 0.5, "min_q_hooks": 3, "top_n": 5,
                 "graph_mode": "both"},
  "A1_relation_connectivity": {
    "graph_mode": "both",
    "notes_total": 13, "relation_units": 3, "unresolved_doc_ids": [],
    "explicit": {
      "edges": 0, "edges_by_source": {"wikilink": 0, "relation_endpoint": 0},
      "components": 13, "largest_component": 1, "largest_component_ratio": 0.0769,
      "isolated_count": 13, "isolated": ["..."], "isolated_top": ["..."],
      "degree_histogram": {"0": 13},
      "degrees": [{"doc_id": "...", "out": 0, "in": 0, "degree": 0}]
    },
    "concept": {
      "edges": 4, "edges_by_source": {"topic_hit": 4},
      "components": 9, "largest_component": 5, "largest_component_ratio": 0.3846,
      "isolated_count": 6, "isolated": ["..."], "isolated_top": ["..."],
      "degree_histogram": {"0": 6, "1": 7},
      "degrees": [{"doc_id": "...", "out": 1, "in": 0, "degree": 1}]
    }
  },
  "A2_topic_structure": {
    "topics_total": 14, "exclusive_count": 12, "shared_count": 2,
    "exclusive": ["..."], "notes_without_topic": 0, "notes_without_topic_list": [],
    "notes_without_topic_top": [],
    "inverted": [{"topic": "选题", "docs": 4, "doc_ids": ["..."]}],
    "inverted_top": []
  },
  "A3_q_hooks_coverage": {
    "notes_total": 13, "with_q_hooks": 13, "coverage": 1.0, "min_q_hooks": 3,
    "below_min_count": 10, "below_min": [{"doc_id": "...", "count": 2}], "below_min_top": [],
    "missing_count": 0, "missing": [], "missing_top": [], "count_histogram": {"1": 2}
  },
  "A4_generic_bigram": {
    "threshold": 0.5, "bigram_total": 288, "generic_count": 14,
    "generic": [{"gram": "原话", "df": 13, "ratio": 1.0}], "generic_top": [],
    "notes_generic_ratio": [{"doc_id": "...", "grams": 34, "generic": 14, "ratio": 0.4118}],
    "notes_generic_ratio_top": []
  },
  "A5_stale": {
    "notes_total": 13, "stale_count": 1, "ratio": 0.0769,
    "stale": [{"doc_id": "...", "updated": "2026-01-05"}], "stale_top": []
  },
  "A6_index_consistency": {"status": "pass", "message": "schema v3；索引 13 篇 = 磁盘 13 篇"}
}
```

- `*_top` 是给人看的样例切片（长度 `top_n`），不带后缀的字段是**全量**。
- `A1_relation_connectivity.explicit` / `.concept` 是两张**独立**的图，字段结构相同；`--graph-mode`
  选单模式时，**另一张图的键为 `null`**（不输出、不合并）。
- `edges_by_source` 是**来源计数**（不去重）：同一对笔记既有双链又有端点指向时，边只算 1 条，
  来源计 2 次。
- 比率在分母为 0 时写 `null`（markdown 显示 `—`），**不伪造 0**。
- 阈值原样出现在 `thresholds` 与报告抬头，便于复现。

## 5. 硬约束

1. **只读**：不调用 `build` / `build_topics` / `search_index build`，也不调用 `verify --snapshot-source`
   （那是 verify **唯一**会写 `_meta/source_snapshot.json` 的入口，audit 不触发它）；不写被审计库的 `.md` / `units.jsonl` / `topics.json` / 索引。
2. **可复跑**：两次运行输出**逐字节一致**——`doc_id` 全排序、json `sort_keys=True`、**不打时间戳**。
3. **零新依赖**：只用标准库 + 同目录的 `search_index.py` / `verify.py`。
4. **空库**：0 篇时输出空分布、exit 0，不崩、不写空文件。
5. **`--out` 护栏**：输出路径落在被审计目录内直接拒绝（exit 2）。
6. **布局约束**：`_meta/` 必须在笔记目录的**父目录**下（见第 2 节的 ⚠️）。这条写死，不许漂移。
7. **不给处方**：报告里不出现「建议完善元数据」这类空话，也不出现「该补哪条边」。

## 6. 不做的事

- 不自动补边、补 topic、补 q_hooks；
- **不新增边密度 / 连通性校验**：不要求「每篇必须有出链或入链」、不要求「图必须连通」、
  不设「孤岛数上限」；A1 explicit 的边数与孤岛数永远只是分布（见第 3 节 A1 的定性说明）；
- **不做笔记间双链的补链 / 生成**——链由深抽时的执行 AI 按 `08_topics_pipeline_units.md` 第 3.6 节
  规约决定，audit 与 verify 都不负责把它造出来（也不提供 `--link` 这类能力）；
- 不调用 verify 的修复路径；
- 不把 audit 结果写回主库；
- 不做成「一次性针对当前库的报告」——它是通用子命令，换任何 `--notes-dir` 都要能用。

## 7. 巡检用法（手动，先不自动化）

audit 不做趋势追踪、不存历史——**巡检 = 自己定期跑一次 json、拿两次结果 diff**。不需要新代码：

```bash
# 每次知识库有较大变更后（文件名自己填当次日期——不给 shell 内插，跨平台都能照抄）
python scripts/audit.py --notes-dir 工作流 --format json --out audit/20261006.json
```

**比两期 = 语义比较（推荐）**：只用标准库，跨平台，**不依赖 jq**。

```bash
python -c "import json;a=json.load(open('audit/20261002.json',encoding='utf-8'));b=json.load(open('audit/20261009.json',encoding='utf-8'));print('无变化' if a==b else '有变化')"
```

**要看具体差异行**：先归一化（键排序 + 中文不转义成 `\uXXXX`），再比。

```bash
# POSIX / Git Bash
N='import json,sys;print(json.dumps(json.load(sys.stdin),ensure_ascii=False,sort_keys=True,indent=2))'
python -c "$N" < audit/20261002.json > a.norm.json
python -c "$N" < audit/20261009.json > b.norm.json
diff a.norm.json b.norm.json
```

```powershell
# PowerShell 不支持 `<` 输入重定向，改走管道；差异用 Compare-Object
$N = 'import json,sys;print(json.dumps(json.load(sys.stdin),ensure_ascii=False,sort_keys=True,indent=2))'
Get-Content audit/20261002.json -Raw | python -c $N | Set-Content a.norm.json -Encoding utf8
Get-Content audit/20261009.json -Raw | python -c $N | Set-Content b.norm.json -Encoding utf8
Compare-Object (Get-Content a.norm.json) (Get-Content b.norm.json)
```

**为什么不直接 `diff` 原始文件**：audit 保证的是**同一份输入两次运行输出逐字节一致**（已验），但
**两次不同输入之间**字段顺序不必保证（如 `degree_histogram` 的键集合会随数据变化）——直接 diff 会天天
噪声报警。语义比较（字典相等）天然免疫键序；要行级差异就先 `sort_keys=True` 归一化再比。
**这里不给 `jq` 依赖**：零第三方依赖是本工具的硬约束（第 5 节），上面两条只用标准库。

看 diff 时只盯四个数：

| 指标 | 往哪走算坏 |
|---|---|
| A1 explicit 边数 | **只有一侧可疑**：突然暴涨（每篇好几条）多半是有人在硬凑关联；**孤岛数上升不算坏**——规约允许孤岛，链少而准正是 `08` 第 3.6 节想要的结果 |
| A1 concept 连通分量数 | **上升** |
| A4 泛化 bigram DF 榜首 | **上升**（说明又混进模板味） |
| A3 q_hooks 覆盖率 | **下降** |

其余都是诊断参考，不设阈值——audit 只报数，判读在人。

> explicit 这一行**不设"孤岛数下降"这类目标**，否则就是在鼓励补链，与第 3.6 节规约冲突。
> 要看引用质量，只能回正文抽查：这条链对应的正文是不是真的引用了那篇。

> 先手动跑两周，看自己会不会真的看。会看，再谈 CI；不会看，自动化了也是死文件。
