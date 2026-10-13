<!--
模板：PROGRESS.template.md（项目进度）
变量：{{project}} 项目名；{{date}}
六要素来自【Blake】：目标/当前状态/已完成/最近决策/下一步/待确认。
要求：不编造已完成事项；每次推进后更新并自检。
-->
# {{project}} · PROGRESS

> 更新：{{date}}

## 项目目标

## 当前状态

## 已完成
-

## 最近决策
-

## 下一步
- [ ]

## 待确认问题
-

## 抽取质量（每批回填）
- 高价值块处理率：__%（coverage_audit；**进度事实以 `progress.py` 反推为准，冲突时 progress 赢、
  本行标过期**）
- inbox 占本批 high_value chunk：__%（>20% 不放行，小批次 <10 块人工判断）
- validate_extraction：通过 / 错误 N 条
- 抽检条目通过率：__%（<95% 回滚）
- 最近抽检：批次 __ / 抽 __ 条 / 通过 __ 条（详见 _meta/抽检记录.md）
- units 计数：claim__ / concept__ / relation__ / procedure__ / qa__ / open_question__ / conflict__
- stale 计数：笔记 __ 篇 / units __ 条（原文更新后未重抽）

## 资料索引（指向原文，不复制）
-
