#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""validate_extraction.py — 抽取结果的批量确定性校验（层3，不幻觉兜底）。

检查项（对应 references/08 第 8 节）：
  1. quote 回原文：按 evidence.locator 的字符范围取原文片段，quote（去空白）应在其中；
  2. procedure 步骤连续：steps.order 从 1 连续无缺；
  3. conflict 双源：positions >= 2；
  4. high 置信必有 evidence 三要素；
  5. 高价值块未抽：doc_maps 中 high_value=true 的 chunk 必须有 units 或 coverage=extracted/inbox；
  6. 合并留痕（08 §5.1「禁止只留第一条 locator」）的可检形态：evidence 数组项三要素不齐、
     合并条目指向同一个 locator、procedure 跨 >=2 段却只留 1 段顶层 evidence。
输入守卫：`units.jsonl` 不存在或 0 条 → 直接 exit 1，**不打印「通过」**。
  units 是可选辅助层（08 第 11 节）——没开 units 就不该跑本脚本，它不是非 units 路径的放行依据。
能力边界：units 不记 alias，「合并前声明条数」不可反查；第 6 项只检上面三种可检形态，report 里
  以 `merge_count_checkable: false` + `merge_note` 明写，不假装全检。
输出 _meta/validate_report.json；有错时退出码 1（本批不放行）。
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

LOCATOR_RE = re.compile(r"char=(\d+)-(\d+)")
BACKTICK_RE = re.compile(r"`([^`]+)`")
# claim 里需要逐字回原文的 token：数字/百分比 或 --命令
NUM_OR_CMD_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?|--[\w-]+")


def squash(s):
    return re.sub(r"\s+", "", s or "")


