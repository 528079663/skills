#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_profile.py — 问卷答案 answers.json → 结构化画像 profile.json。

字段题号对齐新版 intake_questionnaire.md（16 题/22 小问，工作流驱动）：
  Q1 工作流清单 / Q2 环节划分 / Q3 半年第一件事 / Q4 卡点 /
  Q5 类型+规模 / Q6 笔记粒度 / Q7 入层范围 / Q8 未归桶 / Q9 已有库 /
  Q10 协作 / Q11 笔记深度+例外 / Q12 批量 / Q13 输出+分类+隐私 /
  Q14 六维辅助标签+主题层 / Q15 项目+排除 / Q16 检索+units。
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

PAINPOINT_MAP = {"a": "retrieval", "b": "forgetting", "c": "direction",
                 "d": "workflow", "e": "scattered"}
DOCTYPE_MAP = {"a": "case", "b": "minutes", "c": "tutorial",
               "d": "prompts", "e": "sop", "f": "links"}
SCALE_MAP = {"a": "under50", "b": "mid50_300", "c": "large300_1000", "d": "huge1000+"}
EXISTING_KB_MAP = {"a": "fresh", "b": "import_existing", "c": "new_only"}
COLLAB_MAP = {"a": "conservative", "b": "balanced", "c": "aggressive"}
DEPTH_MAP = {"a": "card", "b": "topic", "c": "deep"}
BATCH_MAP = {"a": 5, "b": 20, "c": 100}
OUTPUT_MAP = {"a": "local", "b": "feishu", "c": "notion_pub", "d": "rag"}
CLASSIFICATION_MAP = {"a": "flow_first", "b": "tag_first", "c": "mixed", "d": "flow_first"}
PRIVACY_MAP = {"a": "income", "b": "accounts", "c": "internal"}
UNSORTED_MAP = {"a": "suggest_table", "b": "skip", "c": "handpick"}
EXCLUDE_MAP = {"a": "过时", "b": "草稿", "c": "低信心", "d": "个人敏感"}
GRANULARITY_MAP = {"a": "coarse", "b": "atomic"}

VALID = {
    "q4": set(PAINPOINT_MAP), "q5": set(DOCTYPE_MAP),
    "q10_collab": set(COLLAB_MAP), "q11_depth": set(DEPTH_MAP),
    "q11_exceptions": set("abcd"), "q12_batch": set(BATCH_MAP),
    "q13_output": set(OUTPUT_MAP), "q13_class": set(CLASSIFICATION_MAP),
    "q13_priv": set(PRIVACY_MAP), "q15_exclude": set(EXCLUDE_MAP),
}


def valid_list(vals, valid_key, defaults):
    if not vals:
        return None
    good = [v for v in vals if v in VALID[valid_key]]
    if not good:
        defaults.append(f"{valid_key}: 非法选项已忽略: 原值={vals}")
        return None
    if len(good) != len(vals):
        defaults.append(f"{valid_key}: 部分非法选项已忽略")
    return good


