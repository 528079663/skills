#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_verbatim_lite.py —— units 关闭时的正文数值/命令逐字轻量校验。

定位（`08_topics_pipeline_units.md` §3/§3.1 与 `04_pipeline.md` §11）：
`validate_extraction.py` 的数值/命令逐字校验**只在 units 路径上跑**（它读 `_meta/units.jsonl`，
且逐字那一项只对 `type=="claim"` 的 `text`/`metric` 生效）。units 关掉的库里，正文数字/命令
只剩模型自律——真库首批实测（发现 11）确实失手过一次（把源里的 6 段链写成「5 段式」）。
本脚本补那一格：**warn only，永不 fail**。它是提示器，不是门禁；真要判错仍走 units + validate。

两个方向，真库实测的信噪比差一个量级（P9 把这两个读数钉成断言）：
  · 「多」（**主判据**）：笔记里出现、**整篇源文件里都没有**的数字 / 命令。自创计数就是这一类；
      在定稿笔记上 0 假警。
  · 「缺」（**参考信号**）：**主块**里有、笔记里没有的数字。1:N 之后它报的是
      "这块还有东西没进本篇"＝拆篇候选，不是缺陷。
      已知噪声源（明写，别当错误清单）：markdown 有序列表标记、图片文件名编号、URL 里的数字。

主块怎么定：`source_locator` **首项**落在的那个块；块边界直接复用 `doc_map.split_chunks()`，
不另起一套切块口径。跨块的语义单元**只校主块**，报告里逐篇明写「跨块，仅校主块」。

豁免按 `08` §3.1 的**前缀白名单**判，**不是整段豁免**：inference 段里只有以
`作者未提、我的推论：` 开头的行豁免；`同块其他结论：` / `口径澄清：` / `⚠️` 三类照查。
整段豁免等于承认"把失手挪进推断段就免检"合法——真库那两次真实失手都写在推断段里。

反引号里的什么算"命令"：含空格 / `/` / `-` / `$` / `>` / 数字的 span。
**纯标识符**（`source_locator`、`coverage_audit` 这类字段名）不算命令、不查——它是元数据不是原文片段。

明确不检（输出里逐条打出来，别当全检）：中文数量词（"三段""三条"）、inference 段声明过的自创、
归纳论断本身是否有原文支撑、引文是否为源区间子串（那是 validate 的第 1 项）、纯标识符反引号 span。

用法：
    python scripts/check_verbatim_lite.py --notes-dir <KB>/工作流 --source-root <源资料根>
    python scripts/check_verbatim_lite.py --notes-dir <KB>/工作流 --source-root <源资料根> --format json
退出码：**0 = 跑完（有无 warn 都是 0）**；1 = 输入不可用
（笔记目录不存在 / 源目录不存在 / 笔记 0 篇——绝不在"什么都没查"的基础上打印通过）。
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from search_index import AGGREGATE_PAGES, DEFAULT_NOTES_DIR   # 目录口径与 build/build_topics/verify/audit 统一
from doc_map import split_chunks             # 块边界复用 doc_map，不另起一套切块口径

