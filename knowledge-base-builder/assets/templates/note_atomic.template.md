<!-- 原子笔记模板：一篇笔记回答一个可独立回答的问题（语义单元）；高价值块只是输入容器，一块可拆 N 篇。
     AI 深抽时按此模板填写，frontmatter 必须含 flow/stage/substage。规约见 references/08 第 3 节硬约束 9。 -->
<!-- 注意：本模板放在 _meta/模板/ 下，尖括号 <...> 占位由 AI 深抽时替换，非 render 槽位。 -->
---
title: <笔记标题，从高价值块标题提炼>
flow: <主工作流名，如 视频制作>
stage: <主环节名，如 1_找素材>
substage: <总览/子技巧/案例/工具/坑，5 选 1>
domains: []
forms: []
tools: []
types: []
projects: []
topics: []        # 由 AI 读高价值块标注（每篇 1–5 个），规则打标不猜
q_hooks: []       # 3–5 条口语问法（用户会怎么问这件事），录入时顺手生成；检索优先匹配
sources:
  - <源文件相对路径>
source_locator:           # block 列表：首项 = 主块；一个语义单元跨块时，其余块按引用顺序往下列
  - <§章节#char=起始-结束>
                          # 只用 block 列表，不要内联 [a, b]；任何读它的脚本要走 fm_list，不能用 parse_frontmatter
confidence: <high/medium/low>
status: <draft/confirmed>
created: <YYYY-MM-DD>
---

# <笔记标题>

> 一句话结论（30 字内）。

## 资料原话（evidence.quote）

> 逐字引用源文件中支撑本笔记的段落（validate_extraction 会严格校验子串）。
> —— `§<章节标题>#char=<起始>-<结束>`

<!-- 上面第二行 `> —— `§…#char=…`` 是 **autolocate.py --check 读取 evidence 的唯一入口**，
     必须紧跟在引文行之后、同属一个引用块；一行引文配一行定位符，一行多据时拆成多行写。
     定位符照抄 `autolocate.py --compute` 的输出（标题与区间都不许手写），禁止编造。
     少了这行，--check 会读到 0 条 evidence 并 rc=0 放行 —— 事后复核等于没开。 -->

## 归纳结论

- 要点 1
- 要点 2
- 要点 3

## 可执行清单（substage=子技巧/总览 时填，其余可删）

1. 步骤一
2. 步骤二

## AI 推断（inference）

> AI 的推断、适用场景、注意事项。与资料原话分开标注。
> **每行必须以四种前缀之一开头**（规约见 `references/08_topics_pipeline_units.md` 第 3.1 节）：
> `作者未提、我的推论：`（唯一被逐字校验豁免的一类）/ `同块其他结论：` / `口径澄清：` / `⚠️`。
> 无前缀的 inference 行视为违规，走抽检，不做机器校验。

## 关联

- 来源：[[来源笔记链接]]

<!-- 关联节只放「正文明确引用且需跳转」的双链，规约见 references/08_topics_pipeline_units.md 第 3.6 节。
     不预留 [[相关笔记]] 占位：同 topic / 同标签 / 同概念 / 泛泛相关都不是加链理由，
     没有明确引用就删掉整节，允许本笔记是孤岛。目标名用文件名去 .md 的 stem（verify C10 按 stem 解析）。 -->
