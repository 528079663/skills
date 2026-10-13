#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""split_boundaries.py —— 高价值块的**拆篇候选边界**生成器（只读源料，只写 --out）。

为什么要有它：`08 §3` 第 9 条要求「按语义单元拆，不按块拆」，但 05 的实测块长尾很重
（单块最长 30,761 字 / 481 段），要求执行 AI 对着整块自己找边界，既不可复核也易漏。
本脚本把**原文里已有的结构**变成可核对的候选段，交给深抽按语义定夺——
它是提示器与体检表，**不是第二套切块口径**：`doc_map.py` 按标题切块这条约定一字未改，
本脚本只在块**内部**找候选边界。

三条 unit 规约（本批裁决定稿）：
  ① `media_table`：**按内容判**——单元格过半是 URL / 文件名 / 素材占位的表 = 资产索引表，
     默认**不产候选段**（05 实测 184 单位 / 85,691 字）；「文字·数据·标准」型表格是正常
     表格，按语义参与切分（反例：`#60` 的「手动版 VS 进阶自动化」对比表必须保留）。
  ② `fence_atomic`：代码围栏**整体不可切**，且**与它的说明段落粘连**；粘不下才独立成段，
     独立且超 LIMIT 者标 `oversized_fence`（宁可出一段超长的，也不劈代码/劈提示词模板）。
     围栏按**整行**配对（行首 ``` 开、独占一行的 ``` 闭）——不按 ` ```…``` ` 正则配对，
     实测会被正文里的 `content.replaceAll("```json","")` 骗出落在一行中间的假边界。
     闭栏的**反引号数必须 ≥ 开栏数**（05 有 5 处用 ```` 开栏、里面嵌 ``` 示例；
     只认三个反引号会让 ```` 闭栏认不出来，把围栏外正文整段吞进"不可切"——发现 37）。
  ③ `frag` 处置（11 段实测定稿）：超限的普通单位**先试粘连**，条件＝前段是引子
     （以标题行 / 冒号 / 破折号结尾，或前段 ≤400 字）**且未链式**（已带 frag 的段不接受
     第二次粘连）；粘上仍超 LIMIT → 整段标 `oversized_frag` 交深抽按语义再拆。
     **绝不在无结构处硬切造边界**——v1 那样按 1,500 字切，实测把表格与签名 URL 劈成
     半行碎片（#12 的 9 个坏断点全这么来）。

只读：不改 KB、不改 doc_maps、不写任何库内文件；输出只有一个 --out。
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

LIMIT = 1500          # 候选段长度上限（对齐 config.extraction.chunk_size 的上沿）
MIN_LEN = 300         # 达到此长度后，遇伪标题优先断
DENSE_AT = 2          # 段内 ≥ 这么多伪标题 ⇒ 深抽必须按 08 §3 第 9 条再拆
GLUE_PREV = 400       # ③：前段 ≤ 这么长视为“引子”，可粘连
NL = "\n"

BLANK_RE = re.compile("\n[ \t]*\n")
FENCE_OPEN = re.compile("^[ \t]{0,3}(`{3,})")              # 开栏可以是 3 个或**更多**反引号（要记长度）
FENCE_CLOSE = re.compile("^[ \t]{0,3}(`{3,})[ \t]*$")      # 闭栏＝整行只有反引号，且长度 ≥ 开栏长度
TABLE_START = re.compile(r"^\s*(?:\||<table|</table|<tbody|<tr|<colgroup)", re.I)
MEDIA_CELL = re.compile(r"https?://|\]\(|x-oss-|\.(mp4|mov|m4a|mp3|wav|png|jpe?g|gif|webp|pdf|zip)\b"
                        r"|缺失素材|未随文|<img|<video|<audio", re.I)
HEAD_END = re.compile(r"(?:^|\n)#{1,6} .+$|(?:[:：—\-])\s*$", re.M)
PSEUDO = [
    re.compile("^[ \t]{0,3}\\*\\*[^*\n]{2,60}\\*\\*[:：]?[ \t]*$"),
    re.compile("^[ \t]{0,3}\\*\\*[^*\n]{2,60}?\\*\\*"),
    re.compile("^[ \t]{0,3}\\d+(?:\\.\\d+){1,4}[ \t]+\\S"),
    re.compile("^[ \t]{0,3}[一二三四五六七八九十]{1,3}[、.．][ \t]*\\S"),
    re.compile("^[ \t]{0,6}第[ \t]*[0-9一二三四五六七八九十]+[ \t]*[步讲节部课]"),
    re.compile("^[ \t]{0,3}[^*\n]{2,20}[:：][ \t]*$"),
]