# 数字 token 不归一（1,000 ≠ 1000）；连接式数字（5-10 / 3-4）当一个 token，两侧同规则。
# 前后不接字母/数字：否则飞书画板的 token 串（`Mp7nwi0gohC1cJbpSPDcibC8nPb`）会被拆出
# 一堆 0/1/7/8 假警——那是 ID 不是数值。
NUM_RE = re.compile(r"(?<![0-9A-Za-z])\d[\d,\.]*(?:[-–—]\d[\d\.]*)?%?(?![0-9A-Za-z])")
CHAR_RE = re.compile(r"#char=(\d+)-(\d+)")
# 发现 39：定位符**文本本身**是元数据，不是正文数值。两种写法都要剥——
#   `§3.1.2 节点二：AI agent#char=46044-46085`（连 § 后的章节号一起剥，只剥 #char= 会漏下 3.1.2）
#   `[char=46298-46369]`（可执行清单的行内引用，旧版没剥它，8 篇笔记因此成片误报「多」）
LOCATOR_HEADING_RE = re.compile(r"§[^`\n]*?#char=\d+-\d+")
LOCATOR_BRACKET_RE = re.compile(r"\[char=\d+(?:-\d+)?\]")
# 章节号（`### 3.1.2 节点二`）是**结构编号**不是数值：源块的切片从标题行开始，
# 不剥就会在「缺」里报出 `3.1.2`（本篇剥了定位符、主块还留着标题号，两侧不对称）。
HEADING_NUM_RE = re.compile(r"(?m)^[ \t>]*#{1,6}[ \t]+\d+(?:\.\d+)*[ \t.、]*")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
CODE_RE = re.compile(r"`([^`\n]+)`")
IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]*)\)")
URL_RE = re.compile(r"https?://\S+")
ASSET_RE = re.compile(r"(?:assets|静态资源)/[^\s)`]+")
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")   # 目标名是笔记名不是内容：丢目标、有别名留别名
# markdown 有序列表标记：行首 `1.`、blockquote 里 `> 1.`、嵌套项 `  - 1.` 三种形态都剥。
# 这些是**排版编号**不是数值；不剥的话笔记里"第 1 条/1. 2. 3."会成片误报成自创数字。
LIST_MARK_RE = re.compile(r"(?m)^(?:[ \t>]*|[ \t>]*[-*+][ \t]+)\d+[\.、)]")
INFER_HEAD = "## AI 推断"
EXEMPT_PREFIX = "作者未提、我的推论："                          # 08 §3.1 里唯一被豁免的一类
CMDISH_RE = re.compile(r"[\s/$>\-]|\d")                        # 含这些才算命令；纯标识符不算
# 「缺」方向的已知噪声形态（剥掉它们，剩下的才值得人看）：
#   `1.` `2.` 这种列表标记被 NUM_RE 连着点吃了；`001` `008` 是图片文件名编号（**必须前导零**，
#   写成 `[0-5]?\d\d\d` 会把 100 这类真数字一起吞掉——P9-2b 就是这么抓到的）；URL 里的长账号数字。
MISSING_NOISE_RE = re.compile(r"^(?:\d+[\.、]|0\d\d|[0-9]{8,})$")

# 发现 36：外部导出件里的「必然失效资产」。C5 只校 sources 的文件路径、C14 只比源目录 sha256，
# 正文里的死链没有任何校验会报——这里补一条 warn（warn only，不新增 C 编号，不改 exit code）。
SIGNED_URL_RE = re.compile(r"x-oss-[A-Za-z-]+=|X-Amz-Signature|X-Amz-Credential|sig=[0-9a-f]{16,}")
MISSING_ASSET_RE = re.compile(r"缺失素材|\[[^\]]*:None\]|未随文复刻|未随文导出|请回[^，。\n]{0,8}原文查看")
NOT_CHECKED = [
    "中文数量词（三段/三条/九要素——不查，假红太多）",
    "inference 段里以「作者未提、我的推论：」开头的行（声明过的自创，按 08 §3.1 免责）",
    "归纳论断本身是否有原文支撑（那是抽检与 C9 的事，不是数值校验）",
    "引文是否为源区间子串（validate_extraction.py 的第 1 项，units 路径才有）",
    "纯标识符反引号 span（字段名/目录名不是命令，不参与逐字比对）",
    "定位符文本本身（`§章节#char=a-b`、行内 `[char=a-b]`）＝元数据，不计入「多」（发现 39）",
]


def fm_list(text, key):
    """自己解析块列表 + 内联列表——**不能用 parse_frontmatter**：那份实现按
    `line.split(':',1)` 行切，块列表的 `- ` 行不含冒号会被静默丢掉（`04` §2.3 写死了这条）。"""
    m = re.search(r"(?m)^" + re.escape(key) + r":[ \t]*(.*)$", text)
    if not m:
        return []
    inline = m.group(1).strip()
    if inline.startswith("[") and inline.endswith("]"):
        return [x.strip() for x in inline[1:-1].split(",") if x.strip()]
    out = []
    for line in text[m.end():].split("\n"):
        if re.match(r"^\s*-\s+", line):
            v = re.sub(r"^\s*-\s+", "", line)
            v = re.sub(r"\s+#[^a-zA-Z0-9\-/]*$", "", v).strip()   # 只剥行尾注释；§…#char= 的 # 要留
            if v:
                out.append(v)
        elif line.strip() and not line.startswith((" ", "\t")):
            break
    return out