def main():
    ap = argparse.ArgumentParser(description="问卷答案 → 用户画像")
    ap.add_argument("--answers", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.answers, "r", encoding="utf-8-sig") as fh:
        a = json.load(fh)

    defaults = []

    # Q1 工作流清单
    flows_list = a.get("q1_flows") or []
    if not flows_list:
        defaults.append("q1: 工作流清单缺失，方案中将从资料归纳候选 flow")
        flows_list = []

    # Q2 环节划分
    stages_map = a.get("q2_stages") or {}
    if not stages_map:
        defaults.append("q2: 环节划分缺失，方案中将从资料章节归纳候选 stage")
        stages_map = {}
    # 为每个有 flow 但没 stages 的给空列表
    for f in flows_list:
        if f not in stages_map:
            stages_map[f] = []

    # Q3 半年第一件事
    first_task = a.get("q3_first_task")
    if not first_task:
        defaults.append("q3: 首个任务缺失，方案中将给候选而不虚构")

    # Q4 卡点
    pain = valid_list(a.get("q4_painpoints"), "q4", defaults)
    painpoints = [PAINPOINT_MAP[x] for x in pain] if pain else []

    # Q5 资料类型 + 规模
    dt = valid_list(a.get("q5_doc_types"), "q5", defaults)
    doc_types = [DOCTYPE_MAP[x] for x in dt] if dt else []
    scale = a.get("q5_scale")
    if scale not in SCALE_MAP:
        scale = "b"
        defaults.append("q5.2: 规模缺失，默认 mid50_300")
    else:
        scale = SCALE_MAP[scale]

    # Q6 笔记粒度
    gran = a.get("q6_granularity")
    if gran not in GRANULARITY_MAP:
        gran = "b"
        defaults.append("q6: 笔记粒度缺失，默认 atomic（读高价值块、按语义单元拆篇）")
    granularity = GRANULARITY_MAP[gran]

    # Q7 入层范围
    scope_in = a.get("q7_ingest_scope") or {}
    ingest_scope = {
        "md": scope_in.get("md", True),
        "minutes": scope_in.get("minutes", True),
        "pdf": scope_in.get("pdf", False),
        "media": scope_in.get("media", False),
        "images": scope_in.get("images", False),
    }
    if not a.get("q7_ingest_scope"):
        defaults.append("q7: 入层范围缺失，按 md/minutes=true，其余=false")

    # Q8 条件题：未归桶
    if a.get("q8_unsorted_not_applicable"):
        unsorted_policy = None
        handpick = []
    else:
        q8 = a.get("q8_unsorted")
        if q8 not in UNSORTED_MAP:
            if q8 is not None:
                defaults.append("q8: 非法值，按 suggest_table")
            q8 = "a"
            defaults.append("q8: 未归桶策略缺失，默认 suggest_table")
        unsorted_policy = UNSORTED_MAP[q8]
        handpick = a.get("q8_handpick") or []
        if unsorted_policy == "handpick" and not handpick:
            unsorted_policy = "suggest_table"
            defaults.append("q8: handpick 未附篇名，降级 suggest_table")

    # Q9 已有笔记库
    q9 = a.get("q9_existing_kb")
    if q9 not in EXISTING_KB_MAP:
        q9 = "a"
        defaults.append("q9: 已有笔记库缺失，默认 fresh（从零建）")
    existing_kb = EXISTING_KB_MAP[q9]

    # Q10 协作风格
    q10 = a.get("q10_collab")
    if q10 not in COLLAB_MAP:
        q10 = "b"
        defaults.append("q10: 协作风格缺失，默认 balanced")
    collab_level = COLLAB_MAP[q10]

    # Q11 笔记深度 + 例外
    q11 = a.get("q11_note_depth")
    if q11 not in DEPTH_MAP:
        q11 = "b"
        defaults.append("q11.1: 笔记深度缺失，默认 topic")
    note_depth = DEPTH_MAP[q11]
    depth_exc = a.get("q11_depth_exceptions")
    if not depth_exc:
        depth_exceptions = ["a", "b"]
        defaults.append("q11.2: 深度例外缺失，默认 重点工作流 + 高价值块多")
    else:
        depth_exceptions = [x for x in depth_exc if x in "abcd"]

    # Q12 批量规模
    q12 = a.get("q12_batch_size")
    if q12 not in BATCH_MAP:
        q12 = "b"
        defaults.append("q12: 批量规模缺失，默认 20")
    batch_size = BATCH_MAP[q12]

    # Q13 输出/分类/隐私
    out_vals = valid_list(a.get("q13_output_targets"), "q13_output", defaults)
    output_targets = ([OUTPUT_MAP[x] for x in out_vals]
                      if out_vals else ["local", "feishu"])
    if not a.get("q13_output_targets"):
        defaults.append("q13.1: 输出去向缺失，按推荐默认 local + feishu")

    cls = a.get("q13_classification")
    if cls not in CLASSIFICATION_MAP:
        cls = "a"
        defaults.append("q13.2: 分类偏好缺失，默认 flow_first（工作流为主）")
    classification_preference = CLASSIFICATION_MAP[cls]

    priv_vals = valid_list(a.get("q13_privacy"), "q13_priv", defaults)
    privacy_exclusions = ([PRIVACY_MAP[x] for x in priv_vals]
                          if priv_vals else ["income", "accounts", "internal"])
    if not a.get("q13_privacy"):
        defaults.append("q13.3: 隐私边界缺失，按安全底线默认全脱敏")

    # Q14 六维辅助标签 + 主题层
    aux_tags_enabled = a.get("q14_aux_tags_enabled")
    if aux_tags_enabled is None:
        aux_tags_enabled = True
        defaults.append("q14.1: 六维辅助标签缺失，默认开启")
    aux_tags_enabled = bool(aux_tags_enabled)

    topics_enabled = a.get("q14_topics_enabled")
    if topics_enabled is None:
        topics_enabled = True
        defaults.append("q14.2: 主题层缺失，默认开启")
    topics_enabled = bool(topics_enabled)

    # Q15 项目配方
    projects_list = a.get("q15_projects") or []
    excl_letters = a.get("q15_recipe_exclude") or ["a", "b", "c"]
    recipe_exclude = [EXCLUDE_MAP[x] for x in excl_letters if x in EXCLUDE_MAP]

    # Q16 检索方式
    q16 = a.get("q16_retrieval") or "a"
    retrieval_mode = "vector" if q16 == "b" else "fts"

    # Q16.2 units（显式优先；未选按目标推断）
    q16u = a.get("q16_extract_units")
    if q16u in ("a", "b"):
        extract_units = (q16u == "b")
    else:
        outputs = a.get("q13_output_targets") or []
        painpoints = a.get("q4_painpoints") or []
        # 推断规则：Q4 含 c（不知学啥）或 Q13.1 含 d（RAG）→ 开 units
        extract_units = ("d" in outputs) or ("c" in painpoints)
        src = "用户显式选'你建议'" if q16u == "c" else "未答"
        defaults.append(
            f"q16.2: {src}，按目标智能推断 units={'开' if extract_units else '关'}"
            f"（Q4含c或Q13.1含d则开；Q16.2 可显式覆盖）")

    profile = {
        "flows_list": flows_list,
        "flows_candidates": [],  # 由执行 AI 在 Step 4 读资料后回填（当 flows_list 为空时）
        "stages_map": stages_map,
        "granularity": granularity,
        "first_task": first_task,
        "painpoints": painpoints,
        "doc_types": doc_types,
        "scale": scale,
        "ingest_scope": ingest_scope,
        "unsorted_policy": unsorted_policy,
        "handpick": handpick,
        "existing_kb": existing_kb,
        "collab_level": collab_level,
        "note_depth": note_depth,
        "depth_exceptions": depth_exceptions,
        "batch_size": batch_size,
        "output_targets": output_targets,
        "classification_preference": classification_preference,
        "privacy_exclusions": privacy_exclusions,
        "aux_tags_enabled": aux_tags_enabled,
        "topics_enabled": topics_enabled,
        "projects_list": projects_list,
        "recipe_exclude": recipe_exclude,
        "retrieval_mode": retrieval_mode,
        "units": {"enabled": extract_units},
        "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "defaults_applied": defaults,
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(profile, fh, ensure_ascii=False, indent=2)

    print(f"[profile] 工作流={flows_list}")
    for f, ss in stages_map.items():
        print(f"  · {f}: {ss}")
    print(f"[profile] 粒度={granularity} 笔记档={note_depth}(例外{depth_exceptions})")
    print(f"[profile] 规则档={collab_level} 批量={batch_size} 规模={scale}")
    print(f"[profile] 六维辅助={aux_tags_enabled} 主题层={topics_enabled} units={extract_units}")
    print(f"[profile] 默认项 {len(defaults)} 条")
    for d in defaults:
        print(f"  · {d}")
    print(f"[profile] 已写出：{args.out}")


if __name__ == "__main__":
    main()
