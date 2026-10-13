#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""progress.py —— 进度**派生**器（只读）。把"抽到哪儿了"从人肉台账变成可复算的读数。

为什么是派生而不是账本：账本要人手工维护就会漂（发现 17），而笔记里的 `source_locator`
本来就是"这块抽过了"的天然凭证——它已经在库里、已被 C5 与逐字校验间接检查过。所以
**progress 只读两样东西**：`工作流/` 的笔记 + `_meta/doc_maps.jsonl`，反推 chunk→笔记 的映射。

```
python scripts/progress.py --notes-dir <KB>/工作流                      # 人读
python scripts/progress.py --notes-dir <KB>/工作流 --format json        # 机器读，逐字节确定
python scripts/progress.py --notes-dir <KB>/工作流 --emit-todo         # 只吐续跑起点一行
python scripts/progress.py --notes-dir <KB>/工作流 --path-prefix 04_   # 只缩小视图，不改判据
python scripts/progress.py --notes-dir <KB>/工作流 --gate              # 显式门禁：本视图不一致非空 → exit 1
python scripts/progress.py --notes-dir <KB>/notes --kb <KB>            # 目录改名/嵌套布局：显式给 KB 根
```

**KB 根默认＝笔记目录的父目录**（`_meta/doc_maps.jsonl` 从它解析）。库是嵌套布局
（如 `kb/content/notes`）时用 `--kb` 显式给出；不给 `--kb` 时与从前逐字节一致。

**退出码**：`0` = 跑完（有几篇没抽都算跑完，默认不是门禁）；`1` = 输入不可用
（笔记目录不存在 / `doc_maps.jsonl` 不存在或 0 行 / 笔记 0 篇——绝不在"什么都没读"的基础上打印进度），
**或** 显式 `--gate` 之下本视图 `inconsistencies` 非空。

**`--gate`（默认关；唯一的显式门禁）**：开启后只看**本视图内**的不一致（给了 `--path-prefix`
就是范围内），非空 → exit 1、空 → exit 0。**判据是结构性错误（定位符落不进块 / 笔记指的文档不在
地图上），不是进度百分比**——全库 5,226 块只抽了 8 块也照样绿，因为它不管抽了多少。**代价要写清**：
带 `--path-prefix` 跑 gate 时**范围外的真实不一致不触发**，那是主动缩小视图的代价，用的人须知。
gate **不产生任何 stdout**（stdout 与不加 `--gate` 逐字节一致，JSON/markdown 消费方不受污染），
判红理由只走 stderr。可与 `--emit-todo` 叠加：一次拿到起点 + 判绿。

**不读 `coverage_audit.jsonl`；不写任何文件；不改 verify 的 C1–C15；不吃 `check_verbatim_lite` /
`check_hooks` 的 warn、不吃 audit 指标、不吃 inbox 占比与处理率——那些一律不进 gate。**

进度语义（只在**高价值块**上算，低密度块天然不算债）：
`done` = 该文档全部高价值块都被 ≥1 篇笔记引用；`partial` = 部分；`todo` = 0 引用；
`no_hv` = 该文档没有高价值块（做不到 done，也不该被当债——不给这一档，纯广告文/目录页会永远 todo）。
分母同时给「全部块」和「高价值块」两栏：只报 12,005 会误导估工，只报 5,226 会丢掉块结构。

两类不一致（`inconsistencies`）：

| 类型 | 含义 | 判据 |
|---|---|---|
| `ghost_locator` | 笔记定位符落不进该文档任何块（源改过 / 偏移写错 / 旧笔记没 locator） | 派生 |
| `unmapped_source` | 笔记 `sources` 指的文档不在 doc_maps 里（doc_map 过期，新补资料没重建） | 派生 |

> **为什么不读 `coverage`**（发现 29，也是发现 17 的根因）：`doc_map.py` 的 chunk 记录里**没有
> status 字段**，声称粒度只存在于文档级 `coverage`，而 chunk 级"这块抽了没"没有中间层承载——
> **任何块级声称都无法回填到文档级计数器**。因此 `coverage.chunks_processed` / `high_value_done`
> 只是 doc_map 生成时的快照，**不由任何脚本维护、progress 也不读**：它们是**已作废的历史字段**，
> 不是"待回填的 TODO"。进度唯一的可信来源就是从笔记反推。两类都是 warn 级，**不影响退出码**。

