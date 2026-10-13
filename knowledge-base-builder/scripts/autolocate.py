#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""autolocate.py —— 定位符由脚本算，模型/人只交 quote（08 §3 第 8 条的落地器）。

两个子命令：
  --compute  给「源文件 + 一段引文」，输出该引文的 `§标题#char=a-b`。
             唯一命中才算数；多处命中＝报歧义并打印每处 ±30 字上下文；
             零命中＝先去空白/加粗标记再试一次，命中则报"归一化后才找到"并给映射回原文的区间；
             仍找不到＝点名"源里没有这句"。
  --check    给一篇笔记，逐条复核它写着的 locator：
             ① evidence 行：用 --compute 的同一套逻辑反算，区间与标题必须**逐字相等**；
             ② 清单行 `[char=a-b]`：该行文字在本篇已立据的 evidence 区间里找**最佳匹配**，
                若最佳匹配区间 ≠ 标注区间即报"该条更像指向 X-Y，不是标注的 A-B"。

它是**门禁不是提示器**：任何不一致都 rc≠0（与 warn-only 的 check_verbatim_lite 明确分工）。
标题一律从 `doc_maps.jsonl` 读（char 落在哪个块就用那个块的 heading），不手抄——
手抄标题正是上一批"区间对、标题错"那类错位的来源之一。
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LOC_RE = re.compile(r"#char=(\d+)-(\d+)")
EV_LINE = re.compile(r"^>\s*(?P<q>.*?)\s*$", re.M)
CIT = re.compile(r"^> —— `§(?P<h>.*?)#char=(?P<a>\d+)-(?P<b>\d+)`", re.M)
TODO = re.compile(r"^\d+\.\s+(?P<txt>.*?)\s*——\s*\[char=(?P<a>\d+)-(?P<b>\d+)\]", re.M)
FM_LIST = re.compile(r"^sources:\n((?:[ \t]+- [^\n]+\n)+)", re.M)
STRIP = re.compile(r"[\s\u3000*`#>\"“”'’‘，。、：；（）()\[\]{}!！?？—\-~·|]")
STOP = set("的了是在有和与就都不也很这那个么怎么办如何做一二三四五六七八九十".strip())


def die(msg, code=1):
    sys.stderr.write("[autolocate] %s\n" % msg)
    raise SystemExit(code)


def norm(s):
    return "".join(ch for ch in (s or "") if not STRIP.match(ch))


def norm_map(raw):
    """返回 (归一化串, 每个归一化字符对应的原文下标)——用于把归一化命中映射回原文区间。
       剥的东西必须与 `norm` 同一份 STRIP：只剥空白会让「原文有反引号、引文没抄」这类引文永远找不到。"""
    chars, idx = [], []
    for i, ch in enumerate(raw):
        if STRIP.match(ch):
            continue
        chars.append(ch)
        idx.append(i)
    return "".join(chars), idx


def load_doc_maps(path):
    if not path or not os.path.isfile(path):
        return None
    out = []
    for line in io.open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            d = json.loads(line)
            out.append({"path": d.get("path"), "doc_id": d.get("doc_id"),
                        "chunks": [(c.get("heading", ""), c.get("char_start"), c.get("char_end"))
                                   for c in d.get("chunks", [])]})
    return out


def heading_for(maps, rel, a):
    """标题从 doc_maps 读：先按 path 找文档（两种写法都认），再找包住 a 的块。"""
    if not maps:
        return "(无 doc_maps，未校验标题)"
    cand = [m for m in maps if m["path"] and (m["path"].replace("\\", "/") == rel
            or m["path"].endswith("/" + os.path.basename(rel)) or os.path.basename(rel) in m["path"])]
    if not cand:
        return "(doc_maps 里没有这篇：%s)" % rel
    for h, s, e in cand[0]["chunks"]:
        if s is not None and s <= a < e:
            return h
    return "(char=%d 不在任何块里)" % a


