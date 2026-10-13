#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""evaluate.py — 入库分类与检索召回的量化评估 + 门禁。

子命令：
  classify   多标签黄金集 gold.json vs tags_pred.json → 每维度 P/R/F1、micro/macro-F1、误报漏报
  retrieval  黄金查询集（含项目级）→ Precision@k / Recall@k / MRR / nDCG@k / P95 延迟
门禁阈值（对应 references/07）：分类每维度 F1≥0.85；项目 Recall@k≥0.9、MRR≥0.8、P95<300ms。
"""
import argparse
import json
import math
import os
import sys
import time
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import search_index as si  # noqa: E402

DIMS = ["domains", "forms", "tools", "types", "projects"]
F1_GATE = 0.85
PROJ_RECALL_GATE = 0.9
MRR_GATE = 0.8
P95_GATE_MS = 300


def load(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return round(p, 4), round(r, 4), round(f, 4)


# ---------- 分类评估 ----------
def eval_classify(gold, pred):
    pred_map = {i["path"]: i for i in pred["items"]}
    counts = {d: {"tp": 0, "fp": 0, "fn": 0} for d in DIMS}
    active_dims = set()
    errors = Counter()

    for g in gold["items"]:
        p = pred_map.get(g["path"], {})
        for d in DIMS:
            gset, pset = set(g.get(d, [])), set(p.get(d, []))
            if gset:
                active_dims.add(d)
            c = counts[d]
            c["tp"] += len(gset & pset)
            c["fp"] += len(pset - gset)
            c["fn"] += len(gset - pset)
            for x in pset - gset:
                errors[f"{d} 误报「{x}」"] += 1
            for x in gset - pset:
                errors[f"{d} 漏报「{x}」"] += 1

    per_dim, tp_all = {}, [0, 0, 0]
    for d in DIMS:
        c = counts[d]
        p, r, f = prf(c["tp"], c["fp"], c["fn"])
        per_dim[d] = {"precision": p, "recall": r, "f1": f, **c}
        tp_all[0] += c["tp"]
        tp_all[1] += c["fp"]
        tp_all[2] += c["fn"]

    mp, mr, mf1 = prf(*tp_all)  # micro
    checked = [per_dim[d]["f1"] for d in active_dims]
    macro_f1 = round(sum(checked) / len(checked), 4) if checked else 0.0
    gate = bool(checked) and all(f >= F1_GATE for f in checked)

    return {
        "n_gold": len(gold["items"]), "per_dimension": per_dim,
        "micro": {"precision": mp, "recall": mr, "f1": mf1},
        "macro_f1": macro_f1,
        "top_errors": errors.most_common(12),
        "gate": gate,
        "gate_rule": f"每个出现过的维度 F1 ≥ {F1_GATE}",
    }


# ---------- 检索评估 ----------
def eval_retrieval(kb, gq, k):
    rows, latencies = [], []
    for q in gq["queries"]:
        is_project = q.get("type") == "project"
        relevant = set(q["relevant_paths"])
        # 项目拉取=确定性过滤：取足够大 k 验证完整性/精度；普通查询用给定 k 看排序
        kk = max(k, len(relevant)) if is_project else k
        scored, elapsed = si.run_query(
            kb, q.get("filters", {}), q.get("keywords", ""),
            q.get("exclude", []), q.get("rank", []), 1000)
        latencies.append(elapsed)
        ranked = [d["path"] for d, _ in scored][:kk]
        hits = [p in relevant for p in ranked]

        precision_k = round(sum(hits) / kk, 4)
        recall_k = round(sum(hits) / len(relevant), 4) if relevant else 0.0
        rr = next((1 / (i + 1) for i, h in enumerate(hits) if h), 0.0)
        dcg = sum((1 if h else 0) / math.log2(i + 2) for i, h in enumerate(hits))
        idcg = sum(1 / math.log2(i + 2) for i in range(min(len(relevant), kk)))
        ndcg = round(dcg / idcg, 4) if idcg else 0.0
        rows.append({
            "name": q["name"], "type": q.get("type", "normal"), "k_used": kk,
            "precision": precision_k, "recall": recall_k,
            "MRR": round(rr, 4), "nDCG": ndcg,
            "returned": len(ranked), "latency_ms": round(elapsed, 1),
        })

    def mean(key, subset=None):
        data = [r[key] for r in rows if subset is None or r["type"] == subset]
        return round(sum(data) / len(data), 4) if data else 0.0

    lat_sorted = sorted(latencies)
    p95 = lat_sorted[min(len(lat_sorted) - 1,
                         int(math.ceil(0.95 * len(lat_sorted))) - 1)]
    proj = [r for r in rows if r["type"] == "project"]
    proj_recall = round(sum(r["recall"] for r in proj) / len(proj), 4) \
        if proj else mean("recall")
    mrr = mean("MRR")
    gate = proj_recall >= PROJ_RECALL_GATE and mrr >= MRR_GATE and p95 < P95_GATE_MS

    return {
        "base_k": k, "queries": rows,
        "summary": {
            "mean_recall": mean("recall"),
            "project_recall": proj_recall,
            "mean_MRR": mrr,
            "mean_nDCG": mean("nDCG"),
            "P95_latency_ms": round(p95, 1),
        },
        "gate": gate,
        "gate_rule": f"项目Recall≥{PROJ_RECALL_GATE}、MRR≥{MRR_GATE}、P95<{P95_GATE_MS}ms",
    }


def report(title, result, out):
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f"===== {title} =====")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"[gate] {'通过 ✅' if result['gate'] else '未通过 ❌'}（{result['gate_rule']}）")
    print(f"[eval] 报告已写出：{out}")


def main():
    ap = argparse.ArgumentParser(description="入库与检索量化评估")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("classify")
    c.add_argument("--gold", required=True)
    c.add_argument("--pred", required=True)
    c.add_argument("--out", required=True)

    r = sub.add_parser("retrieval")
    r.add_argument("--kb", required=True)
    r.add_argument("--gold-queries", required=True)
    r.add_argument("--k", type=int, default=20)
    r.add_argument("--out", required=True)

    args = ap.parse_args()
    if args.cmd == "classify":
        result = eval_classify(load(args.gold), load(args.pred))
        report("分类评估", result, args.out)
    else:
        result = eval_retrieval(args.kb, load(args.gold_queries), args.k)
        report("检索评估", result, args.out)


if __name__ == "__main__":
    main()