def clean_note(body):
    t = WIKILINK_RE.sub(lambda m: m.group(2) or " ", body)
    t = LOCATOR_HEADING_RE.sub(" ", t)          # §章节#char=a-b 整段（含章节号）
    t = LOCATOR_BRACKET_RE.sub(" ", t)          # 行内 [char=a-b]
    t = CHAR_RE.sub(" ", t)                     # 裸 #char=a-b
    t = IMG_RE.sub(" ", t)
    t = URL_RE.sub(" ", t)
    t = ASSET_RE.sub(" ", t)
    t = LINK_RE.sub(lambda m: m.group(1), t)
    t = FENCE_RE.sub(" ", t)
    t = LIST_MARK_RE.sub(" ", t)
    t = HEADING_NUM_RE.sub(lambda m: m.group(0).split("#")[0] + "### ", t)
    return t


def clean_src(src):
    t = IMG_RE.sub(" ", src)
    t = URL_RE.sub(" ", t)
    t = ASSET_RE.sub(" ", t)
    t = FENCE_RE.sub(" ", t)
    t = LIST_MARK_RE.sub(" ", t)
    t = HEADING_NUM_RE.sub("### ", t)          # 章节号与笔记侧对称剥除（发现 39 的第二半）
    return t


def infer_scope(body):
    """inference 段里只豁免「作者未提、我的推论：」开头的行，其余三类前缀照查（08 §3.1）。"""
    if INFER_HEAD not in body:
        return body
    head, tail = body.split(INFER_HEAD, 1)
    kept = [l for l in tail.split("\n")
            if not l.strip().lstrip("- ").startswith(EXEMPT_PREFIX)]
    return head + INFER_HEAD + "\n".join(kept)


def cmds_of(text):
    return {c.strip() for c in CODE_RE.findall(text)
            if c.strip() and CMDISH_RE.search(c.strip())}


def block_of(pos, blocks):
    for i, (h, s, e) in enumerate(blocks):
        if s <= pos < e:
            return i, h, (s, e)
    return None, None, None


def dead_assets_of(text):
    """返回这篇笔记里的失效资产种类（带次数）；只报不判。"""
    out = []
    for rx, name in ((SIGNED_URL_RE, "预签名 URL 参数（有效期通常 24 小时）"),
                     (MISSING_ASSET_RE, "素材缺失/未导出占位")):
        n = len(rx.findall(text))
        if n:
            out.append("%s ×%d" % (name, n))
    return out


