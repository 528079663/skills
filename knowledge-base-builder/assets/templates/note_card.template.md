<!--
模板：note_card.template.md（速读卡，学习型默认；100–200 字）
变量：{{title}} 标题；{{date}} 日期；{{source}} 原文相对路径
多维：六维度标签必填（至少 domains/types），否则多维检索召回不到；同义词先归一。
要求：一句话 + 3 要点；不展开。
-->
---
title: "{{title}}"
type: card
bucket: 
domains: []
forms: []
tools: []
types: []
projects: []
topics: []
q_hooks: []       # 3–5 条口语问法，录入时顺手生成；检索优先匹配
sources: ["{{source}}"]
source_kind: 
confidence: 
classified_by: 
created: {{date}}
updated: {{date}}
stale: false
---
# {{title}}

> 一句话：

- 要点 1：
- 要点 2：
- 要点 3：

关联：<!-- 仅在正文明确引用某篇现有笔记时才写 [[stem]]；无引用则删掉本行，允许孤岛。见 references/08 第 3.6 节 -->
