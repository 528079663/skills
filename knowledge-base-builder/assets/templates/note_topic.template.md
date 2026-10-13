<!--
模板：note_topic.template.md（主题笔记，创作型默认；500–1000 字）
变量：{{title}}；{{date}}；{{sources}} 原文路径列表
多维：六维度多值标签；同维多值、同义词归一；confidence 低则进收件箱。
要求：核心结论≤7；可执行清单；数字标出处；三段分标；关联。
-->
---
title: "{{title}}"
type: topic
bucket: 
domains: []
forms: []
tools: []
types: []
projects: []
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

> 一句话：

## 核心结论（≤7 条）
1.
2.

## 关联知识单元（开 units 时填 units id，双链）
- doc-xxx-claim-1：

## 可执行清单
- [ ]

## 关键数字（每条带 locator：§章节#char=起始-结束）
-

## 资料原话 / 归纳结论 / AI 推断
- 资料原话：（短引文，带定位，如 §3.1#char=1200-1280）
- 归纳结论：
- AI 推断：

## 本主题成员笔记（聚合列举，不是正文引用）
<!-- 本节列的是"这个主题下有哪些篇"，与 references/08 第 3.6 节的引用双链是两回事：
     引用双链写在正文里，只在确实引用/依赖/对照某篇具体内容时才写 [[stem]]；
     同 topic / 同标签 / 泛泛相关都不是加链理由，没有引用就不加，允许孤岛。 -->

## 原文
-