两条写死的匹配口径（真库实测出来的，不写清必踩）：
① join key = 笔记 `sources[0]` ↔ `doc_maps.path`（都是相对源根的路径）；`doc_id` 不做 join key。
② **`§标题` 不参与定位**，只有 `#char=起-止` 用来落块——真库 11 篇的 § 段写的是**文档标题**，
   而 doc_map 的 `chunk.heading` 只有第 0 块恰好等于文档标题，按 § 标题匹配会把 100% 的合法
   定位符判成 ghost。§ 段给人看，char 给机器用。
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/守卫/GATE 文案走 stderr，同样要包

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from search_index import AGGREGATE_PAGES, DEFAULT_NOTES_DIR   # 目录口径与 build/build_topics/verify/audit 统一
from check_verbatim_lite import fm_list             # 块列表解析：不能用 parse_frontmatter（04 §2.3）

CHAR_RE = re.compile(r"#char=(\d+)-(\d+)")
SCHEMA = "progress-v1"
KINDS = ("ghost_locator", "unmapped_source")


def scan_notes(notes_dir, kb_root):
    """→ 按 rel 排序的 [{rel, source, ranges, locator_items}]。聚合页按 `AGGREGATE_PAGES` 白名单跳过
    （**不再按 `_` 前缀豁免**——前缀形状会让 `_临时.md` 这类文件静默消失，B8 收口）。"""
    out = []
    for dp, _, files in os.walk(notes_dir):
        for fn in files:
            if not fn.endswith(".md") or fn in AGGREGATE_PAGES:
                continue
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, kb_root).replace("\\", "/")
            text = open(p, encoding="utf-8", errors="ignore").read()
            srcs = fm_list(text, "sources")
            locs = fm_list(text, "source_locator")
            ranges = sorted(set((int(a), int(b))
                                for a, b in CHAR_RE.findall(" | ".join(locs))))
            out.append({"rel": rel, "source": srcs[0].strip() if srcs else "",
                        "ranges": ranges, "locator_items": len(locs)})
    out.sort(key=lambda n: n["rel"])
    return out


def load_doc_maps(path):
    docs = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    docs.sort(key=lambda d: d.get("path", ""))
    return docs


def chunk_of(doc, start):
    for c in doc.get("chunks", []):
        if c["char_start"] <= start < c["char_end"]:
            return c
    return None


def derive(notes, maps):
    """核心：笔记 → 高价值块反查 + 三档进度 + 两类不一致。纯计算，不碰磁盘。"""
    by_path = {d["path"]: d for d in maps}
    refs = {}
    incons = []

    for n in notes:
        d = by_path.get(n["source"])
        if not n["source"]:
            incons.append({"type": "ghost_locator", "doc": "", "chunk_id": "", "note": n["rel"],
                           "msg": "sources 为空，定位符无从校验（C5 也管它，这里只报事实）"})
            continue
        if d is None:
            incons.append({"type": "unmapped_source", "doc": n["source"], "chunk_id": "",
                           "note": n["rel"],
                           "msg": "sources 指向的文档不在 doc_maps 里——doc_map 过期或新补资料没重建"})
            continue
        if not n["ranges"]:
            incons.append({"type": "ghost_locator", "doc": d["path"], "chunk_id": "",
                           "note": n["rel"], "msg": "没有可用的 #char= 区间（旧笔记未补定位符）"})
            continue
        for a, _b in n["ranges"]:
            c = chunk_of(d, a)
            if c is None:
                incons.append({"type": "ghost_locator", "doc": d["path"], "chunk_id": "",
                               "note": n["rel"],
                               "msg": "定位符 #char=%d 落不进该文档任何块（源被改过或偏移写错）" % a})
            else:
                lst = refs.setdefault(c["chunk_id"], [])
                if n["rel"] not in lst:
                    lst.append(n["rel"])

    rows, todo_list = [], []
    for d in maps:
        hv = [c for c in d.get("chunks", []) if c.get("high_value")]
        done = [c for c in hv if refs.get(c["chunk_id"])]
        status = ("no_hv" if not hv else
                  "done" if len(done) == len(hv) else
                  "partial" if done else "todo")
        rows.append({"path": d["path"], "doc_id": d.get("doc_id", ""),
                     "total_chunks": len(d.get("chunks", [])),
                     "high_value_chunks": len(hv), "done_chunks": len(done), "status": status,
                     "note_paths": sorted({p for c in hv for p in refs.get(c["chunk_id"], [])})})
        for c in hv:
            if not refs.get(c["chunk_id"]):
                todo_list.append((d["path"], c))

    rows.sort(key=lambda r: r["path"])
    todo_list.sort(key=lambda t: (t[0], t[1]["char_start"]))
    incons.sort(key=lambda i: (i["type"], i["doc"], i["note"]))
    return rows, todo_list, incons


