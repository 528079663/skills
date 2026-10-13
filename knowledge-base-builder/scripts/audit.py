#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit：知识库诊断度量（只读）—— skill 自带的「X 光机」，不负责开药方。

与 verify.py 的分工（详见 references/10_audit.md）：

  - verify：二值门禁。PASS / FAIL + exit code，给 CI 与交付验收用，不解释分布。
  - audit ：诊断度量。分布 + 信号，给人看，**不判 PASS/FAIL、不改任何文件**。

硬边界：
  - 只读：不调用 build / build_topics / search_index build，也不调用 verify 的
    `--snapshot-source`（verify 无 `--fix`；它唯一会写的东西是 `_meta/` 下的报告与源目录基线）；
    不写被审计目录下的任何 .md / units.jsonl / topics.json / 索引。
  - 不自动补边、不补 topic、不补 q_hooks，也不给出「该补哪条边」这类处方。
  - 可复跑：两次运行输出逐字节一致（doc_id 排序、无时间戳）。
  - 零新依赖：只用标准库 + 同目录的 search_index / verify。
  - 空库：0 篇时输出空分布，exit 0。
"""
import argparse
import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import search_index as si          # noqa: E402  复用 frontmatter 解析 / 2-gram / units 加载
import verify as vf                # noqa: E402  复用 C12 判定（单一实现）

AUDIT_VERSION = 2                  # v2：A1 拆 explicit / concept 两张图 + graph_mode
DEFAULT_BIGRAM_DF_THRESHOLD = 0.5
DEFAULT_MIN_Q_HOOKS = 3
DEFAULT_TOP_N = 5
DEFAULT_GRAPH_MODE = "both"
GRAPH_MODES = ("explicit", "concept", "both")
# 聚合页**显式白名单**（乙批 B8）：豁免"这篇不是原子笔记"从此靠这张表，不靠 `_` 前缀——
# 前缀是会腐烂的暗号：`_临时.md` 这种文件从前被静默豁免，C4/C9/C11 都看不见它（负控见 P12-dir⑩）。
# `_主题地图.md` **本库不存在**（build_topics 写的是不带下划线的 `00_导航/主题地图.md`），
# 留着是为其他库形状预留；本库实际生效的是 `_流程.md`/`_总览.md`/`_提示词资产.md`/`_模板.md`。
AGGREGATE_PAGES = ("_流程.md", "_总览.md", "_主题地图.md", "_提示词资产.md", "_模板.md")
BAR_WIDTH = 30


# ---------------------------------------------------------------- 扫描（只读）
def scan_notes(notes_dir, kb):
    """扫笔记目录，口径与 build / build_topics 一致：

    只数 `.md`；跳过 `_` 前缀的聚合页（`_流程.md`/`_总览.md`）；frontmatter 解析不出的不计。
    返回 [(rel_path, fm, body)]，按 rel_path 排序（保证可复跑）。
    """
    out = []
    if not os.path.isdir(notes_dir):
        return out
    for dirpath, _, files in os.walk(notes_dir):
        for fn in sorted(files):
            if not fn.endswith(".md") or fn in AGGREGATE_PAGES:   # B8
                continue
            full = os.path.join(dirpath, fn)
            try:
                with io.open(full, encoding="utf-8", errors="ignore") as fh:
                    text = fh.read()
            except OSError:
                continue
            fm = si.parse_frontmatter(text)
            if fm is None:
                continue
            rel = os.path.relpath(full, kb).replace("\\", "/")
            out.append((rel, fm, si.FRONT_RE.sub("", text, count=1)))
    out.sort(key=lambda x: x[0])
    return out


def _ratio(a, b):
    """a/b，分母为 0 时返回 None（报告里显示 —，不伪造 0）。"""
    return None if not b else round(a / b, 4)


def _doc_bigrams(fm, body):
    """该笔记的 n-gram 口径 2-gram 集合（索引口径：标题 + 正文 + 六维字段 + q_hooks）。

    A1 后 gram_units 按脚本分流，「哪些 gram 算 bigram」必须与它同源，所以这里不再
    用「首字是汉字」这种中文专属判据，而是取 **n-gram 段产出的 2 gram**：
    汉字/假名/韩文/泰文段的 2-gram 都计入；字母词与数字整段 token 不参与 DF 阈值判定
    （即便长度恰好为 2，如 "ai"，也不会被 fullmatch 认成 n-gram）。
    """
    text = " ".join([fm.get("title", ""), body,
                     " ".join(" ".join(fm.get(d) or []) for d in si.DIMS),
                     " ".join(fm.get("q_hooks") or [])])
    return {g for g in si.gram_units(text)          # 索引侧口径：drop_stopwords=False
            if len(g) == 2 and si.NGRAM_SEG_RE.fullmatch(g)}


# ---------------------------------------------------------------- A1 relation 连通性
def _resolve_note(name, by_path):
    """把一个名字解析成本库笔记路径——复用 search_index 的三种匹配（路径/文件名/标题）。"""
    if not name:
        return None
    return si._unit_doc_path(name.strip(), by_path)


def _wikilink_targets(body):
    """笔记正文里的 `[[ ]]` 双链目标（复用 verify 的正则，去掉 |别名 与 #锚点）。"""
    out = []
    for m in vf.WIKILINK_RE.finditer(body or ""):
        t = m.group(1).strip().split("#", 1)[0].strip()
        if t:
            out.append(t)
    return out