def fence_spans(text):
    """按整行配对围栏；未闭合的整段丢弃（宁可不标 atomic，也不凭空造边界）。

    发现 37（本批修）：**闭栏反引号数必须 ≥ 开栏数**。05 里有 5 处用四个反引号开栏的模板
    （` ````JSON ` 包一份内嵌 ``` 示例的 agent 配置），旧写法只认「恰好三个反引号结尾」，
    它们的 ```` 闭栏认不出来，外层围栏被一路配到远处随便一个 ``` 上——实测 5/5 全配错，
    最多的一处把围栏外 11,333 字正文与素材表一起吞成"不可切的原子段"，
    还让那些 media_table 逃过弃区。规约② 的意图（不劈模板）反被破坏。
    """
    spans, open_at, open_len, dangling = [], None, 0, 0
    pos = 0
    for line in text.split(NL):
        start, end = pos, pos + len(line) + 1
        if open_at is None:
            mo = FENCE_OPEN.match(line)
            if mo:
                open_at, open_len = start, len(mo.group(1))
        else:
            mc = FENCE_CLOSE.match(line)
            if mc and len(mc.group(1)) >= open_len:
                spans.append((open_at, end - 1))
                open_at, open_len = None, 0
        pos = end
    if open_at is not None:
        dangling = 1
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged, dangling


def in_spans(pos, spans):
    return any(a <= pos < b for a, b in spans)


def pseudo_kind(text):
    f = text.strip().split(NL, 1)[0].rstrip()
    for rx in PSEUDO:
        if rx.match(f):
            return True
    return False


def cells_of(u):
    cs = [c.strip() for c in u.split("|")]
    cs += re.findall(r"<td>(.*?)</td>", u, re.S)
    return [c for c in cs if c and not set(c) <= set("-: ")]


def is_media_table(u):
    cs = cells_of(u)
    if len(cs) < 2:
        return False
    return sum(1 for c in cs if MEDIA_CELL.search(c)) / len(cs) >= 0.5


def units_of(seg, base, spans):
    """unit 边界 = 围栏外的空行 ∪ 每个围栏的首尾。"""
    bnd = {0, len(seg)}
    for m in BLANK_RE.finditer(seg):
        if not in_spans(base + m.end(), spans):
            bnd.add(m.end())
    for a, b in spans:
        for edge in (a - base, b - base):
            if 0 < edge < len(seg):
                bnd.add(edge)
    ordered = sorted(bnd)
    out = []
    for i in range(len(ordered) - 1):
        s, e = ordered[i], ordered[i + 1]
        if e <= s or not seg[s:e].strip():
            continue
        u = seg[s:e]
        mid = base + (s + e) // 2
        if in_spans(mid, spans) or u.lstrip().startswith("```"):
            cls = "fence"
        elif TABLE_START.match(u.split(NL, 1)[0]) and is_media_table(u):
            cls = "media_table"
        else:
            cls = "normal"
        out.append((s, e - s, pseudo_kind(u), cls))
    return out


def is_intro(prev_text):
    """③ 的“引子”判据：前段以标题行 / 冒号 / 破折号结尾。"""
    t = prev_text.rstrip()
    if not t:
        return False
    last = t.split(NL)[-1].strip()
    return bool(re.match(r"^#{1,6} ", last)) or bool(re.search("[:：—\\-]\\s*$", last))


def pack(units, text, base):
    """返回候选段 [(start, len, pseudo_count, flags)] 与被弃的 media_table 区间。"""
    segs, dropped = [], []
    cur = {"s": 0, "e": 0, "pk": 0, "flags": set(), "on": False}

    def flush():
        if cur["on"] and cur["e"] > cur["s"]:
            segs.append((cur["s"], cur["e"] - cur["s"], cur["pk"], set(cur["flags"])))
        cur["on"], cur["pk"], cur["flags"] = False, 0, set()

    def cur_len():
        return cur["e"] - cur["s"]

    for st, ln, pk, cls in units:
        if cls == "media_table":
            flush()
            dropped.append((st, ln))
            continue
        if cls == "fence":
            if cur["on"] and cur_len() + ln <= LIMIT:
                cur["e"] += ln
                cur["pk"] += int(pk)
                continue
            flush()
            flags = {"oversized_fence"} if ln > LIMIT else set()
            segs.append((st, ln, int(pk), flags))
            continue
        if ln > LIMIT:                                    # ③ 先试粘连，不硬切
            prev_len = cur_len()
            glue = (cur["on"] and "frag" not in cur["flags"]
                    and (prev_len <= GLUE_PREV or is_intro(text[base + cur["s"]:base + st]))
                    and cur_len() + ln <= LIMIT * 3)      # 禁链式 + 给个天花板，防止一路吞
            if glue:
                cur["e"] = st + ln
                cur["pk"] += int(pk)
                cur["flags"].add("frag")
                if cur_len() > LIMIT:
                    cur["flags"].add("oversized_frag")
            else:
                flush()
                cur.update(s=st, e=st + ln, pk=int(pk), on=True,
                           flags={"frag"} | ({"oversized_frag"} if ln > LIMIT else set()))
            continue
        if cur["on"] and (cur_len() + ln > LIMIT or (pk and cur_len() >= MIN_LEN)):
            flush()
        if not cur["on"]:
            cur.update(s=st, e=st + ln, pk=int(pk), on=True)
        else:
            cur["e"] += ln
            cur["pk"] += int(pk)
    flush()
    return segs, dropped


