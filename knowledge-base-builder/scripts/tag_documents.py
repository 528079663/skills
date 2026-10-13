#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tag_documents.py — 规则初筛打标：manifest + taxonomy → 多维标签预测。

确定性部分（对应 references/05 第 7 节步骤 1、3、4）：
  - 按路径/文件名匹配同义词 → 规范标签 → 归入 6 维度；
  - 计算信心度，核心维度(domains/types)缺失则低信心、标记待人工(进收件箱)；
  - 输出 tags_pred.json，供 AI 语义复核与 evaluate.py 评估。
AI 语义打标（读标题+开头补标签）由执行 AI 在本脚本结果上进行，不在此脚本内。
"""
import argparse
import json
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

# 规范标签 → 维度（synonyms 的 key 与各维度 core 的并集）
CANON_DIM = {
    "AI": "domains", "编程": "domains",
    "自媒体": "forms", "视频": "forms", "文章": "forms", "直播": "forms",
    "Codex": "tools", "Claude": "tools", "Cursor": "tools", "AI Agent": "tools",
    "Skills": "tools", "ComfyUI": "tools", "即梦": "tools", "可灵": "tools",
    "剪辑": "tools", "微信小程序": "tools", "n8n": "tools", "WorkBuddy": "tools",
    "教程": "types", "案例": "types", "复盘": "types", "SOP": "types",
    "问答": "types", "观点": "types", "素材": "types", "资源": "types",
    "AI自媒体": "projects", "B站好物": "projects", "视频号带货": "projects",
    "小红书虚拟": "projects", "YouTube_TK": "projects", "Codex剪辑": "projects",
    "AI视频": "projects", "AI绘画": "projects",
    "PDF": "sources", "网页剪藏": "sources", "妙记": "sources", "原创": "sources",
}
SKIP_TOP = {"tmp", "00_索引·规范·日志", ".trash", "__MACOSX"}
SKIP_NAME_KW = ["清单", "索引", "日志", "待下载", "报告", "总览", "说明"]


def load(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def is_body(path, size=0):
    """判断是否为正文 md。根目录文件直接接受；SKIP_NAME_KW 仅小文件跳过。"""
    if size and size < 200:
        return False
    parts = path.split("/")
    top = parts[0]
    if top.startswith(".") or top in SKIP_TOP:
        return False
    base = parts[-1]
    if size and size < 500 and any(k in base for k in SKIP_NAME_KW):
        return False
    return True


def build_variant_index(taxonomy):
    """canon → [变体小写...]；并校验 canon 都有维度归属。

    遍历 CANON_DIM 与 synonyms 的并集，避免 synonyms 缺 key 时
    CANON_DIM 里的规范标签（如素材/资源）不进入匹配索引。
    """
    index = {}
    all_canons = set(taxonomy.get("synonyms", {}).keys()) | set(CANON_DIM.keys())
    for canon in all_canons:
        variants = taxonomy.get("synonyms", {}).get(canon, [])
        vals = [canon.lower()] + [v.lower() for v in variants]
        index[canon] = sorted(set(vals))
    missing = [c for c in index if c not in CANON_DIM]
    if missing:
        print(f"[tag][warn] 以下规范标签未配置维度，将跳过: {missing}")
    return index


def tag_one(path, variant_index):
    low = path.lower()
    dims = {d: [] for d in ["domains", "forms", "tools", "types", "projects"]}
    source_kind = None
    hits = []
    for canon, variants in variant_index.items():
        if any(v in low for v in variants):
            dim = CANON_DIM.get(canon)
            if dim == "sources":
                # 单值，按优先级：妙记 > PDF > 网页剪藏
                prio = {"妙记": 0, "PDF": 1, "网页剪藏": 2}
                if source_kind is None or prio[canon] < prio[source_kind]:
                    source_kind = canon
            elif dim:
                if canon not in dims[dim]:
                    dims[dim].append(canon)
                hits.append(canon)

    # 跨维度推断：项目命中 → 隐含领域/形态/工具
    PROJECT_IMPLY = {
        "AI自媒体": (["AI"], ["自媒体"], []),
        "B站好物": (["AI"], ["自媒体"], []),
        "视频号带货": (["AI"], ["自媒体"], []),
        "小红书虚拟": (["AI"], ["自媒体"], []),
        "YouTube_TK": (["AI"], ["自媒体"], []),
        "AI视频": (["AI"], ["视频"], []),
        "AI绘画": (["AI"], [], []),
        "Codex剪辑": (["AI"], [], ["Codex", "剪辑"]),
    }
    AI_IMPLY_TOOLS = {"Codex", "Claude", "Cursor", "AI Agent", "Skills",
                      "ComfyUI", "即梦", "可灵", "n8n", "WorkBuddy"}

    def add_unique(dim, vals):
        for v in vals:
            if v not in dims[dim]:
                dims[dim].append(v)

    for proj in dims["projects"]:
        d, f, t = PROJECT_IMPLY.get(proj, ([], [], []))
        add_unique("domains", d)
        add_unique("forms", f)
        add_unique("tools", t)
    if set(dims["tools"]) & AI_IMPLY_TOOLS:
        add_unique("domains", ["AI"])

    # 信心度
    conf = 0.0
    if dims["domains"]:
        conf += 0.4
    if dims["types"]:
        conf += 0.3
    conf += min(0.15, 0.15 * len(dims["tools"]))
    conf += min(0.1, 0.1 * len(dims["forms"]))
    conf += min(0.15, 0.15 * len(dims["projects"]))
    if not dims["domains"] or not dims["types"]:
        conf = min(conf, 0.5)  # 核心维度缺失，封顶
    conf = min(round(conf, 3), 0.95)
    needs_review = conf < 0.6

    bucket = path.split("/", 1)[0]
    return {
        "path": path, "bucket": bucket,
        "domains": dims["domains"], "forms": dims["forms"], "tools": dims["tools"],
        "types": dims["types"], "projects": dims["projects"],
        "source_kind": source_kind, "confidence": conf,
        "classified_by": "规则", "needs_review": needs_review,
    }


def main():
    ap = argparse.ArgumentParser(description="规则初筛多维打标")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--taxonomy", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="只处理前 N 篇（0=全部）")
    ap.add_argument("--gold", default=None, help="仅对 gold 中 path 打标（评估用）")
    args = ap.parse_args()

    manifest = load(args.manifest)
    taxonomy = load(args.taxonomy)
    variant_index = build_variant_index(taxonomy)

    all_md = manifest["documents"]["md"]
    # 非精华 md 路径集合：用于判断精华笔记是否有对应原文
    non_essence_paths = {d["path"] for d in all_md if not d.get("is_essence")}

    def should_process(d):
        if d.get("is_essence"):
            # 精华笔记：同目录有同名 .md 时跳过（原文已被 doc_map 处理）；
            # 无同名 .md（如来自妙记 txt 派生）时作为正文提炼，避免丢主题。
            orig = d["path"][:-len("·精华笔记.md")] + ".md"
            if orig in non_essence_paths:
                return False
        return is_body(d["path"], d.get("size", 0))

    docs = [d["path"] for d in all_md if should_process(d)]

    if args.gold:
        gold_set = {g["path"] for g in load(args.gold)}
        docs = [d for d in docs if d in gold_set]
    docs = sorted(docs)
    if args.limit:
        docs = docs[:args.limit]

    items = [tag_one(p, variant_index) for p in docs]

    reviewed = sum(1 for i in items if i["needs_review"])
    dim_fill = {dim: sum(1 for i in items if i[dim])
                for dim in ["domains", "forms", "tools", "types", "projects"]}
    result = {
        "items": items,
        "summary": {
            "total": len(items), "needs_review": reviewed,
            "dimension_coverage": dim_fill,
            "source_kind_coverage": dict(Counter(
                i["source_kind"] for i in items if i["source_kind"])),
        },
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    print(f"[tag] 处理 {len(items)} 篇；待人工 {reviewed} 篇")
    print(f"[tag] 维度覆盖 {dim_fill}")
    print(f"[tag] 已写出：{args.out}")


if __name__ == "__main__":
    main()