def _graph_stats(notes, edges, out_deg, in_deg, top_n):
    """把一张图汇总成分布：连通分量、孤岛、度数直方图、逐篇度数。"""
    parent = {rel: rel for rel, _, _ in notes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in sorted(edges):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    comp = {}
    for rel, _, _ in notes:
        comp.setdefault(find(rel), []).append(rel)
    sizes = sorted((len(v) for v in comp.values()), reverse=True)

    rows = [{"doc_id": rel, "out": out_deg[rel], "in": in_deg[rel],
             "degree": out_deg[rel] + in_deg[rel]} for rel, _, _ in notes]
    rows.sort(key=lambda r: (-r["degree"], r["doc_id"]))
    hist = {}
    for r in rows:
        hist[str(r["degree"])] = hist.get(str(r["degree"]), 0) + 1
    isolated = sorted(r["doc_id"] for r in rows if r["degree"] == 0)
    n = len(notes)
    return {
        "edges": len(edges),
        "components": len(comp),
        "largest_component": sizes[0] if sizes else 0,
        "largest_component_ratio": _ratio(sizes[0] if sizes else 0, n),
        "isolated_count": len(isolated),
        "isolated": isolated,
        "isolated_top": isolated[:top_n],
        "degree_histogram": hist,
        "degrees": rows,
    }


def audit_a1(notes, kb, top_n, mode=DEFAULT_GRAPH_MODE):
    """A1 拆成**两张互不合并**的图（口径写进 references/10_audit.md 第 3 节）：

      - **explicit 图**：笔记 → 笔记的**直接指向**，两个来源分别计数——
        ① `[[目标]]` 双链解析到本库笔记；② relation 单元的 subject/object 解析到本库笔记。
        回答「笔记之间有没有**真连线**」。
      - **concept 图**：relation 断言 × **topic 命中**——
        断言方与「topic 里含该端点概念」的其他笔记连边。回答「笔记之间有没有**概念桥**」。

    两张图各自报边数、连通分量、孤岛数、度数分布，**不合并成一个数**：
    explicit 说的是"没有引用跳转"，concept 说的是"没有 topic 交集"——两者是**不同的分布读数**，
    动作完全不同，也**都不构成补链任务**（加不加链由深抽规约决定，见 references/08 第 3.6 节）。
    """
    units = si.load_units(kb)
    rels = [u for u in units if u.get("type") == "relation"
            and u.get("subject") and u.get("object")]
    by_path = {rel: {"title": fm.get("title", "")} for rel, fm, _ in notes}
    n = len(notes)

    unresolved = sorted({u.get("doc_id") or "" for u in rels
                         if _resolve_note(u.get("doc_id"), by_path) is None} - {""})
    out = {"graph_mode": mode, "notes_total": n, "relation_units": len(rels),
           "unresolved_doc_ids": unresolved, "explicit": None, "concept": None}

    # ---- explicit：笔记 → 笔记的直接指向（双链 ∪ relation 端点指向笔记） ----
    if mode in ("explicit", "both"):
        e_out = {rel: 0 for rel, _, _ in notes}
        e_in = {rel: 0 for rel, _, _ in notes}
        e_edges, src = set(), {"wikilink": 0, "relation_endpoint": 0}
        for rel, _, body in notes:
            for tgt in _wikilink_targets(body):
                b = _resolve_note(tgt, by_path)
                if b and b != rel:
                    e_edges.add((rel, b) if rel < b else (b, rel))
                    e_out[rel] += 1
                    e_in[b] += 1
                    src["wikilink"] += 1
        for u in rels:
            a = _resolve_note(u.get("doc_id"), by_path)
            if a is None:
                continue
            for endpoint in {u["subject"], u["object"]}:
                b = _resolve_note(endpoint, by_path)
                if b and b != a:
                    e_edges.add((a, b) if a < b else (b, a))
                    e_out[a] += 1
                    e_in[b] += 1
                    src["relation_endpoint"] += 1
        blk = _graph_stats(notes, e_edges, e_out, e_in, top_n)
        blk["edges_by_source"] = src
        out["explicit"] = blk

    # ---- concept：relation 断言 × topic 命中 ----
    if mode in ("concept", "both"):
        owners = {}          # topic → 拥有它的笔记 rel 列表
        for rel, fm, _ in notes:
            for t in sorted(set(fm.get("topics") or [])):
                owners.setdefault(t, []).append(rel)
        c_out = {rel: 0 for rel, _, _ in notes}
        c_in = {rel: 0 for rel, _, _ in notes}
        c_edges, n_hit = set(), 0
        for u in rels:
            a = _resolve_note(u.get("doc_id"), by_path)
            if a is None:
                continue
            c_out[a] += 1
            for endpoint in {u["subject"], u["object"]}:
                for b in owners.get(endpoint, []):
                    if b != a:
                        c_edges.add((a, b) if a < b else (b, a))
                        c_in[b] += 1
                        n_hit += 1
        blk = _graph_stats(notes, c_edges, c_out, c_in, top_n)
        blk["edges_by_source"] = {"topic_hit": n_hit}
        out["concept"] = blk

    return out


# ---------------------------------------------------------------- A2 topic 结构
def audit_a2(notes, top_n):
    inv = {}
    for rel, fm, _ in notes:
        for t in sorted(set(fm.get("topics") or [])):
            inv.setdefault(t, []).append(rel)
    rows = [{"topic": t, "docs": len(v), "doc_ids": sorted(v)} for t, v in inv.items()]
    rows.sort(key=lambda r: (-r["docs"], r["topic"]))
    exclusive = [r for r in rows if r["docs"] == 1]
    shared = [r for r in rows if r["docs"] >= 2]
    no_topic = sorted(rel for rel, fm, _ in notes if not (fm.get("topics") or []))
    return {
        "topics_total": len(rows),
        "exclusive_count": len(exclusive),
        "shared_count": len(shared),
        "exclusive": [r["topic"] for r in exclusive],
        "notes_without_topic": len(no_topic),
        "notes_without_topic_list": no_topic,
        "notes_without_topic_top": no_topic[:top_n],
        "inverted": rows,
        "inverted_top": rows[:top_n],
    }


# ---------------------------------------------------------------- A3 q_hooks 覆盖率
def audit_a3(notes, min_q_hooks, top_n):
    rows, below, missing, hist = [], [], [], {}
    for rel, fm, _ in notes:
        c = len(fm.get("q_hooks") or [])
        hist[str(c)] = hist.get(str(c), 0) + 1
        if c == 0:
            missing.append(rel)
        elif c < min_q_hooks:
            below.append({"doc_id": rel, "count": c})
        rows.append({"doc_id": rel, "count": c})
    below.sort(key=lambda r: (r["count"], r["doc_id"]))
    missing.sort()
    with_hooks = len(notes) - len(missing)
    return {
        "notes_total": len(notes),
        "with_q_hooks": with_hooks,
        "coverage": _ratio(with_hooks, len(notes)),
        "min_q_hooks": min_q_hooks,
        "below_min_count": len(below),
        "below_min": below,
        "below_min_top": below[:top_n],
        "missing_count": len(missing),
        "missing": missing,
        "missing_top": missing[:top_n],
        "count_histogram": hist,
    }


# ---------------------------------------------------------------- A4 泛化 bigram
def audit_a4(notes, threshold, top_n):
    per_doc = [(rel, _doc_bigrams(fm, body)) for rel, fm, body in notes]
    df = {}
    for _, grams in per_doc:
        for g in grams:
            df[g] = df.get(g, 0) + 1
    n = len(notes)
    generic = sorted(({"gram": g, "df": c, "ratio": _ratio(c, n)}
                      for g, c in df.items() if n and c / n >= threshold),
                     key=lambda r: (-r["df"], r["gram"]))
    gset = {r["gram"] for r in generic}
    doc_rows = []
    for rel, grams in per_doc:
        hit = len(grams & gset)
        doc_rows.append({"doc_id": rel, "grams": len(grams), "generic": hit,
                         "ratio": _ratio(hit, len(grams))})
    doc_rows.sort(key=lambda r: (-(r["ratio"] or 0), r["doc_id"]))
    return {
        "threshold": threshold,
        "bigram_total": len(df),
        "generic_count": len(generic),
        "generic": generic,
        "generic_top": generic[:top_n],
        "notes_generic_ratio": doc_rows,
        "notes_generic_ratio_top": doc_rows[:top_n],
    }


# ---------------------------------------------------------------- A5 stale
def audit_a5(notes, top_n):
    rows = sorted(({"doc_id": rel, "updated": fm.get("updated") or ""}
                   for rel, fm, _ in notes if fm.get("stale")),
                  key=lambda r: r["doc_id"])
    return {
        "notes_total": len(notes),
        "stale_count": len(rows),
        "ratio": _ratio(len(rows), len(notes)),
        "stale": rows,
        "stale_top": rows[:top_n],
    }


# ---------------------------------------------------------------- A6 索引一致性
def audit_a6(kb, notes_name):
    """直接引用 verify 的 C12 判定，不重复实现磁盘比对逻辑。

    索引不存在 → N/A（不 FAIL）；其余结论与 verify 逐字一致。
    """
    status, msg = vf.check_index_consistency(kb, notes_name)
    return {"status": status, "message": msg}


# ---------------------------------------------------------------- 渲染
def _hist_lines(hist):
    if not hist:
        return ["  （空）"]
    items = sorted(hist.items(), key=lambda kv: int(kv[0]))
    w = max(len(k) for k, _ in items)
    mx = max(v for _, v in items) or 1
    return ["  `%*s` │%-*s %d" % (w, k, BAR_WIDTH, "█" * int(round(v / mx * BAR_WIDTH)), v)
            for k, v in items]


def _pct(x):
    return "—" if x is None else "%.1f%%" % (x * 100)


def _a1_block(L, name, desc, blk, top_n):
    """渲染 A1 的一张图：边数（含来源拆分）、分量、孤岛、度数分布与样例。"""
    L.append("### %s 图" % name)
    L.append("")
    L.append(desc)
    L.append("")
    if name == "explicit":
        s = blk["edges_by_source"]
        L.append("- 边 **%d** 条（`[[ ]]` 双链 %d / relation 端点指向笔记 %d；来源计数不去重）"
                 % (blk["edges"], s["wikilink"], s["relation_endpoint"]))
    else:
        L.append("- 边 **%d** 条（topic 命中 %d 次）"
                 % (blk["edges"], blk["edges_by_source"]["topic_hit"]))
    L.append("- 连通分量 **%d** 个，最大分量 %d 篇（%s）；孤岛（度数 0）**%d 篇**"
             % (blk["components"], blk["largest_component"],
                _pct(blk["largest_component_ratio"]), blk["isolated_count"]))
    L.append("")
    L.append("度数分布（度数 │ 篇数）：")
    L.append("")
    L.extend(_hist_lines(blk["degree_histogram"]))
    L.append("")
    if blk["isolated_top"]:
        L.append("孤岛样例（top%d）：" % top_n)
        L.append("")
        for d in blk["isolated_top"]:
            L.append("- `%s`" % d)
        L.append("")
    L.append("度数最高样例（top%d，全量见 json `degrees`）：" % top_n)
    L.append("")
    L.append("| doc_id | 出度 | 入度 | 度数 |")
    L.append("| --- | --- | --- | --- |")
    for r in blk["degrees"][:top_n]:
        L.append("| `%s` | %d | %d | **%d** |" % (r["doc_id"], r["out"], r["in"], r["degree"]))
    L.append("")


def render_markdown(rep):
    t = rep["thresholds"]
    L = []
    L.append("# 知识库 audit 报告")
    L.append("")
    L.append("- 扫描目录：`%s`（KB 根 `%s`）" % (rep["notes_dir"], rep["kb_root"]))
    L.append("- 笔记总数：**%d**" % rep["notes_total"])
    L.append("- 阈值：`bigram-df-threshold=%s`、`min-q-hooks=%s`、`top-n=%s`"
             % (t["bigram_df_threshold"], t["min_q_hooks"], t["top_n"]))
    L.append("- audit v%d（只读：未修改任何文件；不判 PASS/FAIL——那是 verify 的活）"
             % rep["audit_version"])
    L.append("")
    a1, a2, a3 = rep["A1_relation_connectivity"], rep["A2_topic_structure"], rep["A3_q_hooks_coverage"]
    a4, a5, a6 = rep["A4_generic_bigram"], rep["A5_stale"], rep["A6_index_consistency"]
    L.append("## 总览")
    L.append("")
    L.append("| 检查项 | 关键指标 | 值 |")
    L.append("| --- | --- | --- |")
    a1_sum = " / ".join("%s 孤岛 %d" % (k, a1[k]["isolated_count"])
                        for k in ("explicit", "concept") if a1.get(k))
    L.append("| A1 relation 连通性 | graph_mode=`%s`；两张图分开报 | %s |"
             % (a1["graph_mode"], a1_sum))
    L.append("| A2 topic 结构 | 主题数（独占 / 共享） | %d（%d / %d）"
             % (a2["topics_total"], a2["exclusive_count"], a2["shared_count"]))
    L.append("| A3 q_hooks 覆盖率 | 有 q_hooks 的笔记 | %d / %d（%s）"
             % (a3["with_q_hooks"], a3["notes_total"], _pct(a3["coverage"])))
    L.append("| A4 泛化 bigram | DF 占比 ≥ %s 的 bigram | %d / %d 个"
             % (a4["threshold"], a4["generic_count"], a4["bigram_total"]))
    L.append("| A5 stale | 带 stale 标记 | %d 篇（%s）"
             % (a5["stale_count"], _pct(a5["ratio"])))
    L.append("| A6 索引一致性 | 引用 verify C12 判定 | %s" % a6["status"])
    L.append("")

    L.append("## A1 relation 连通性")
    L.append("")
    L.append("- `--graph-mode %s`；relation 单元 %d 条" % (a1["graph_mode"], a1["relation_units"]))
    L.append("- 两张图**分别统计、不合并**：explicit 孤岛=没有引用跳转，concept 孤岛=没有 topic 交集"
             "（都是分布读数，**不构成补链任务**，见 references/08 第 3.6 节）")
    L.append("")
    if a1.get("explicit"):
        _a1_block(L, "explicit",
                  "笔记 → 笔记的**直接指向**（`[[ ]]` 双链 ∪ relation 端点指向笔记）"
                  "——回答「笔记之间有没有真连线」。", a1["explicit"], t["top_n"])
    if a1.get("concept"):
        _a1_block(L, "concept",
                  "relation 断言 × **topic 命中**——回答「笔记之间有没有概念桥」。",
                  a1["concept"], t["top_n"])
    if a1["unresolved_doc_ids"]:
        L.append("doc_id 解析不到笔记的 relation 单元：%d 个（%s）"
                 % (len(a1["unresolved_doc_ids"]),
                    "、".join("`%s`" % x for x in a1["unresolved_doc_ids"][:t["top_n"]])))
        L.append("")

    L.append("## A2 topic 结构")
    L.append("")
    L.append("- 主题 %d 个：独占（只被 1 篇用）**%d** 个，共享（≥2 篇）**%d** 个"
             % (a2["topics_total"], a2["exclusive_count"], a2["shared_count"]))
    L.append("- 无 topic 的笔记 **%d** 篇" % a2["notes_without_topic"])
    L.append("")
    if a2["notes_without_topic_top"]:
        L.append("无 topic 样例（top%d）：" % t["top_n"])
        L.append("")
        for d in a2["notes_without_topic_top"]:
            L.append("- `%s`" % d)
        L.append("")
    L.append("topic 倒排表（篇数最高 top%d，全量见 json `A2_topic_structure.inverted`）："
             % t["top_n"])
    L.append("")
    L.append("| topic | 篇数 |")
    L.append("| --- | --- |")
    for r in a2["inverted_top"]:
        L.append("| %s | **%d** |" % (r["topic"], r["docs"]))
    L.append("")

    L.append("## A3 q_hooks 覆盖率")
    L.append("")
    L.append("- 有 q_hooks：**%d / %d**（%s）；缺失 %d 篇；条数 < %s 的 %d 篇"
             % (a3["with_q_hooks"], a3["notes_total"], _pct(a3["coverage"]),
                a3["missing_count"], a3["min_q_hooks"], a3["below_min_count"]))
    L.append("")
    L.append("条数分布（条数 │ 篇数）：")
    L.append("")
    L.extend(_hist_lines(a3["count_histogram"]))
    L.append("")
    if a3["below_min_top"]:
        L.append("有 q_hooks 但条数 < %s（top%d）：" % (a3["min_q_hooks"], t["top_n"]))
        L.append("")
        for r in a3["below_min_top"]:
            L.append("- `%s`（%d 条）" % (r["doc_id"], r["count"]))
        L.append("")
    if a3["missing_top"]:
        L.append("完全没有 q_hooks（top%d）：" % t["top_n"])
        L.append("")
        for d in a3["missing_top"]:
            L.append("- `%s`" % d)
        L.append("")

    L.append("## A4 泛化 bigram")
    L.append("")
    L.append("- 全库 2-gram %d 个；DF/总篇数 ≥ **%s** 的泛化 bigram **%d** 个"
             % (a4["bigram_total"], a4["threshold"], a4["generic_count"]))
    L.append("")
    L.append("泛化 bigram（DF 最高 top%d，全量见 json `A4_generic_bigram.generic`）："
             % t["top_n"])
    L.append("")
    L.append("| bigram | DF | DF/总篇数 |")
    L.append("| --- | --- | --- |")
    for r in a4["generic_top"]:
        L.append("| %s | **%d** | %s |" % (r["gram"], r["df"], _pct(r["ratio"])))
    L.append("")
    L.append("每篇笔记的泛化 bigram 占比（最高 top%d，全量见 json "
             "`A4_generic_bigram.notes_generic_ratio`）：" % t["top_n"])
    L.append("")
    L.append("| doc_id | 2-gram 数 | 泛化命中 | 占比 |")
    L.append("| --- | --- | --- | --- |")
    for r in a4["notes_generic_ratio_top"]:
        L.append("| `%s` | %d | %d | %s |" % (r["doc_id"], r["grams"], r["generic"],
                                              _pct(r["ratio"])))
    L.append("")

    L.append("## A5 stale / 过期")
    L.append("")
    L.append("- 带 stale 标记 **%d 篇**（%s）" % (a5["stale_count"], _pct(a5["ratio"])))
    L.append("")
    if a5["stale_top"]:
        L.append("| doc_id | updated |")
        L.append("| --- | --- |")
        for r in a5["stale_top"]:
            L.append("| `%s` | %s |" % (r["doc_id"], r["updated"] or "—"))
        L.append("")

    L.append("## A6 索引一致性")
    L.append("")
    L.append("- 判定来源：verify 的 C12（同一函数，不重复实现）")
    L.append("- 状态：**%s** — %s" % (a6["status"], a6["message"]))
    L.append("")
    L.append("> audit 只报「是什么」，不报「该补哪条边」——那是人 / 下一轮的事。")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(
        prog="audit", description="知识库诊断度量（只读；不判 PASS/FAIL，那是 verify 的活）")
    ap.add_argument("--notes-dir", default=si.DEFAULT_NOTES_DIR,
                    help="笔记目录（默认 %s）；KB 根取其父目录，_meta/ 从 KB 根解析，"
                         "或用 --kb 显式给出"
                         % si.DEFAULT_NOTES_DIR)
    ap.add_argument("--kb", default=None,
                    help="KB 根；缺省＝笔记目录的父目录（嵌套布局如 kb/content/notes 时显式给出）")
    ap.add_argument("--format", choices=["markdown", "json"], default="markdown")
    ap.add_argument("--out", default=None,
                    help="报告输出文件；不得落在被审计目录内（只读护栏）")
    ap.add_argument("--graph-mode", choices=list(GRAPH_MODES), default=DEFAULT_GRAPH_MODE,
                    help="A1 的图口径：explicit（笔记→笔记显式连线）/ concept（relation × "
                         "topic 命中）/ both（两张图分别统计，默认）")
    ap.add_argument("--bigram-df-threshold", type=float,
                    default=DEFAULT_BIGRAM_DF_THRESHOLD)
    ap.add_argument("--min-q-hooks", type=int, default=DEFAULT_MIN_Q_HOOKS)
    ap.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    args = ap.parse_args()

    notes_dir = args.notes_dir
    kb = os.path.abspath(args.kb) if args.kb else (os.path.dirname(os.path.abspath(notes_dir)) or os.getcwd())
    notes_name = os.path.basename(os.path.normpath(notes_dir))
    if not os.path.isdir(notes_dir):
        sys.stderr.write("[audit] 笔记目录不存在：%s\n" % notes_dir)
        raise SystemExit(2)

    # 只读护栏：报告不得写进被审计的库
    if args.out:
        out_abs = os.path.abspath(args.out)
        for root in (os.path.abspath(notes_dir), kb):
            if out_abs == root or out_abs.startswith(root + os.sep):
                sys.stderr.write(
                    "[audit] 拒绝写入：--out 落在被审计目录内（%s）。audit 只读。\n" % args.out)
                raise SystemExit(2)

    notes = scan_notes(notes_dir, kb)
    top_n = args.top_n
    rep = {
        "audit_version": AUDIT_VERSION,
        "notes_dir": notes_dir,
        "kb_root": kb,          # 复用上面解析出的 kb（--kb 生效时报告里的 KB 根才不是假话）
        "notes_total": len(notes),
        "thresholds": {"bigram_df_threshold": args.bigram_df_threshold,
                       "min_q_hooks": args.min_q_hooks,
                       "top_n": top_n,
                       "graph_mode": args.graph_mode},
        "A1_relation_connectivity": audit_a1(notes, kb, top_n, args.graph_mode),
        "A2_topic_structure": audit_a2(notes, top_n),
        "A3_q_hooks_coverage": audit_a3(notes, args.min_q_hooks, top_n),
        "A4_generic_bigram": audit_a4(notes, args.bigram_df_threshold, top_n),
        "A5_stale": audit_a5(notes, top_n),
        "A6_index_consistency": audit_a6(kb, notes_name),
    }
    text = (json.dumps(rep, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            if args.format == "json" else render_markdown(rep))
    if args.out:
        with io.open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print("[audit] 报告已写出：%s（format=%s，只读，未改动被审计库）"
              % (args.out, args.format))
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