def load_jsonl(path):
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, "r", encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser(description="批量校验抽取结果")
    ap.add_argument("--kb", required=True)
    ap.add_argument("--source-root", required=True, help="原始资料根，用于回原文")
    ap.add_argument("--units", default="_meta/units.jsonl")
    ap.add_argument("--doc-maps", default="_meta/doc_maps.jsonl")
    ap.add_argument("--coverage", default="_meta/coverage_audit.jsonl")
    ap.add_argument("--out", default="_meta/validate_report.json")
    args = ap.parse_args()

    units_path = os.path.join(args.kb, args.units.replace("/", os.sep))
    doc_maps_path = os.path.join(args.kb, args.doc_maps.replace("/", os.sep))
    coverage_path = os.path.join(args.kb, args.coverage.replace("/", os.sep))

    # —— 输入守卫（G1）：措辞与 build_topics.py / search_index build 的守卫同一套 ——
    # 没有这一条时，units.jsonl 不存在 → load_jsonl 返回 [] → 六项检查全 0 → 打印「通过 ✓」exit 0，
    # 等于把"整批没抽任何东西"报成"抽得没问题"。这是假绿，不是没错。
    if not os.path.isfile(units_path):
        raise SystemExit(f"[validate] 输入缺失：{os.path.abspath(units_path)}（不存在）"
                         f"——拒绝给出「通过」。units 是**可选辅助层**：没开 units 的库别跑 validate，"
                         f"它不是非 units 路径的放行依据（见 references/08 第 11 节）。")
    units = load_jsonl(units_path)
    if not units:
        raise SystemExit(f"[validate] 输入缺失：{os.path.abspath(units_path)} 存在但 0 条"
                         f"——拒绝给出「通过」：本批没有任何可校验的抽取结果，"
                         f"先让深抽产出 units.jsonl 再来。")
    doc_maps = load_jsonl(doc_maps_path)
    coverage = load_jsonl(coverage_path)

    quote_mismatch, broken_steps, conflict_short, high_no_ev = [], [], [], []
    missing_code = []
    # —— T6：合并留痕的可检形态（08 §5.1「任何合并都必须保留全部 evidence，禁止只留第一条」）——
    #   evidence_thin     ：数组里某项三要素不齐（file/locator/quote 缺任一）——削剩下的痕迹
    #   evidence_dup      ：合并的多条指向同一个 locator —— 假合并，没真正保留多源
    #   evidence_trimmed  ：procedure 的 steps 跨 >=2 段，顶层 evidence 却只有 <=1 段 —— 只留第一条
    #   合并前声明条数**不可反查**（units 不记 alias），所以这些是"能检的形态"，不是"合并全检"。
    evidence_thin, evidence_dup, evidence_trimmed, merged_units = [], [], [], 0
    src_cache = {}

    def read_src(rel):
        if rel not in src_cache:
            p = os.path.join(args.source_root, rel.replace("/", os.sep))
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    src_cache[rel] = fh.read()
            except OSError:
                src_cache[rel] = None
        return src_cache[rel]

    unit_chunk_ids = set()
    for u in units:
        uid = u.get("id", "?")
        # evidence 可为单对象或合并后的对象数组
        ev = u.get("evidence") or []
        if isinstance(ev, dict):
            ev = [ev]
        ev_list = [e for e in ev if isinstance(e, dict)]
        has_ev = any(e.get("file") and e.get("locator") and e.get("quote")
                     for e in ev_list)
        if u.get("confidence") == "high" and not has_ev:
            high_no_ev.append(uid)
        if u.get("chunk_id"):
            unit_chunk_ids.add(u["chunk_id"])

        # —— T6：合并留痕的可检形态（08 §5.1「任何合并都必须保留全部 evidence，禁止只留第一条」）——
        if len(ev) > 1:
            merged_units += 1
            not_obj = [i for i, e in enumerate(ev) if not isinstance(e, dict)]
            thin = [i for i, e in enumerate(ev_list)
                    if not (e.get("file") and e.get("locator") and e.get("quote"))]
            if not_obj or thin:
                evidence_thin.append({"id": uid, "items": len(ev),
                                      "not_object": not_obj, "missing_fields": thin})
            locs = [e.get("locator") for e in ev_list if e.get("locator")]
            dup = sorted({l for l in locs if locs.count(l) > 1})
            if dup:
                evidence_dup.append({"id": uid, "locators": dup})
        if u.get("type") == "procedure":
            step_locs = {s.get("locator") for s in u.get("steps", []) if s.get("locator")}
            top_locs = {e.get("locator") for e in ev_list if e.get("locator")}
            # 步骤跨 >=2 段出处，顶层 evidence 却只留 <=1 段 = "只留第一条"的残留形态
            if len(step_locs) >= 2 and len(top_locs) <= 1:
                evidence_trimmed.append({"id": uid, "step_locators": sorted(step_locs),
                                         "top_evidence": sorted(top_locs)})

        # 1. quote 回原文（每个 evidence 块都校验）
        for e in ev_list:
            if not (e.get("file") and e.get("locator") and e.get("quote")):
                continue
            m = LOCATOR_RE.search(e["locator"])
            src = read_src(e["file"])
            if src is None or not m:
                continue
            start, end = int(m.group(1)), int(m.group(2))
            seg = src[start:end]
            if squash(e["quote"]) not in squash(seg):
                quote_mismatch.append({"id": uid, "quote": e["quote"][:40],
                                       "locator": e["locator"]})
            # procedure 步骤里的代码/命令逐字出现
            if u.get("type") == "procedure":
                for step in u.get("steps", []):
                    for code in BACKTICK_RE.findall(step.get("action", "")):
                        if squash(code) not in squash(seg):
                            missing_code.append({"id": uid, "code": code})
            # claim 的数字/百分比/命令逐字出现、不归一（1,000 vs 1000 算不符）
            if u.get("type") == "claim":
                blob = str(u.get("text", "")) + " " + str(u.get("metric", ""))
                for tok in NUM_OR_CMD_RE.findall(blob):
                    if squash(tok) not in squash(seg) and squash(tok) not in squash(e["quote"]):
                        missing_code.append({"id": uid, "code": tok})

        # 2. procedure 步骤连续
        if u.get("type") == "procedure":
            orders = sorted(s.get("order") for s in u.get("steps", []))
            if orders != list(range(1, len(orders) + 1)):
                broken_steps.append({"id": uid, "orders": orders})

        # 3. conflict 双源
        if u.get("type") == "conflict" and len(u.get("positions", [])) < 2:
            conflict_short.append(uid)

    # 5. 高价值块未抽
    covered_chunks = {c.get("chunk_id") for c in coverage
                      if c.get("status") in ("extracted", "inbox")}
    touched = unit_chunk_ids | covered_chunks
    unextracted = []
    for dm in doc_maps:
        for ch in dm.get("chunks", []):
            if ch.get("high_value") and ch.get("chunk_id") not in touched:
                unextracted.append(ch.get("chunk_id"))

    merge_checkable = merged_units > 0
    report = {
        "total_units": len(units),
        "quote_mismatch": quote_mismatch,
        "broken_steps": broken_steps,
        "conflict_short": conflict_short,
        "high_no_evidence": high_no_ev,
        "missing_code": missing_code,
        "unextracted_high_value_chunks": unextracted,
        "merged_units": merged_units,
        "evidence_thin": evidence_thin,
        "evidence_dup_locator": evidence_dup,
        "evidence_trimmed": evidence_trimmed,
        # 诚实标注能力边界：units 不记 alias，合并前声明条数**不可反查**（见 08 §5.1）
        "merge_count_checkable": False,
        "merge_note": ("本库有 %d 个合并单元，已检三要素齐全/重复 locator/跨段只留一条三种形态；"
                       "合并前声明条数不可反查（units 无 alias）" % merged_units) if merge_checkable
                      else "本库无合并记录可校验（evidence 全是单来源，未触发合并形态检查）",
        "pass": not (quote_mismatch or broken_steps or conflict_short
                     or high_no_ev or unextracted
                     or evidence_thin or evidence_dup or evidence_trimmed),
    }
    out_path = os.path.join(args.kb, args.out.replace("/", os.sep))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print(f"[validate] 单元 {len(units)}；quote不符 {len(quote_mismatch)}；"
          f"步骤断 {len(broken_steps)}；冲突缺源 {len(conflict_short)}；"
          f"high缺证 {len(high_no_ev)}；高价值块未抽 {len(unextracted)}；"
          f"evidence削痕 {len(evidence_thin) + len(evidence_dup) + len(evidence_trimmed)}")
    print(f"[validate] 合并校验范围：{report['merge_note']}")
    if not report["pass"]:
        print("[validate] 未通过，本批不放行；详见", out_path)
        return 1
    print("[validate] 通过 ✓")
    return 0


if __name__ == "__main__":
    # main() 的返回值必须接到进程退出码上：以前 `main()` 直接丢弃返回值，
    # 导致 docstring 承诺的「有错时退出码 1」从未成立——报一堆错照样 exit 0，
    # SKILL.md 的「validate 必跑、有错不放行」在这条线上是空的。
    sys.exit(main())