def doc_id_of(path):
    import hashlib
    return "doc-" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:8]


def main():
    global LIMIT
    ap = argparse.ArgumentParser(description="高价值块的拆篇候选边界（只读；只写 --out）")
    ap.add_argument("--doc-maps", required=True, help="doc_map.py 产出的 doc_maps.jsonl")
    ap.add_argument("--source-root", required=True, help="源资料根目录（doc_maps 的 path 相对它）")
    ap.add_argument("--out", required=True, help="候选边界 JSONL 输出路径（不在库内）")
    ap.add_argument("--limit", type=int, default=LIMIT, help="候选段长度上限，默认 %d" % LIMIT)
    args = ap.parse_args()
    LIMIT = args.limit

    if not os.path.isfile(args.doc_maps):
        raise SystemExit("[split] doc_maps 不存在：%s（先跑 doc_map.py）" % args.doc_maps)
    if not os.path.isdir(args.source_root):
        raise SystemExit("[split] 源目录不存在：%s" % args.source_root)

    n_doc = n_blk = n_seg = n_ovf = n_ovs = n_dense = 0
    n_mt = n_mtch = n_dang = 0
    with io.open(args.doc_maps, encoding="utf-8") as fh, \
            io.open(args.out, "w", encoding="utf-8", newline="\n") as out:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            rel = d["path"].replace("\\", os.sep)
            fp = os.path.join(args.source_root, rel)
            if not os.path.isfile(fp):
                raise SystemExit("[split] 源文件不可达：%s" % fp)
            text = io.open(fp, encoding="utf-8", errors="ignore").read()
            spans, dangling = fence_spans(text)
            n_dang += dangling
            hv = [c for c in d.get("chunks", []) if c.get("high_value")]
            rows = []
            for c in hv:
                b0, b1 = c["char_start"], c["char_end"]
                us = units_of(text[b0:b1], b0, spans)
                segs, dropped = pack(us, text, b0)
                n_mt += len(dropped)
                n_mtch += sum(x[1] for x in dropped)
                n_blk += 1
                rows.append({
                    "chunk_id": c["chunk_id"], "heading": c.get("heading", ""),
                    "block_start": b0, "block_len": b1 - b0,
                    "units": len(us), "table_units": len(dropped),
                    "table_chars": sum(x[1] for x in dropped),
                    "segments": [{"rel_start": s, "len": ln, "pseudo": pc,
                                  "dense": pc >= DENSE_AT,
                                  "frag": "frag" in fl,
                                  "oversized_fence": "oversized_fence" in fl,
                                  "oversized_frag": "oversized_frag" in fl,
                                  "locator": "%s#char=%d-%d" % (c.get("heading", ""), b0 + s, b0 + s + ln)}
                                 for s, ln, pc, fl in segs],
                })
                n_seg += len(segs)
                n_ovf += sum(1 for s in segs if "oversized_fence" in s[3])
                n_ovs += sum(1 for s in segs if "oversized_frag" in s[3])
                n_dense += sum(1 for s in segs if s[2] >= DENSE_AT)
            n_doc += 1
            out.write(json.dumps({"doc": d["path"], "doc_id": d.get("doc_id") or doc_id_of(d["path"]),
                                  "fence_dangling": bool(dangling), "blocks": rows},
                                 ensure_ascii=False, sort_keys=True) + NL)
    print("[split] 文档 %d 篇｜高价值块 %d｜候选段 %d（膨胀 %.2f×）"
          % (n_doc or 0, n_blk, n_seg, n_seg / max(n_blk, 1)))
    print("[split] 规约读数：oversized_fence %d｜oversized_frag %d｜dense %d"
          "｜media_table 弃 %d 单位 / %s 字｜未闭合围栏块 %d"
          % (n_ovf, n_ovs, n_dense, n_mt, format(n_mtch, ","), n_dang))
    print("[split] 下一步：深抽按 08 §3 第 9 条在候选段内定篇；dense 段必须再拆，"
          "oversized_* 段交模型按语义定界，不得由脚本硬切。→ %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