def compute(raw, quote, rel, maps, quiet=False):
    """唯一命中 → (heading, a, b, note)；否则抛 (kind, payload)。"""
    exact = []
    start = 0
    while True:
        i = raw.find(quote, start)
        if i < 0:
            break
        exact.append(i)
        start = i + 1
    if len(exact) == 1:
        a, b = exact[0], exact[0] + len(quote)
        return {"kind": "ok", "a": a, "b": b, "heading": heading_for(maps, rel, a), "how": "逐字唯一命中"}
    if len(exact) > 1:
        ctx = [{"a": i, "ctx": raw[max(0, i - 30):i + len(quote) + 30]} for i in exact]
        return {"kind": "ambiguous", "hits": ctx}
    nq = norm(quote)
    if nq:
        nr, idx = norm_map(raw)
        hits = []
        s = 0
        while True:
            i = nr.find(nq, s)
            if i < 0:
                break
            hits.append(i)
            s = i + 1
        if len(hits) == 1:
            a, b = idx[hits[0]], idx[hits[0] + len(nq) - 1] + 1
            return {"kind": "ok", "a": a, "b": b, "heading": heading_for(maps, rel, a),
                    "how": "去空白/去标记后才命中（引文与原文不是逐字相等）"}
        if len(hits) > 1:
            return {"kind": "ambiguous",
                    "hits": [{"a": idx[h], "ctx": raw[idx[h]:idx[h] + 60]} for h in hits]}
    return {"kind": "notfound"}


def cmd_compute(args):
    raw = io.open(args.src, encoding="utf-8", errors="ignore").read()
    maps = load_doc_maps(args.doc_maps)
    rel = os.path.basename(args.src)
    r = compute(raw, args.quote, rel, maps)
    if r["kind"] == "ok":
        line = "§%s#char=%d-%d" % (r["heading"], r["a"], r["b"])
        if args.json:
            print(json.dumps({"ok": True, "locator": line, "how": r["how"]}, ensure_ascii=False))
        else:
            print(line + "　（%s）" % r["how"])
        return 0
    if r["kind"] == "ambiguous":
        sys.stderr.write("[autolocate] 歧义：该引文在源里出现 %d 次，要求加宽上下文。每处 ±30 字：\n"
                         % len(r["hits"]))
        for h in r["hits"][:6]:
            sys.stderr.write("   char≈%d ｜…%s…\n" % (h["a"], h["ctx"].replace("\n", "⏎")[:90]))
        return 2
    die("零命中：源文件里没有这句（逐字与归一化两轮都没找到）。拒绝编造区间。", 3)


def parse_note(path):
    txt = io.open(path, encoding="utf-8", errors="ignore").read()
    src = FM_LIST.search(txt + "\n")
    sources = [l.strip()[1:].strip() for l in (src.group(1).splitlines() if src else [])]
    evs = []
    lines = txt.split("\n")
    for i, l in enumerate(lines):
        m = CIT.match(l)
        if not m:
            continue
        q = []
        j = i - 1
        # 往上收到"紧邻本行的 quote 段"为止：空行、或**另一条 evidence 的引用行**都要停。
        # 不停在引用行上会把上一条的 `—— §…#char=` 当成正文吞进来（老笔记是"一行 quote 一行引用"
        # 紧挨着排的、中间不空行，实测 8 篇因此被误判成"逐字不可回放"）。
        while j >= 0 and lines[j].startswith("> ") and not CIT.match(lines[j]):
            q.insert(0, lines[j][2:])
            j -= 1
        quote = "\n".join(q).strip()
        if quote:
            evs.append({"quote": quote, "h": m.group("h"), "a": int(m.group("a")), "b": int(m.group("b"))})
    todos = [{"txt": m.group("txt"), "a": int(m.group("a")), "b": int(m.group("b"))}
             for m in TODO.finditer(txt)]
    return sources, evs, todos


def toks_of(s):
    """CJK 段切**二元组**＋拉丁整词。用整段词不行：`转场多`／`转场少` 这种一段话会被当成一个 token，
       两处交集都是空，判据就退化成"永远通过"（实测第一版就栽在这儿）。"""
    out = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", s or ""):
        for i in range(len(run) - 1):
            out.add(run[i:i + 2])
        if len(run) == 1:
            out.add(run)
    for w in re.findall(r"[A-Za-z][A-Za-z0-9_.\-]{2,}|\d[\d,.]{1,}", (s or "").lower()):
        out.add(w)
    return out - {t for t in out if t in STOP}