def main():
    ap = argparse.ArgumentParser(description="units-off 路径的正文数值/命令逐字轻量校验（warn only）")
    ap.add_argument("--notes-dir", required=True, help="笔记目录本身（默认口径名 %s）" % DEFAULT_NOTES_DIR)
    ap.add_argument("--source-root", required=True, help="源资料根目录（只读）")
    ap.add_argument("--kb", default=None,
                    help="KB 根；缺省＝笔记目录的父目录（嵌套布局如 kb/content/notes 时显式给出）")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    args = ap.parse_args()

    notes_abs = os.path.abspath(args.notes_dir)
    src_abs = os.path.abspath(args.source_root)
    if not os.path.isdir(notes_abs):
        raise SystemExit("[verbatim-lite] 笔记目录不存在：%s" % notes_abs)
    if not os.path.isdir(src_abs):
        raise SystemExit("[verbatim-lite] 源目录不存在：%s" % src_abs)

    kb_root = os.path.abspath(args.kb) if args.kb else os.path.dirname(notes_abs)
    units_path = os.path.join(kb_root, "_meta", "units.jsonl")
    units_rows = 0
    if os.path.isfile(units_path):
        with open(units_path, encoding="utf-8") as fh:
            units_rows = sum(1 for l in fh if l.strip())
    if units_rows:
        # units 开着 → validate 是权威，本脚本不掺和。这不是错误：exit 0，但明写"未做任何校验"，
        # 不给人"跑过了"的错觉。判据是**产物存在**（units.jsonl 有行），不是 config 里的开关——
        # 本脚本的 CLI 没有 --config，别把这句读成配置探测。
        print("[verbatim-lite] 本库 units 已开（%s：%d 条）——数值/命令逐字请用 "
              "validate_extraction.py，本脚本只服务 units 关闭的库。**未做任何校验。**"
              % (units_path, units_rows))
        return 0

    cache = {}

    def read_src(rel):
        for base in (src_abs, kb_root):              # 与 verify 的 C5 同两种路径基准
            p = os.path.join(base, rel.replace("/", os.sep))
            if os.path.isfile(p):
                if p not in cache:
                    with open(p, encoding="utf-8", errors="ignore") as fh:
                        txt = fh.read()
                    cache[p] = (txt, split_chunks(txt))
                return cache[p], p
        return None, None

    notes = []
    for dp, _, fn in os.walk(notes_abs):
        for f in fn:
            if f.endswith(".md") and f not in AGGREGATE_PAGES:
                notes.append(os.path.join(dp, f))
    notes.sort()
    if not notes:
        raise SystemExit("[verbatim-lite] %s 下 0 篇原子笔记——拒绝在"
                         "「什么都没查」的基础上打印通过。" % notes_abs)

    rows = []
    for p in notes:
        rel = os.path.relpath(p, kb_root).replace("\\", "/")
        text = open(p, encoding="utf-8", errors="ignore").read()
        body = text.split("---", 2)[-1] if text.startswith("---") else text
        srcs, locs = fm_list(text, "sources"), fm_list(text, "source_locator")
        if not srcs:
            rows.append({"note": rel, "skipped": "sources 为空（C5 的事，这里不重复报）",
                         "extra": [], "missing": [], "dead_assets": dead_assets_of(text)})
            continue
        got, used = read_src(srcs[0])
        if got is None:
            rows.append({"note": rel, "skipped": "源文件不可达：%s" % srcs[0],
                         "extra": [], "missing": [], "dead_assets": dead_assets_of(text)})
            continue
        src, blocks = got
        src_clean = clean_src(src)
        # 「多」的参照系 = **本篇引用落在的那几个块之并**（主块 + 其余被引块），不是贴紧的 quote 区间。
        # 两头的失败都实测过：
        #   · 用整篇当参照太松——把源里的「5-10分钟」写成「20分钟」检不到（别处确有「5到20人」的 20）；
        #   · 用贴紧的 quote 区间当参照太紧——笔记合法复述本块里的其它数字（如 3-4 单/6-7 单/60 分钟）
        #     会被成片误报成"自创"。块才是这篇声明过的出处单位。
        # 没有 `#char=` 可用时（旧笔记/漏写定位符）退回整篇，并在输出里标 degraded。
        # 引用范围取"正文里出现过的所有定位符"（含 资料原话、可执行清单的行内引用），
        # 再归到它们各自落在的**块**——贴紧的单条 quote 区间当参照会成片误报（实测过）。
        cited_ids = set()
        for m in CHAR_RE.finditer(" | ".join(locs) + " " + body):
            i2 = block_of(int(m.group(1)), blocks)[0]
            if i2 is not None:
                cited_ids.add(i2)
        cited = "".join(src[blocks[i][1]:blocks[i][2]] for i in sorted(cited_ids))
        degraded = not cited
        ref = cited if cited else src
        raw_tokens = NUM_RE.findall(ref)
        src_nums_ref = set(raw_tokens) | {t.rstrip(".、") for t in raw_tokens}
        src_codes_raw = {c.strip() for c in CODE_RE.findall(src)}

        scope = infer_scope(body)
        note_text = clean_note(scope)
        note_nums = set(NUM_RE.findall(note_text))

        extra_nums = sorted(note_nums - src_nums_ref, key=lambda x: (-len(x), x))
        extra_cmds = sorted(c for c in cmds_of(note_text)
                            if c not in src_codes_raw and c not in ref)

        # 主块 = 首个定位符落在的块；跨块 = 全篇引用落在 >1 个块（cited_ids 已在上面算好）
        first = CHAR_RE.search(locs[0]) if locs else CHAR_RE.search(body)
        bid, bhead, main_block = (None, None, None)
        if first:
            bid, bhead, main_block = block_of(int(first.group(1)), blocks)
        cross = len(cited_ids) > 1
        missing = []
        if main_block:
            bs, be = main_block
            raw = sorted(set(NUM_RE.findall(clean_src(src[bs:be]))) - note_nums,
                         key=lambda x: (-len(x), x))
            missing = [t for t in raw if not MISSING_NOISE_RE.match(t)]
        rows.append({"note": rel, "skipped": None, "source_used": used,
                     "main_block": list(main_block) if main_block else None,
                     "main_block_heading": bhead, "block_index": bid,
                     "cross_block": cross, "locator_items": len(locs),
                     "extra_reference": ("整篇文件（笔记没写 #char= 区间，退化参照）" if degraded
                                         else "本篇引用的定位符区间之并"),
                     "extra": extra_nums + ["`%s`" % c for c in extra_cmds],
                     "missing": missing, "dead_assets": dead_assets_of(text)})

    n_extra = sum(len(r["extra"]) for r in rows)
    n_missing = sum(len(r["missing"]) for r in rows)
    n_skip = sum(1 for r in rows if r["skipped"])
    n_cross = sum(1 for r in rows if r.get("cross_block"))
    n_dead = sum(len(r.get("dead_assets") or []) for r in rows)
    n_dead_notes = sum(1 for r in rows if r.get("dead_assets"))

    if args.format == "json":
        print(json.dumps({"check_version": 5, "notes_total": len(notes),
                          "units_enabled": False, "source_root": src_abs,
                          "cross_block_notes": n_cross,
                          "warn_extra": n_extra, "warn_missing": n_missing, "skipped": n_skip,
                          "warn_dead_asset_hits": n_dead, "dead_asset_notes": n_dead_notes,
                          "rows": rows, "severity": "warn", "blocking": False,
                          "not_checked": NOT_CHECKED,
                          "noise_note": "「缺」是参考信号：常见噪声=有序列表标记/图片编号/URL 数字，"
                                        "已尽量剥除；剩余多为「主块确实还有数字没进本篇」＝拆篇候选"},
                         ensure_ascii=False, indent=2))
    else:
        print("[verbatim-lite] 笔记 %d 篇｜units **关闭**路径｜跨块笔记 %d 篇（只校主块）"
              % (len(notes), n_cross))
        for r in rows:
            if r["skipped"]:
                print("  [SKIP] %s │ %s" % (r["note"], r["skipped"]))
                continue
            mark = "[WARN]" if (r["extra"] or r["missing"] or r.get("dead_assets")) else "[ ok ]"
            print("  %s %s（%s｜定位符 %d 项｜主块「%s」｜多的参照=%s）"
                  % (mark, os.path.basename(r["note"])[:-3],
                     "跨块，仅校主块" if r["cross_block"] else "单块",
                     r["locator_items"], (r["main_block_heading"] or "?")[:14],
                     "整篇(退化)" if "整篇文件" in (r.get("extra_reference") or "") else "引用区间"))
            if r["extra"]:
                print("        多（主判据·笔记有、本篇引用区间里没有）：%s" % " ".join(r["extra"]))
            if r["missing"]:
                print("        缺（参考信号·主块有、笔记没有）：%s" % " ".join(r["missing"]))
            if r.get("dead_assets"):
                print("        失效资产（warn·不可回放的证据，见 08 §3 第 10 条）：%s"
                      % "、".join(r["dead_assets"]))
        print("-" * 66)
        print("[verbatim-lite] 「多」warn %d 条（主判据）｜「缺」warn %d 条（参考信号）｜跳过 %d 篇"
              % (n_extra, n_missing, n_skip))
        print("[verbatim-lite] 「失效资产」warn %d 处 / %d 篇（签名 URL 与导出占位；只报不判）"
              % (n_dead, n_dead_notes))
        print("[verbatim-lite] 明确不检：")
        for x in NOT_CHECKED:
            print("   · %s" % x)
        print("[verbatim-lite] 本脚本 warn only、不判失败；exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
