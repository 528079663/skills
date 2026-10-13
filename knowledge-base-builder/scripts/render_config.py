#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_config.py — profile.json + manifest + taxonomy → config.json。

生成工作流驱动的物理骨架（工作流/<flow>/<n>_<stage>/、概念索引、素材库/_来源地图、
00_导航、99_收件箱、projects、_meta），六维辅助标签降为辅助层，笔记按语义单元原子化（块是输入容器）。
对应 references/03_rules_engine.md、04_pipeline.md、09_workflow_model.md。
"""
import argparse
import json
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

# 统一物理骨架（工作流驱动）
BASE_DIRS = ["00_导航", "工作流", "概念索引", "素材库/_来源地图",
             "99_收件箱", "projects", "_meta"]
BASE_FILES = [
    ("README.md", "README.template.md"),
    ("AGENTS.md", "AGENTS.template.md"),
    ("00_导航/文件目录.md", None),
    ("00_导航/主题地图.md", None),
    ("_meta/问题资产库.md", "issue_log.template.md"),
    ("_meta/抽检记录.md", "inspection_log.template.md"),
    ("_meta/生成日志.md", None),
]
NOTE_TEMPLATE = "note_atomic.template.md"
FLOW_TEMPLATE = "flow.template.md"
STAGE_OVERVIEW_TEMPLATE = "stage_overview.template.md"
SOURCE_NOTE_TEMPLATE = "source_note.template.md"

# 样板选题用关键词
PLATFORM_LEAVES = {
    "B站": ["b站", "好物", "悬赏", "蓝链"],
    "视频号": ["视频号"],
    "小红书": ["小红书", "小绿书"],
    "YouTube_TK": ["youtube", "tiktok", "/tk", "ypp", "shorts", "推特"],
}
PROMPT_LEAVES = {
    "生图": ["生图", "绘画", "comfyui", "nanobanana"],
    "视频": ["即梦", "seedance", "sora", "可灵", "剪辑"],
    "编程": ["cursor", "codex", "claude", "代码", "小程序"],
}


def load(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


# ---------- 项目与配方（辅助层） ----------
def build_projects(profile, taxonomy):
    seed_map = {r["project"]: r for r in taxonomy.get("project_seed_recipes", [])}
    names = profile.get("projects_list") or \
        [r["project"] for r in taxonomy.get("project_seed_recipes", [])]
    projects = []
    for name in names:
        if name in seed_map:
            r = seed_map[name]
            recipe = {"project": name, "filters": r["filters"],
                      "exclude": r["exclude"], "rank": r["rank"],
                      "keywords": "", "limit": 50,
                      "units_type": r.get("units_type", []),
                      "units_confidence": r.get("units_confidence", []),
                      "units_status": r.get("units_status", [])}
            source = "受控词表种子配方"
        else:
            recipe = {"project": name, "filters": {},
                      "exclude": ["过时", "草稿", "低信心低质量"],
                      "rank": ["相关度", "时间"],
                      "keywords": "", "limit": 50,
                      "units_type": [], "units_confidence": [],
                      "units_status": []}
            source = "用户项目，配方待补/确认"
        projects.append({"name": name, "dir": f"projects/{name}",
                         "recipe_path": f"projects/{name}/recipe.yaml",
                         "recipe": recipe, "source": source})
    return projects


# ---------- 工作流 / 环节 ----------
def build_flows(profile):
    """从 profile.flows_list / stages_map 构建工作流配置。"""
    flows_list = profile.get("flows_list") or profile.get("flows_candidates") or []
    stages_map = profile.get("stages_map") or {}
    if not flows_list:
        print("[config] 警告：flows_list / flows_candidates 均为空，将不生成任何工作流目录。"
              "请在 Step 4 由 AI 读资料归纳后写入 profile.json 的 flows_candidates，"
              "再重跑 render_config.py。")
    flows = []
    for f in flows_list:
        stages = []
        for i, s in enumerate(stages_map.get(f, []), 1):
            # 自动给环节加序号前缀（如果用户没给）
            s_name = s if s[:1].isdigit() else f"{i}_{s}"
            stages.append({"name": s_name, "order": i})
        flows.append({"name": f, "stages": stages})
    return flows


# ---------- 目录 / 文件 ----------
def build_directories(flows, projects):
    dirs = {d: [True, "主干目录"] for d in BASE_DIRS}
    for flow in flows:
        flow_dir = f"工作流/{flow['name']}"
        dirs[flow_dir] = [True, f"工作流「{flow['name']}」"]
        for stage in flow["stages"]:
            stage_dir = f"{flow_dir}/{stage['name']}"
            dirs[stage_dir] = [True, f"环节「{flow['name']}/{stage['name']}」"]
    for p in projects:
        dirs[p["dir"]] = [True, f"项目「{p['name']}」"]
    return dirs


def build_files(flows, projects):
    files = {t: [tpl, "主干文件"] for t, tpl in BASE_FILES}
    # 原子笔记模板 + 来源笔记模板
    files[f"_meta/模板/{NOTE_TEMPLATE}"] = [NOTE_TEMPLATE, "原子笔记模板"]
    files[f"_meta/模板/{SOURCE_NOTE_TEMPLATE}"] = [SOURCE_NOTE_TEMPLATE, "来源笔记模板"]
    # 素材库/_来源地图/ 下放一个模板占位，让用户打开目录就看到格式
    files["素材库/_来源地图/_模板.md"] = [SOURCE_NOTE_TEMPLATE, "来源笔记格式参考"]
    # 概念索引占位说明
    files["概念索引/_说明.md"] = [None, "概念索引说明（units 产物入口）"]
    # 每个 flow 的 _流程.md
    for flow in flows:
        files[f"工作流/{flow['name']}/_流程.md"] = [FLOW_TEMPLATE,
                                                   f"工作流「{flow['name']}」流程总览"]
        for stage in flow["stages"]:
            files[f"工作流/{flow['name']}/{stage['name']}/_总览.md"] = \
                [STAGE_OVERVIEW_TEMPLATE,
                 f"环节「{flow['name']}/{stage['name']}」总览"]
    # 项目配方
    for p in projects:
        files[p["recipe_path"]] = ["recipe.template.yaml",
                                   f"项目「{p['name']}」配方"]
        files[f"projects/{p['name']}/PROGRESS.md"] = [
            "PROGRESS.template.md", f"项目「{p['name']}」进度"]
    return files


# ---------- 规则 / 冲突 ----------
def rules_table(profile):
    base = {
        "conservative": {"new_note": "L1", "fix_format": "L1", "add_tags": "L1",
                         "build_index": "L0", "move_in_inbox": "L2", "batch_20plus": "L2"},
        "balanced": {"new_note": "L0", "fix_format": "L0", "add_tags": "L0",
                     "build_index": "L0", "move_in_inbox": "L1", "batch_20plus": "L2"},
        "aggressive": {"new_note": "L0", "fix_format": "L0", "add_tags": "L0",
                       "build_index": "L0", "move_in_inbox": "L1", "batch_20plus": "L1"},
    }[profile["collab_level"]]
    base.update({"edit_source": "L2", "delete": "L2",
                 "rename_topic": "L2", "write_rules": "L2"})
    return base


def resolve_conflicts(profile):
    conflicts = []
    if profile["collab_level"] == "conservative" and profile["batch_size"] == 100:
        profile["batch_size"] = 20
        conflicts.append({"id": "C1", "decision": "安全优先，批量降为20"})
    if "minutes" in profile["doc_types"] and not profile["ingest_scope"]["minutes"]:
        conflicts.append({"id": "C3", "decision": "资料含妙记但你选了不进知识层，待你确认是否改回轻量引用",
                          "needs_user_confirm": True})
    if "internal" in profile["privacy_exclusions"]:
        conflicts.append({"id": "C5", "decision": "整库标记私有，禁止对外分享"})
    if not any(profile["ingest_scope"].values()):
        conflicts.append({"id": "C7", "decision": "入库范围全否，与建库矛盾，待你拍板"})
    if profile.get("granularity") == "atomic":
        conflicts.append({"id": "C8", "decision": "笔记按语义单元原子化：高价值块是输入容器，每块拆 N 篇（N≥1），文档级另出来源笔记"})
    return conflicts


# ---------- 特殊资料 / 样板 ----------
def build_special(profile, manifest):
    pairing = manifest["pairing"]
    orphan_pdfs = []
    for p in pairing["orphan_pdfs"]:
        if "卡片版" in p or "知识卡片" in p:
            action, reason = "extract_cards", "卡片型PDF"
        elif "问答" in p:
            action, reason = "extract", "内容型PDF"
        else:
            action, reason = "register", "未判定"
        orphan_pdfs.append({"path": p, "action": action, "reason": reason})
    essenceless = [{"path": p,
                    "action": "generate_essence"
                    if profile["ingest_scope"]["minutes"] else "skip"}
                   for p in pairing["essenceless_minutes"]]
    return {"unsorted": {"policy": profile["unsorted_policy"],
                         "index_target": "00_导航/待分拣索引.md"},
            "orphan_pdfs": orphan_pdfs, "essenceless_minutes": essenceless}


def body_docs(manifest):
    """收集正文 md 路径（根目录或子目录都接受）。"""
    out = []
    skip_kw = ["清单", "索引", "日志", "待下载", "报告"]
    for d in manifest["documents"]["md"]:
        p = d["path"]
        size = d.get("size", 0)
        if d.get("is_essence"):
            # 精华笔记：原文缺失时作为 body（简化：小文件才跳过）
            if size >= 500:
                out.append(p)
            continue
        # 根目录或子目录都接受
        parts = p.split("/")
        top = parts[0]
        if top.startswith(".") or top in {"tmp", "00_索引·规范·日志", ".trash", "__MACOSX"}:
            continue
        base = parts[-1]
        # 小文件且含导航关键词才跳过
        if size < 500 and any(k in base for k in skip_kw):
            continue
        out.append(p)
    return out


def build_samples(profile, docs):
    chosen, reasons = [], []
    leaf_map = {**PLATFORM_LEAVES, **PROMPT_LEAVES}
    for leaf, kws in leaf_map.items():
        if len(chosen) >= 4:
            break
        cands = [d for d in docs if any(k in d.lower() for k in kws)
                 and "transcript" not in d and d not in chosen]
        if cands:
            pick = sorted(cands, key=len)[len(cands) // 2]
            chosen.append(pick)
            reasons.append((pick, leaf, f"{leaf} 主题代表作"))
    for d in docs:
        if len(chosen) >= 5:
            break
        if d not in chosen:
            chosen.append(d)
            reasons.append((d, "补充", "高密度补充样本"))
    return [{"source": s, "topic": r[1], "reason": r[2]}
            for s, r in zip(chosen, reasons)]


def main():
    ap = argparse.ArgumentParser(description="画像+盘点+词表 → 配置")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--taxonomy", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    profile, manifest = load(args.profile), load(args.manifest)
    taxonomy = load(args.taxonomy)

    conflicts = resolve_conflicts(profile)
    flows = build_flows(profile)
    projects = build_projects(profile, taxonomy)
    dirs = build_directories(flows, projects)
    files = build_files(flows, projects)
    special = build_special(profile, manifest)
    docs = body_docs(manifest)
    samples = build_samples(profile, docs)

    config = {
        "flows": flows,
        "granularity": profile.get("granularity", "atomic"),
        "aux_tags_enabled": profile.get("aux_tags_enabled", True),
        "topics_enabled": profile.get("topics_enabled", True),
        "dimensions": taxonomy.get("auxiliary_dimensions", taxonomy.get("dimensions", {})),
        "primary_axis": taxonomy.get("primary_axis", {}),
        "projects": projects,
        "directories": [{"path": k, "create": v[0], "reason": v[1]}
                        for k, v in sorted(dirs.items())],
        "files": [{"target": k, "template": v[0], "reason": v[1]}
                  for k, v in sorted(files.items())],
        "note_template": NOTE_TEMPLATE,
        "note_depth": profile["note_depth"],
        "retrieval_mode": profile.get("retrieval_mode", "fts"),
        "extract_units": {
            "enabled": (profile.get("units") or {}).get("enabled", False),
            "core_types": ["claim", "concept", "qa", "open_question"],
            "extended_types": ["relation", "procedure", "conflict"],
            "optional_types": ["asset"],
        },
        "extraction": {
            "units_enabled": (profile.get("units") or {}).get("enabled", False),
            "confidence_thresholds": {"high": 0.8, "medium": 0.6, "low": 0.0},
            "locator_format": "§章节标题#char=起始-结束",
            "chunk_size": [800, 1500],
            "chunk_overlap_ratio": 0.1,
            "high_value_rules": {
                "min_len": 50, "density_threshold": 0.5,
            },
        },
        "existing_kb": profile.get("existing_kb", "fresh"),
        "scale": profile.get("scale"),
        "topic_policy": taxonomy.get("topic_policy", {}),
        "rules": rules_table(profile),
        "special_handling": special,
        "batch_size": profile["batch_size"],
        "output_targets": profile["output_targets"],
        "privacy_exclusions": profile["privacy_exclusions"],
        "first_task": profile["first_task"],
        "sample_notes": samples,
        "conflicts_resolved": conflicts,
        "defaults_applied": profile.get("defaults_applied", []),
        "source_root": manifest["source_root"],
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2)

    nd = sum(1 for d in config["directories"] if d["create"])
    print(f"[config] 工作流 {len(flows)} 个: {[f['name'] for f in flows]}")
    for f in flows:
        print(f"  · {f['name']}: {[s['name'] for s in f['stages']]}")
    print(f"[config] 落地目录={nd} 文件={len(files)}")
    print(f"[config] 项目配方 {len(projects)} 个")
    print(f"[config] 冲突仲裁 {len(conflicts)}；样板 {len(samples)} 篇")
    print(f"[config] 已写出：{args.out}")


if __name__ == "__main__":
    main()