def best_match(item_txt, evs, raw):
    """在本篇已立据的 evidence 区间里挑与清单行文字最贴合的一个（相对判据，不设绝对阈值）。"""
    toks = toks_of(item_txt)
    best, bestscore = None, -1.0
    for e in evs:
        st = toks_of(raw[e["a"]:e["b"]])
        score = len(toks & st) / max(1, len(toks))
        if score > bestscore:
            best, bestscore = e, score
    return best, bestscore


def cmd_check(args):
    src_dir = args.source_root.rstrip("/\\")
    maps = load_doc_maps(args.doc_maps)
    sources, evs, todos = parse_note(args.check)
    if not sources:
        die("%s：frontmatter 没有 sources，无法定位源文件" % args.check)
    src_rel = sources[0].strip('"')
    raw_path = src_rel if os.path.isabs(src_rel) else os.path.join(src_dir, src_rel)
    if not os.path.isfile(raw_path) and os.sep == "\\":
        alt = os.path.join(src_dir, src_rel.replace("/", os.sep))
        raw_path = alt if os.path.isfile(alt) else raw_path
    if not os.path.isfile(raw_path):
        die("%s：源文件不可达 %s" % (args.check, raw_path))
    raw = io.open(raw_path, encoding="utf-8", errors="ignore").read()
    bad, ok_n = [], 0
    for e in evs:
        r = compute(raw, e["quote"], src_rel, maps)
        if r["kind"] != "ok":
            bad.append("evidence 不可复算（%s）：%s…" % (r["kind"], e["quote"][:30]))
        elif (r["a"], r["b"]) != (e["a"], e["b"]):
            bad.append("evidence 标注 char=%d-%d，实际在 char=%d-%d：%s…" % (
                e["a"], e["b"], r["a"], r["b"], e["quote"][:30]))
        elif args.check_heading and r["heading"] != e["h"]:
            bad.append("标题手抄不符：标注 %r，doc_maps 里是 %r" % (e["h"], r["heading"]))
        else:
            ok_n += 1
    todo_ok = 0
    for td in todos:
        # 每一行都算最佳匹配：贴到本篇**另一条** evidence 的区间上，正是上一批那 10 处错位的形状，
        # 所以不能只判"是不是本篇某条区间"（那样永远过），必须判"是不是最贴合的那一条"。
        cited = next((e for e in evs if (e["a"], e["b"]) == (td["a"], td["b"])), None)
        best, best_score = best_match(td["txt"], evs, raw)
        cited_score = -1.0 if cited is None else best_match(td["txt"], [cited], raw)[1]
        if best is not None and best_score > 0 and cited_score < best_score:
            bad.append("清单行标注 char=%d-%d（贴合度 %.2f），更贴合的是 char=%d-%d（%.2f）：%s" % (
                td["a"], td["b"], cited_score, best["a"], best["b"], best_score, td["txt"][:34]))
        else:
            todo_ok += 1
    print("[autolocate check] %s｜evidence %d 条复算通过 %d｜清单 %d 条通过 %d" % (
        os.path.basename(args.check), len(evs), ok_n, len(todos), todo_ok))
    for b in bad:
        print("   ✗ " + b)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description="定位符计算器／笔记复核器（门禁，不是提示器）")
    ap.add_argument("--src", help="源文件（--compute 用）")
    ap.add_argument("--quote", help="引文原文（--compute 用）")
    ap.add_argument("--check", help="要复核的笔记 .md")
    ap.add_argument("--source-root", default=None, help="--check 时源资料根（解析 sources 用）")
    ap.add_argument("--doc-maps", default=None, help="_meta/doc_maps.jsonl，标题从这儿读")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check-heading", action="store_true", help="--check 时连 §标题 一起比")
    args = ap.parse_args()
    if args.check:
        if not args.source_root:
            die("--check 需要 --source-root")
        sys.exit(cmd_check(args))
    if args.src and args.quote is not None:
        sys.exit(cmd_compute(args))
    die("要么 --src + --quote，要么 --check <笔记> + --source-root")


if __name__ == "__main__":
    main()
