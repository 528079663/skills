<!--
模板：note_deep.template.md（深度解读，项目型默认；2000+ 字）
变量：{{title}}；{{date}}；{{sources}}；{{project}} 项目名（可空）
多维：六维度多值标签；projects 维度与本笔记所属项目对齐。
要求：脉络还原 + 评价 + 适用/不适用 + 引用≤5 段。
-->
---
title: "{{title}}"
type: deep
bucket: 
domains: []
forms: []
tools: []
types: []
projects: ["{{project}}"]
topics: []
q_hooks: []       # 3–5 条口语问法，录入时顺手生成；检索优先匹配
sources: [{{sources}}]
source_kind: 
confidence:      # high / medium / low
classified_by:   # rule / ai / human / mixed
created: {{date}}
updated: {{date}}
stale: false
---
# {{title}}

## 这篇在讲什么（约 200 字）

## 脉络还原（按原文结构）
1.
2.

## 我认同的 / 不认同的
- 认同：
- 保留：

## 对我项目的启示

## 关联知识单元（开 units 时填 units id，双链）
- doc-xxx-claim-1：

## 适用场景 / 不适用场景
- 适用：
- 不适用：

## 关键原文引用（≤5 段，带 locator：§章节#char=起始-结束）
>

## 资料原话 / 归纳结论 / AI 推断
- 资料原话：（短引文，带定位，如 §3.1#char=1200-1280；数字/命令/代码必须原文可校验）
- 归纳结论：
- AI 推断：

## 关联笔记
<!-- 可选节。仅当正文明确引用、依赖或对照库内某篇现有笔记的具体内容/结论，
     且读者需跳转才能理解时，才写 - [[目标笔记的 stem]]。
     同 topic / 同标签 / 同概念 / 泛泛相关都不是加链理由；没有引用就删掉整节，允许孤岛。
     见 references/08_topics_pipeline_units.md 第 3.6 节 -->