def summarize(rows, notes_total, incons_n):
    hv = sum(r["high_value_chunks"] for r in rows)
    done = sum(r["done_chunks"] for r in rows)
    return {"total_docs": len(rows),
            "done_docs": sum(1 for r in rows if r["status"] == "done"),
            "partial_docs": sum(1 for r in rows if r["status"] == "partial"),
            "todo_docs": sum(1 for r in rows if r["status"] == "todo"),
            "no_hv_docs": sum(1 for r in rows if r["status"] == "no_hv"),
            "total_chunks": sum(r["total_chunks"] for r in rows),
            "total_high_value_chunks": hv,
            "done_chunks": done,
            "undone_high_value_chunks": hv - done,
            "notes_total": notes_total,
            "inconsistencies": incons_n}


def pick_next(todo_list, path_prefix=None):
    """next_todo = **范围内**第一个未完成块。范围由人用 --path-prefix 定；
    脚本只报"这个范围内下一个是谁"，不替你决定跑哪个批次。"""
    pool = [(p, c) for p, c in todo_list if not path_prefix or p.startswith(path_prefix)]
    if not pool:
        return None
    p, c = pool[0]
    return {"doc": p, "chunk_id": c["chunk_id"],
            "reason": "高价值块未成篇｜块长 %d 字｜density %s｜特征 %s"
                      % (c.get("char_len", 0), c.get("density"),
                         ",".join(c.get("features", [])) or "无")}


def _gate_rc(incons_view, gate, path_prefix):
    """`--gate`：唯一的显式门禁。**只作用于退出码**——stdout 一个字都不多打，
    判红理由走 stderr，所以 JSON / markdown 消费方不受污染，不加 --gate 时逐字节不变。
    判据 = **本视图内**的不一致非空（`--path-prefix` 给了就是范围内，范围外的不触发——
    这是主动缩小视图的代价，文档 04 §12.2 明写）。百分比、warn、audit 指标一概不判。"""
    if not gate:
        return 0
    scope = ("前缀 %s 范围内" % path_prefix) if path_prefix else "全库"
    if incons_view:
        kinds = sorted(set(i["type"] for i in incons_view))
        sys.stderr.write("[progress] GATE FAIL：%s %d 条不一致（类型 %s）——"
                         "判据是结构性错误，不是百分比\n"
                         % (scope, len(incons_view), ",".join(kinds)))
        return 1
    sys.stderr.write("[progress] GATE OK：%s 0 条不一致\n" % scope)
    return 0


def _blk(s):
    return ["文档 %d：done %d / partial %d / todo %d / no_hv %d"
            % (s["total_docs"], s["done_docs"], s["partial_docs"],
               s["todo_docs"], s["no_hv_docs"]),
            "高价值块 %d：已抽 %d / 未抽 %d（全部块 %d，含低密度）"
            % (s["total_high_value_chunks"], s["done_chunks"],
               s["undone_high_value_chunks"], s["total_chunks"]),
            "笔记 %d 篇｜不一致 %d 条" % (s["notes_total"], s["inconsistencies"])]


