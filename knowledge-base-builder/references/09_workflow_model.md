# 09 · 工作流 / 环节 / 子分组模型

> 本文件定义知识库的主轴模型：工作流（flow）→ 环节（stage）→ 子分组（substage），物理目录结构、frontmatter 字段、Step 4 展示格式、检索方式与迁移路径。六维标签与 units 是辅助层，见 `05_multidim_model.md`、`08_topics_pipeline_units.md`。

## 1. 为什么主轴是工作流而不是标签

- 标签回答"这篇笔记有什么属性"，不回答"这篇笔记帮我做哪件事"；
- 用户打开知识库是为了做事（找素材/写文案/做视频），不是为了查标签组合；
- 因此物理目录直接体现工作流，打开文件夹就看到"下一步该干嘛"。

## 2. 三层定义

### 2.1 flow（工作流）

- 你"要做哪些事"，如：视频制作、B站好物、公众号写作；
- 物理目录：`工作流/<flow>/`；
- 一篇原子笔记归 **1 个主 flow**；
- 来源：用户问卷 Q1，或 AI 从资料归纳后人工确认。

### 2.2 stage（环节）

- 一个工作流按做事顺序分几步，如视频制作：1 找素材 → 2 写文案 → 3 做视频 → 4 发布；
- 物理目录：`工作流/<flow>/<n>_<stage>/`（n 是序号前缀）；
- 一篇原子笔记归 **1 个主 stage**；
- 来源：用户问卷 Q2，或 AI 从资料章节归纳。

### 2.3 substage（子分组，固定 5 值）

- 环节内部的笔记分组，固定为：`总览` / `子技巧` / `案例` / `工具` / `坑`；
- 不自由生长；在该环节的 `_总览.md` 里按这 5 组聚合；
- 一篇原子笔记归 **1 个 substage**。

## 3. 物理目录结构

```
工作流/
└── <flow>/
    ├── _流程.md                  ← 环节顺序 + 关键 SOP（build_flows.py 生成）
    ├── 1_<stage>/
    │   ├── _总览.md              ← 按 substage 5 组聚合（build_flows.py 生成）
    │   └── <原子笔记>.md
    └── 2_<stage>/
概念索引/                          ← units 产物（辅助层）
素材库/
└── _来源地图/                    ← 来源笔记（文档级）
```

## 4. frontmatter 字段

```yaml
---
# 主轴（决定物理位置，必填）
flow: 视频制作
stage: 1_找素材
substage: 子技巧
# 辅助层（跨工作流检索，可选）
domains: [商业]
forms: [自媒体]
tools: []
types: [方法]
projects: [AI自媒体]
topics: [选品, 关键词]
# 溯源与质量（必填）
sources: [素材库/.../原文.md]
source_locator:            # block 列表，首项 = 主块；跨块的语义单元把其余块按引用顺序列在后面
  - §章节#char=起始-结束
confidence: high
status: confirmed
---
```

## 5. Step 4 方案评审展示格式

向用户展示工作流目录树：

```
工作流/
├── 视频制作/
│   ├── 1_找素材/        ← 选品逻辑、关键词检索、对标账号分析
│   ├── 2_写文案/        ← 开头钩子、脚本结构、标题模板
│   ├── 3_做视频/        ← 剪辑流程、配音、字幕
│   └── 4_发布/          ← 平台规则、发布时间、数据复盘
└── B站好物/
    ├── 1_选品/
    ├── 2_制作/
    └── 3_发布/
```

并显式标注：
- 每个 flow 的环节顺序与依据；
- 笔记粒度（按语义单元拆篇 / 粗）；
- substage 5 组如何映射；
- 辅助层开关（六维标签/主题层/units）；
- 所有默认项（用户答"你建议"的）。

## 6. 笔记粒度规则

- 一个高价值块 → N 篇原子笔记（N≥1，粒度单位是语义单元，块只是输入容器）→ 每篇归 1 个主环节；
- 一篇文档讲 3 个环节 → ≥3 篇原子笔记 + 1 篇来源笔记；
- 低密度块不深抽，在 doc_map 记 skip；
- 跨环节的语义单元以"主要教什么"归主环节，**不重复建**；跨环节的可发现性由六维辅助标签 / `topics`
  与 units 的 `relation` 单元承担，**不靠 `[[链接]]`**（正文双链只表示引用跳转，
  见 `08_topics_pipeline_units.md` 第 3.6 节）。

## 7. 检索方式

```bash
# 按工作流/环节/子分组拉取（主轴）
search_index.py search --kb <kb> --flow 视频制作
search_index.py search --kb <kb> --flow 视频制作 --stage 1_找素材
search_index.py search --kb <kb> --flow 视频制作 --stage 1_找素材 --substage 子技巧
# 跨工作流按主题/关键词（辅助）
search_index.py search --kb <kb> --topics 选品
search_index.py search --kb <kb> --query "..."                    # 查询按「查询 gram」匹配（多语言分流，口径见 06 §4）
search_index.py search --kb <kb> --query "..." --include-stale    # 召回 stale 笔记
# 自然语言一次性召回：路由 JSON → FTS 查询 gram OR → q_hooks → topics 扩展 → relation 图遍历
search_index.py recall --kb <kb> --query "视频爆款分析"
search_index.py recall --kb <kb> --route-json '{"keywords":["视频","爆款","分析"],"topics":["爆款"],"flow":null,"stage":null,"unit_type":null,"include_stale":false,"need_relations":true,"top_k":10}'
```

`recall` 的合并排序为 **q_hooks 命中 > FTS > topics 扩展 > relation 关联**（同权重内按 bm25、更新时间）；路由 JSON 的字段与校验规则见 `06_retrieval.md` 第 9 节，q_hooks 见第 8 节。

FTS 通道默认带**弱命中门槛**（`--min-bigram-hits`，默认 2；参数名沿用历史，**实际数的是「查询 gram」**）：查询切出 ≥2 个 gram 时要求结果至少命中 2 个不同 gram，只切出 1 个时不启用；门槛只压 FTS，被滤的弱命中仍可由 q_hooks / topics / relation 通道补回，过滤明细写 `_meta/logs/fts_filtered.jsonl`。

物理层已体现环节，日常也可直接打开文件夹。

## 8. 迁移路径（加法）

旧库（标签驱动、notes 平铺）迁移：
1. 逐篇盘点，判断 flow/stage/substage；判定不了进收件箱；
2. 移到 `工作流/<flow>/<n>_<stage>/`，移动前出清单；
3. 建来源笔记（`素材库/_来源地图/`）指向衍生笔记；
4. 跑 `build_flows.py` 生成 `_流程.md`/`_总览.md`；
5. 六维标签不动，继续跨工作流检索；
6. `_meta/笔记地图.json` 记录笔记 ↔ flow/stage/substage/来源；
7. 旧 `notes/` 全部迁移并经用户确认后再清空。

原则：加法，不重写；每步可回退；移动/删除必须人工确认。
