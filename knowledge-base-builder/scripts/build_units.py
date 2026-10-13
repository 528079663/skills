#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_units.py — 结构化知识单元校验/索引（层3）。

units.jsonl 由执行 AI 在高价值块深抽后写出（每行一个单元）；本脚本做确定性校验与
聚合索引，不生成内容。schema 见 references/08 第 4 节。

默认六类：claim / concept / procedure / qa / open_question / conflict
（relation / asset 为可选，用户明确要时再开）。
校验：分类型必填字段、high 置信必须 evidence 三要素、conflict 双源、procedure steps 为列表。
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

REQUIRED = ["id", "doc_id", "type", "confidence"]
VALID_CONF = {"high", "medium", "low"}
VALID_STATUS = {"draft", "confirmed", "stale"}
CORE_TYPES = {"claim", "concept", "relation", "procedure", "qa",
              "open_question", "conflict"}
OPTIONAL_TYPES = {"asset"}
VALID_TYPES = CORE_TYPES | OPTIONAL_TYPES

TYPE_REQUIRED = {
    "claim": ["text"],
    "concept": ["name", "definition"],
    "relation": ["subject", "predicate", "object"],
    "procedure": ["goal", "steps"],
    "qa": ["question", "answer"],
    "open_question": ["question"],
    "conflict": ["sources", "positions"],
}


def check_unit(u, errors, no_evidence_high, low_conf, conflict_positions, warnings):
    uid = u.get("id", "?")
    miss = [k for k in REQUIRED if k not in u]
    if miss:
        errors.append(f"{uid} 缺通用字段 {miss}")
        return
    if u["type"] not in VALID_TYPES:
        errors.append(f"{uid} 非法 type={u['type']}")
        return
    if u["confidence"] not in VALID_CONF:
        errors.append(f"{uid} 非法 confidence={u['confidence']}")
        return
    req = TYPE_REQUIRED.get(u["type"], [])
    field_miss = [k for k in req if not u.get(k)]
    if field_miss:
        errors.append(f"{uid}({u['type']}) 缺类型字段 {field_miss}")
        return
    # procedure 步骤连续性在 validate_extraction 查；这里要求 steps 是列表
    if u["type"] == "procedure" and not isinstance(u.get("steps"), list):
        errors.append(f"{uid} steps 必须为列表")
    if u["type"] == "conflict":
        if len(u.get("sources", [])) < 2 or len(u.get("positions", [])) < 2:
            errors.append(f"{uid}(conflict) 至少 2 个来源/立场")
        else:
            conflict_positions.append(uid)
    # evidence 可为单对象或合并后的对象数组
    ev = u.get("evidence") or []
    if isinstance(ev, dict):
        ev = [ev]
    has_ev = any(isinstance(e, dict) and e.get("file")
                 and e.get("locator") and e.get("quote") for e in ev)
    if u["confidence"] == "high" and not has_ev:
        no_evidence_high.append(uid)
    if u["confidence"] == "low":
        low_conf.append(uid)
    # high 置信却带 AI 推断 → warn（三段写死：推断不应混入高置信结论）
    if u["confidence"] == "high" and str(u.get("inference", "")).strip():
        warnings.append(f"{uid}(high) 含 inference，应改为 medium 或把推断移出")


def main():
    ap = argparse.ArgumentParser(description="units 校验/索引")
    ap.add_argument("--kb", required=True)
    ap.add_argument("--units", default="_meta/units.jsonl")
    ap.add_argument("--out", default="_meta/units_index.json")
    args = ap.parse_args()

    units_path = os.path.join(args.kb, args.units.replace("/", os.sep))
    if not os.path.isfile(units_path):
        print(f"[units] 未找到 {args.units}（未启用，正常）。")
        return

    units, errors, no_ev_high, low_conf, warnings = [], [], [], [], []
    conflict_ok = []
    by_type = defaultdict(int)
    by_topic = defaultdict(list)
    by_conf = defaultdict(int)
    with open(units_path, "r", encoding="utf-8-sig") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                u = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"第{ln}行 JSON 解析失败: {e}")
                continue
            before = len(errors)
            check_unit(u, errors, no_ev_high, low_conf, conflict_ok, warnings)
            if len(errors) > before:
                continue
            units.append(u)
            by_type[u["type"]] += 1
            by_conf[u["confidence"]] += 1
            for t in u.get("topic_ids", []):
                by_topic[t].append(u["id"])

    index = {
        "total": len(units),
        "by_type": {t: by_type.get(t, 0) for t in sorted(VALID_TYPES)
                    if by_type.get(t) or t in CORE_TYPES},
        "by_confidence": dict(by_conf),
        "by_topic": {t: ids for t, ids in sorted(by_topic.items())},
        "no_evidence_high": no_ev_high,
        "low_confidence": low_conf,
        "conflicts": conflict_ok,
        "warnings": warnings,
        "errors": errors,
    }
    out_path = os.path.join(args.kb, args.out.replace("/", os.sep))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=2)

    print(f"[units] 单元 {len(units)}；类型分布 {dict(by_type)}")
    print(f"[units] 校验错误 {len(errors)}；high缺证据 {len(no_ev_high)}；"
          f"低置信 {len(low_conf)}；冲突 {len(conflict_ok)}")
    for e in errors[:10]:
        print("  !", e)
    print(f"[units] → {out_path}")


if __name__ == "__main__":
    main()