def render(fmt, summary, scope, rows, next_todo, incons, maps_path, notes_dir, path_prefix):
    """带 --path-prefix 时**两份计数都给**：只给范围内的会伪装成全库，
    只给全库的会让人以为过滤器没生效。"""
    if fmt == "json":
        payload = {"schema": SCHEMA, "doc_maps": os.path.abspath(maps_path),
                   "notes_dir": os.path.abspath(notes_dir), "path_prefix": path_prefix or "",
                   "summary": summary, "next_todo": next_todo,
                   "docs": rows, "inconsistencies": incons}
        if path_prefix:
            payload["scope"] = {"path_prefix": path_prefix, "summary": scope,
                                "inconsistencies_in_scope": len(incons)}
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)

    L = ["# 进度派生（%s）" % SCHEMA, ""]
    if path_prefix:
        L += ["## 全库", "```"] + _blk(summary) + ["```", "",
              "## 范围 `--path-prefix %s`" % path_prefix, "```"] + _blk(scope) + ["```", ""]
    else:
        L += ["```"] + _blk(summary) + ["```", ""]
    if next_todo:
        L += ["**next_todo**：%s / %s" % (next_todo["doc"], next_todo["chunk_id"]),
              "> %s" % next_todo["reason"], ""]
    else:
        L += ["**next_todo**：无（%s高价值块已全部成篇）"
              % (("前缀 %s 范围内" % path_prefix) if path_prefix else ""), ""]
    bad = [r for r in rows if r["status"] == "partial"]
    if bad:
        L += ["## 半抽的文档（最危险：看起来在推进，实际漏块）", ""]
        L += ["- `%s` %d/%d" % (r["path"], r["done_chunks"], r["high_value_chunks"])
              for r in bad[:15]]
        L += [""]
    if incons:
        L += ["## 不一致（warn 级，不影响退出码）", ""]
        for i in incons[:30]:
            L.append("- %s｜%s｜%s｜%s"
                     % (i["type"], i["doc"] or "-", i["note"] or "-", i["msg"]))
        if len(incons) > 30:
            L.append("- …另有 %d 条（--format json 看全量）" % (len(incons) - 30))
        L.append("")
    L.append("> 本脚本只读：不写笔记、不写 doc_maps、不动源目录。")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(
        description="进度派生（只读）：chunk↔笔记 反查、三档进度、两类不一致；"
                    "--gate 时本视图不一致非空 → exit 1")
    ap.add_argument("--notes-dir", required=True,
                    help="笔记目录本身（默认口径名 %s）" % DEFAULT_NOTES_DIR)
    ap.add_argument("--doc-maps", default=None, help="默认 <kb>/_meta/doc_maps.jsonl")
    ap.add_argument("--format", choices=["markdown", "json"], default="markdown")
    ap.add_argument("--emit-todo", action="store_true", help="只输出一行续跑起点")
    ap.add_argument("--kb", default=None,
                    help="KB 根；缺省＝笔记目录的父目录（嵌套布局如 kb/content/notes 时显式给出）")
    ap.add_argument("--path-prefix", default=None,
                    help="只缩小 next_todo 与 docs 视图（如 04_），不改判据；默认不过滤")
    ap.add_argument("--gate", action="store_true",
                    help="默认关。开启后**本视图内** inconsistencies 非空 → exit 1；"
                         "判据是结构性错误，不是百分比；stdout 不变，理由走 stderr")
    args = ap.parse_args()

    notes_abs = os.path.abspath(args.notes_dir)
    kb_root = os.path.abspath(args.kb) if args.kb else os.path.dirname(notes_abs)
    maps_path = args.doc_maps or os.path.join(kb_root, "_meta", "doc_maps.jsonl")
    if not os.path.isdir(notes_abs):
        raise SystemExit("[progress] 笔记目录不存在：%s" % notes_abs)
    if not os.path.isfile(maps_path):
        raise SystemExit("[progress] doc_maps 不存在：%s\n"
                         "          先跑：doc_map.py --source-root <源根> --out %s"
                         % (maps_path, maps_path))
    maps = load_doc_maps(maps_path)
    if not maps:
        raise SystemExit("[progress] %s 是 0 行——拒绝在「什么都没读」的基础上打印进度。" % maps_path)
    notes = scan_notes(notes_abs, kb_root)
    if not notes:
        raise SystemExit("[progress] %s 下 0 篇原子笔记——那样算出来会是"
                         "「全库 0 引用」，这不是进度是输入错了。" % notes_abs)

    rows, todo_list, incons = derive(notes, maps)
    summary = summarize(rows, len(notes), len(incons))
    rows_view = [r for r in rows if not args.path_prefix or r["path"].startswith(args.path_prefix)]
    if args.path_prefix:
        keep = set(r["path"] for r in rows_view)
        incons_view = [i for i in incons if not i["doc"] or i["doc"] in keep]
        scope = summarize(rows_view, len(notes), len(incons_view))
    else:
        incons_view = incons
        scope = summary
    next_todo = pick_next(todo_list, args.path_prefix)

    if args.emit_todo:
        if next_todo:
            print("%s\t%s\t%s" % (next_todo["doc"], next_todo["chunk_id"], next_todo["reason"]))
        else:
            print("无（%s范围内高价值块已全部成篇）"
                  % (("前缀 " + args.path_prefix + " ") if args.path_prefix else ""))
        return _gate_rc(incons_view, args.gate, args.path_prefix)
    print(render(args.format, summary, scope, rows_view, next_todo, incons_view,
                 maps_path, notes_abs, args.path_prefix))
    return _gate_rc(incons_view, args.gate, args.path_prefix)


if __name__ == "__main__":
    sys.exit(main())
