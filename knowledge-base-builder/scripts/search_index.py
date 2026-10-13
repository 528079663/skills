#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""search_index.py — 确定性检索引擎（标签维度过滤 + FTS5 全文 + 项目配方拉取）。

子命令：
  build   扫描 <kb>/工作流 下笔记，解析多维 frontmatter，建 _meta/search.db（FTS5）
  search  关键词 + 可选维度/主题/主轴条件检索（--topics / --dim / --flow…）
  pull    按项目 recipe.yaml 一键拉取（rank 生效）
  units   按类型/主题/置信度/状态查 _meta/units.jsonl
  recall  自然语言查询：路由 JSON → 查询 gram OR → q_hooks → topics 扩展 → relation 遍历 → 合并排序
对应 references/06_retrieval.md。检索全程只读（build 仅写 _meta/search.db）。

SCHEMA_VERSION：索引 schema 版本。笔记结构或分词规则变化时必须 +1，verify.py 会
校验该版本，避免用旧索引跑新检索。

q_hooks：笔记 frontmatter 的口语问法（每篇 3–5 条），进索引并在检索时优先匹配，
见 references/06 第 8 节；路由 JSON 契约（含校验原因码与 route_warnings.jsonl）见第 9 节。
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

SCHEMA_VERSION = 4   # v4：分词改多语言分流（A1）；v3：+ q_hooks 索引列；v2：中文 2-gram 索引 + meta 表

try:  # units 类型口径与 build_units.py 同源，避免两处各写一份
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build_units import VALID_TYPES as VALID_UNIT_TYPES
except Exception:  # pragma: no cover
    # 兜底不写第二份类型清单（P12-fb）：有了字面量，路由清洗会"照常工作"却按旧口径丢 unit_type
    VALID_UNIT_TYPES = None

# topics 为内容主题（生长式、非受控），与五维属性并列参与过滤与全文索引
DIMS = ["domains", "forms", "tools", "types", "projects", "topics"]
# 主轴字段（单值，决定物理位置）
PRIMARY = ["flow", "stage", "substage"]
STOP_CHARS = set("的了是在我你他她它们和与及也就都很还被把让给而但或一个不有个这那呢吗啊呀吧")
# A1 停用词：**只在字母词段生效**，中文单字仍走 STOP_CHARS。分语言两张表；不做语言
# 识别——en 全拉丁、ru 全西里尔，两表按码位天然不相交，查一次并集即可。只收**无歧义
# 虚词**：may/will/can/now/key 这类同时是常见检索词的词不收；人称代词族（i / you / he…
# / they）也不收（"I" 在个人品牌类库里能当内容词，且查询侧有护栏①兜底）。词干先于
# 停用词，故 does / doing 这类剥不动的形态直接列进表。日/韩/泰停用词本轮未收＝已知边界。
STOP_WORDS = {
    "en": frozenset("""
        the a an and or but if than then
        that this these those it its is are was
        were be been being do does did doing have
        has had of in on at to for with
        without by from as into about over under not
        no nor only same so
    """.split()),
    "ru": frozenset("""
        и в во не что он она они
        мы вы ты с со к как а
        но да или если то при для от
        до из чтобы этот их её
    """.split()),
}
STOP_WORDS_ALL = STOP_WORDS["en"] | STOP_WORDS["ru"]
# 段级脚本分流（A1）。下列区间都是 **Unicode 码位**，不是 UTF-8 字节：
# n-gram 一律在 str 上按码点滑窗（chunk[i:i+n]），所以韩文/变音拉丁一个字符就是一格。
_HAN_KANA = ("\u4e00-\u9fff\u3400-\u4dbf"           # 汉字 + 扩展 A
             "\u3040-\u30ff\u31f0-\u31ff")           # 平/片/半角假名
_NGRAM_NO_UNI = ("\uac00-\ud7a3\u1100-\u11ff\u3130-\u318f"  # 韩文音节 + jamo + 兼容字母
                 "\u0e00-\u0e7f")                    # 泰文
NGRAM_CHARS = _HAN_KANA + _NGRAM_NO_UNI
NGRAM_CLASS = "[" + NGRAM_CHARS + "]"           # 区间只在这里写一次，下面共用
NGRAM_SEG_RE = re.compile(NGRAM_CLASS + "+")
_HAN_KANA_SEG_RE = re.compile("[" + _HAN_KANA + "]+")
_NGRAM_KEEP_SPLIT_RE = re.compile("([" + _HAN_KANA + "]+|[" + _NGRAM_NO_UNI + "]+)")
#   ↑ 带捕获组（split 后 n-gram 段还在），且**汉字/假名与韩文/泰文分属两段**：
#     两类相邻时不产「词ค」「문한」这种两边各取一字的跨脚本 gram（合成一段会产，是噪音）
# 先按 n-gram 段切开（_NGRAM_KEEP_SPLIT_RE），剩下的才当词处理：这样「AI选题」照旧拆成
# AI + 选题，而 vídeos 不会被 ASCII 类拆成 vid + éos（变音字母留在词段里）。
# 词段 = 全脚本字母 + 数字 + 下划线（沿用旧 [A-Za-z0-9_]+ 的「整段不切」，再扩到
# 非 ASCII 字母）+ 组合音标符号（NFD 拆出的变音符不切断词）。
# 变音符区间用 chr() 拼：把反斜杠+u 的形式直接写进源码，在部分编辑链路里会被
# 解码成真字符，正则就废了（本轮实测踩过）。
_WORD_TOKEN_RE = re.compile(r"[\w" + chr(0x300) + "-" + chr(0x36F) + "]+")
# 轻量词干（A1）：只剥拉丁常见后缀，剥完至少留 3 个码点，**无例外表**。
# 索引侧与查询侧共用本函数，故「同一个词」永远自配——剥错最多是两个不同形态没并上，
# 不会把原来能命中的查询弄成命不中。
STEM_RULES = (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", ""))

TYPE_PRIORITY = {"教程": 1.0, "案例": 0.9, "SOP": 0.85, "复盘": 0.8,
                 "问答": 0.7, "观点": 0.6, "素材": 0.5}
# rank 排序键（recipe.yaml 的 rank 按此顺序级联生效）
RANK_KEYS = ("相关度", "时间", "类型优先级")
# build / build_topics / verify 的统一笔记目录口径（C12 磁盘比对按它数）
DEFAULT_NOTES_DIR = "工作流"
# 聚合页**显式白名单**（乙批 B8）：豁免"这篇不是原子笔记"从此靠这张表，不靠 `_` 前缀——
# 前缀是会腐烂的暗号：`_临时.md` 这种文件从前被静默豁免，C4/C9/C11 都看不见它（负控见 P12-dir⑩）。
# `_主题地图.md` **本库不存在**（build_topics 写的是不带下划线的 `00_导航/主题地图.md`），
# 留着是为其他库形状预留；本库实际生效的是 `_流程.md`/`_总览.md`/`_提示词资产.md`/`_模板.md`。
AGGREGATE_PAGES = ("_流程.md", "_总览.md", "_主题地图.md", "_提示词资产.md", "_模板.md")
# FTS 通道弱命中门槛：查询切出 >=2 个 **查询 gram** 时，要求结果至少命中这么多个不同的 gram。
# A1 口径：汉字/假名/韩文/泰文段产 2-gram，字母词段产**整词**（词干归一后）——门槛数的是
# 「不同查询 gram」。常量名里的 bigram 是历史名，按裁决不改（改名牵动 CLI 参数/文档/探针）。
DEFAULT_MIN_BIGRAM_HITS = 2
# 被 FTS 门槛滤掉的弱命中日志（相对 kb）
FTS_FILTER_LOG = os.path.join("_meta", "logs", "fts_filtered.jsonl")

FRONT_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


# ---------- 文本/解析工具 ----------
def parse_list(v):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1]
    return [x.strip().strip('"').strip("'") for x in re.split(r"[,，]", v) if x.strip()]


def _block_list(raw_fm, key):
    """解析 YAML 块列表：``key:`` 换行后跟 ``  - 值``。"""
    out, capture = [], False
    for ln in raw_fm.split("\n"):
        if re.match(rf"^{re.escape(key)}\s*:\s*$", ln):
            capture = True
            continue
        if capture:
            m = re.match(r"^\s+-\s*(.+)$", ln)
            if m:
                out.append(m.group(1).strip().strip('"').strip("'"))
            elif ln.strip() and not ln.startswith((" ", "\t")):
                break
    return out


def _q(v):
    """剥**成对**的首尾引号再 strip：只认 `"..."` 与 `'...'`，单侧或不配对一律不动。
       YAML 写 `stage: "3_搭建与开发"` 时引号会连进值里，`endswith`/`==` 直接比就误红（乙批 B5）。
       只剥一层、不递归；半截引号**不额外造语法校验**（按裁决接受这个边界）。"""
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("\"", "'"):
        return v[1:-1].strip()
    return v


STAGE_NUM_PREFIX = re.compile(r"^\d+[ \t]*[_、.．\-][ \t]*")


def _stage_key(s):
    """stage 的**比较键**：先 `_q` 剥成对引号，再剥前导「序号＋分隔符」（`3_`/`3.`/`3-`/`3、`）。
       裁决 B6：路由与 `--stage` 里 `3_搭建与开发` 与 `搭建与开发`**等价**——库里存的是带序号写法
       （目录带序号是 render_config 的约定），两侧都归一到无序号形态再比。
       **只对 stage 用**；flow / substage 保持精确比（放宽它们没人要求，且会掩盖填错）。"""
    return STAGE_NUM_PREFIX.sub("", _q(s or "")).strip()


def parse_frontmatter(text):
    m = FRONT_RE.match(text)
    if not m:
        return None
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = _q(v)
    out = {d: parse_list(fm.get(d, "")) for d in DIMS}
    out["title"] = fm.get("title", "")
    # 主轴字段（单值）
    out["flow"] = fm.get("flow", "")
    out["stage"] = fm.get("stage", "")
    out["substage"] = fm.get("substage", "")
    out["source_kind"] = (fm.get("source_kind", "") or None)
    out["updated"] = fm.get("updated", fm.get("created", ""))
    out["stale"] = fm.get("stale", "false").lower() == "true"
    # q_hooks：口语问法，支持内联 [a, b] 与块列表两种写法
    out["q_hooks"] = (parse_list(fm.get("q_hooks", ""))
                      or _block_list(m.group(1), "q_hooks"))
    return out


def stem_light(word):
    """拉丁词段的轻量词干：按 STEM_RULES 剥第一个命中的后缀，且剥完 ≥3 个码点。

    非 ASCII 词（西里尔、希腊…）直接原样返回——后缀表是拉丁形态，剥不到它们，
    与其乱剥不如不剥（俄文词形变化仍是整词精确匹配，这是已知边界）。
    """
    if not word.isascii():
        return word
    for suf, rep in STEM_RULES:
        if word.endswith(suf) and len(word) - len(suf) + len(rep) >= 3:
            return word[: -len(suf)] + rep
    return word


def gram_units(text, sizes=(2,), drop_stopwords=False):
    """多语言切分（A1）：先按脚本切段，再按段类分流。零依赖，单函数。

    - 汉字/假名段：n-gram（索引 sizes=(1,2)、查询 sizes=(2,)），单字仍过滤 STOP_CHARS
    - 韩文/泰文段：只做 n≥2 的 gram——谚文字母、泰文辅音单独成 gram 没有检索价值
    - 字母词段（含 ASCII/数字/snake_case）：整段 token + 小写 + 轻量词干；
      停用词只在这段生效（数字段虽走同一分支，但词干表全是字母后缀、停用词表全是
      字母词，所以数字天然保持整段原样）
    - n-gram 按码点滑窗（步长 1），不按字节；采用滑动窗口而非不重叠切分：
      不重叠会让「关键词选品检索」里的「选品」落在错位边界上而无法被索引

    drop_stopwords：
      False（默认，索引侧）→ 停用词照旧进索引，纯停用词查询也能命中；
      True（查询侧 / matched_hooks 的 gram 分母）→ 删掉字母词段里的停用词，
      并守两条护栏：
        ① 整段查询全是停用词时不删（否则查询退化成空 MATCH，静默 0 结果）；
        ② 分母用删过停用词的 gram 集（红线：停用词不占 hook 重合度分母）。
    """
    out, dropped = [], []
    for piece in _NGRAM_KEEP_SPLIT_RE.split(text or ""):
        if not piece:
            continue
        if NGRAM_SEG_RE.fullmatch(piece):
            # 单字档只对汉字/假名开（兼容 1 字查询）；韩文/泰文段跳过 n==1
            ns = sizes if _HAN_KANA_SEG_RE.fullmatch(piece) else tuple(
                n for n in sizes if n >= 2)
            for n in ns:
                if n == 1:
                    out.extend(c for c in piece if c not in STOP_CHARS)
                else:
                    out.extend(piece[i:i + n] for i in range(len(piece) - n + 1))
            continue
        # 这段已被 n-gram 段切断，里面不会再有汉字/假名/谚文/泰文
        for chunk in _WORD_TOKEN_RE.findall(piece):
            w = stem_light(chunk.lower())
            if drop_stopwords and w in STOP_WORDS_ALL:
                dropped.append(w)
                continue
            out.append(w)
    if drop_stopwords and not out and dropped:   # 护栏①
        out.extend(dropped)
    return out


def to_index_text(text):
    """索引文本：汉字/假名段出单字 + 2-gram（保留单字以兼容 1 字查询），韩文/泰文段只出
    2-gram，字母词段出整词；**停用词不删**（A1，口径见 gram_units）。"""
    return " ".join(gram_units(text, sizes=(1, 2), drop_stopwords=False))


def load_yaml(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        text = fh.read()
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        return _simple_recipe_parse(text)


def _simple_recipe_parse(text):
    """无 pyyaml 时的兜底：解析本 Skill 生成的固定 recipe 结构。"""
    recipe = {"filters": {}, "exclude": [], "rank": [], "keywords": "", "limit": 50}
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r"^[a-z_]+:\s*$", line):
            section = line[:-1]
            continue
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if section == "filters" and val:
                recipe["filters"][key] = parse_list(val)
            elif key in ("exclude", "rank") and val:
                recipe[key] = parse_list(val)
            elif key in ("keywords", "project"):
                recipe[key] = val.strip('"')
            elif key == "limit":
                recipe["limit"] = int(val)
            section = key if key in ("filters",) else section
    return recipe


# ---------- build ----------
def cmd_build(kb, notes_dir, rebuild):
    notes_abs = os.path.join(kb, notes_dir)
    db_path = os.path.join(kb, "_meta", "search.db")
    if not os.path.isdir(notes_abs):
        raise SystemExit(f"[build] 笔记目录不存在：{notes_abs}"
                         f"（默认 --notes {notes_dir}；旧库请显式 --notes notes）")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if rebuild and os.path.exists(db_path):
        os.remove(db_path)

    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS docs ("
                "path TEXT PRIMARY KEY, title TEXT, flow TEXT, stage TEXT, substage TEXT, "
                "domains TEXT, forms TEXT, "
                "tools TEXT, types TEXT, projects TEXT, topics TEXT, "
                "source_kind TEXT, updated TEXT, stale INTEGER, summary TEXT, "
                "q_hooks TEXT)")
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5("
                "path UNINDEXED, title, body, dimtext, qhooks)")

    n = 0
    for dirpath, _, files in os.walk(notes_abs):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            # 跳过 _流程.md / _总览.md（索引它们是总览页，不是原子笔记）
            if fn in AGGREGATE_PAGES:      # B8：索引只跳白名单聚合页
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, kb).replace("\\", "/")
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            fm = parse_frontmatter(text)
            if fm is None:
                continue
            body_plain = FRONT_RE.sub("", text, count=1)
            summary = next((l.strip("> ").strip() for l in body_plain.splitlines()
                            if l.strip().startswith(">") and len(l.strip()) > 8), "")
            dimtext = " ".join(" ".join(fm[d]) for d in DIMS)
            con.execute("INSERT OR REPLACE INTO docs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (rel, fm["title"], fm["flow"], fm["stage"], fm["substage"],
                         *[json.dumps(fm[d], ensure_ascii=False)
                           for d in DIMS],
                         fm["source_kind"], fm["updated"], int(fm["stale"]), summary,
                         json.dumps(fm["q_hooks"], ensure_ascii=False)))
            con.execute("DELETE FROM fts WHERE path=?", (rel,))
            con.execute("INSERT INTO fts VALUES (?,?,?,?,?)",
                        (rel, to_index_text(fm["title"]), to_index_text(body_plain),
                         to_index_text(dimtext),
                         to_index_text(" ".join(fm["q_hooks"]))))
            n += 1
    con.execute("INSERT OR REPLACE INTO meta VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('notes_indexed', ?)", (str(n),))
    con.commit()
    con.close()
    if n == 0:
        raise SystemExit(f"[build] {notes_abs} 下没有可索引笔记（0 篇）——"
                         f"拒绝产出空索引，请检查笔记目录与 frontmatter。")
    print(f"[build] 索引笔记 {n} 篇（schema v{SCHEMA_VERSION}） → {db_path}")


# ---------- q_hooks 匹配 ----------
# 重合度的分母有两个选择，各自会打死一条路径（真库首批 8 篇 / 32 条 hook 实测）：
#   分母=query → 长自然问句切出 16–34 个 2-gram，任何一条 hook 都摊不到 50%，长问句恒 0 命中；
#   分母=hook  → 路由切出的短 keywords（"免费诊断 收钱"＝4 个 gram 对 hook 的 8–16 个）掉到 0.5
#                以下，把原本能命中的短语路径打回 0（实测 3 条短语查询全灭）。
# 所以两条判据**并列**（任一达标即命中），不是替换关系；另加 shared>=2 的地板，
# 防"只共用一个常见 bigram（如「内容」）就误命中"。
# 0.35 不是拍的：阈值扫描里 0.5 长问句全灭、0.30 起出现跨笔记误报，0.35 是"长问句开始命中
# 且 4 条无关查询仍 0 命中"的那一档。**改这两个数必须连 P9 的断言一起改。**
HOOK_GRAM_RATIO = 0.35
HOOK_GRAM_FLOOR = 2


def matched_hooks(d, qtext, qgrams):
    """返回该笔记命中的口语问法（references/06 第 8 节「命中判定」）。

    满足其一即算命中：
      ① query 与 hook 互相包含；
      ② 查询 gram 重合度 ≥ 0.5，分母 = query；
      ③ 查询 gram 重合度 ≥ HOOK_GRAM_RATIO，分母 = hook，且共同 gram 数 ≥ HOOK_GRAM_FLOOR。
         （查询 gram：汉字/假名/韩文/泰文为 2-gram，字母词为整词；见 gram_units）

    红线（A1②）：两侧 gram 都用 drop_stopwords=True —— 停用词不占分母，否则
    「how do I …」这类问法会被虚词把重合度分母撑大、把真实 hook 判成不命中。
    调用方传进来的 qgrams 同样出自 drop_stopwords=True（见 fts_hits / cmd_recall）。
    """
    out = []
    if not qtext or not qgrams:
        return out
    for h in d.get("q_hooks") or []:
        hg = set(gram_units(h, drop_stopwords=True))
        if not hg:
            continue
        shared = len(hg & qgrams)
        if (h in qtext or qtext in h
                or shared / len(qgrams) >= 0.5
                or (shared >= HOOK_GRAM_FLOOR and shared / len(hg) >= HOOK_GRAM_RATIO)):
            out.append(h)
    return out


# ---------- 检索核心 ----------
def load_docs(con):
    cols = ["path", "title", "flow", "stage", "substage",
            "domains", "forms", "tools", "types", "projects",
            "topics", "source_kind", "updated", "stale", "summary", "q_hooks"]
    docs = []
    for row in con.execute(f"SELECT {','.join(cols)} FROM docs"):
        d = dict(zip(cols, row))
        for dim in DIMS:
            d[dim] = json.loads(d[dim])
        d["q_hooks"] = json.loads(d["q_hooks"] or "[]")
        docs.append(d)
    return docs


def passes_filters(d, filters, exclude, primary=None, include_stale=False):
    if d["stale"] and not include_stale:
        return False
    all_tags = set(sum((d[dim] for dim in DIMS), []))
    if all_tags & set(exclude):
        return False
    # 主轴过滤：flow / substage 精确比；stage 走 `_stage_key`（带/不带序号等价，B6）
    if primary:
        for k, v in primary.items():
            if k == "stage":
                if _stage_key(d.get(k) or "") != _stage_key(v or ""):
                    return False
            elif d.get(k) != v:
                return False
    for dim, vals in filters.items():
        if not (set(d[dim]) & set(vals)):  # 同维 OR
            return False
    return True  # 跨维 AND


def _gram_token_set(*texts):
    """把索引文本（已是「单字 + 2-gram + 字母整词」空格串）拆成 token 集合，用于精确计数命中 gram。"""
    toks = set()
    for t in texts:
        if t:
            toks.update(t.split())
    return toks


def fts_hits(con, kw, min_bigram_hits=DEFAULT_MIN_BIGRAM_HITS):
    """FTS 通道检索（查询 gram OR）+ 弱命中门槛。

    查询 gram 的口径见 gram_units：汉字/假名/韩文/泰文段是 2-gram，字母词段是整词
    （词干归一、停用词已删）。查询切出 >=2 个查询 gram 时，要求结果至少命中
    min_bigram_hits 个**不同** gram；只切出 1 个时门槛不启用（否则 1 字/单词查询会被误杀）。
    返回 (kept, filtered, qgrams, floor_on)：
      kept     [(path, bm25)]
      filtered [{"doc_id","grams_hit","hits","bm25","channel"}] —— 只记录，不进 FTS 结果
    """
    qgrams = list(dict.fromkeys(gram_units(kw, drop_stopwords=True)))
    if not qgrams:
        return [], [], [], False
    q = " OR ".join('"%s"' % t for t in qgrams)
    rows = con.execute(
        "SELECT path, bm25(fts, 0.0, 1.0, 1.0, 0.6, 3.0), title, body, dimtext, qhooks "
        "FROM fts WHERE fts MATCH ?", (q,)).fetchall()
    floor_on = len(qgrams) >= 2 and (min_bigram_hits or 0) > 1
    kept, filtered = [], []
    for path, bm, ti, bo, di, qh in rows:
        toks = _gram_token_set(ti, bo, di, qh)
        hit = [g for g in qgrams if g in toks]
        if floor_on and len(hit) < min_bigram_hits:
            filtered.append({"doc_id": path, "grams_hit": hit, "hits": len(hit),
                             "bm25": round(bm, 4), "channel": "fts"})
            continue
        kept.append((path, bm))
    return kept, filtered, qgrams, floor_on


def log_fts_filtered(kb, query, filtered, grams_total, min_bigram_hits):
    """被 FTS 门槛滤掉的弱命中追加写入 _meta/logs/fts_filtered.jsonl（doc_id/命中gram/分数/通道）。"""
    if not filtered:
        return None
    path = os.path.join(kb, FTS_FILTER_LOG)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(path, "a", encoding="utf-8") as fh:
        for f in filtered:
            fh.write(json.dumps({"ts": ts, "query": query, "grams_total": grams_total,
                                 "min_required": min_bigram_hits, **f},
                                ensure_ascii=False) + "\n")
    return path


def run_query(kb, filters, keywords, exclude, rank, limit, primary=None,
              include_stale=False, min_bigram_hits=DEFAULT_MIN_BIGRAM_HITS, stats=None):
    t0 = time.perf_counter()
    con = sqlite3.connect(os.path.join(kb, "_meta", "search.db"))
    docs = load_docs(con)
    candidates = [d for d in docs
                  if passes_filters(d, filters, exclude, primary, include_stale)]

    def tag_score(d):
        if not filters:
            return 0.0
        s = sum(len(set(d[dim]) & set(vals)) / len(vals)
                for dim, vals in filters.items())
        return s / len(filters)

    def type_pri(d):
        return max((TYPE_PRIORITY.get(t, 0) for t in d["types"]), default=0.0)

    hook_paths = set()
    if keywords:
        # 查询 gram OR（汉字类 2-gram、字母词整词；不再单字 OR）+ 弱命中门槛（列权重 path/title/body/dimtext/qhooks，
        # qhooks 给 3 倍，命中口语问法者自然靠前）
        kept, filtered, qgram_list, floor_on = fts_hits(con, keywords, min_bigram_hits)
        log_fts_filtered(kb, keywords, filtered, len(qgram_list), min_bigram_hits)
        qgrams = set(qgram_list)
        bm = dict(kept)
        scored = [(d, bm[d["path"]]) for d in candidates if d["path"] in bm]
        if stats is not None:
            stats.update({"query": keywords, "qgrams": len(qgram_list),
                          "fts_raw": len(kept) + len(filtered), "fts_kept": len(kept),
                          "fts_filtered": len(filtered), "floor_on": floor_on,
                          "min_bigram_hits": min_bigram_hits, "filtered": filtered})
        for d in candidates:                       # 标注命中的口语问法
            mh = matched_hooks(d, keywords, qgrams)
            if mh:
                d["_hooks"] = mh
                hook_paths.add(d["path"])
    else:
        scored = [(d, 0.0) for d in candidates]
        if stats is not None:
            stats.update({"query": "", "qgrams": 0, "fts_raw": 0, "fts_kept": 0,
                          "fts_filtered": 0, "floor_on": False, "filtered": []})

    rank = [k for k in (rank or []) if k in RANK_KEYS]
    if rank:
        # 显式 rank：按配置顺序级联（列表越靠前优先级越高，稳定排序倒序施加）
        for key in reversed(rank):
            if key == "相关度":
                if keywords:
                    scored.sort(key=lambda x: x[1])                 # bm25 越小越相关
            elif key == "时间":
                scored.sort(key=lambda x: x[0]["updated"] or "", reverse=True)
            elif key == "类型优先级":
                scored.sort(key=lambda x: type_pri(x[0]), reverse=True)
    elif keywords:
        # 未显式指定 rank：保持既有默认（bm25 主、标签匹配次、时间末）
        scored.sort(key=lambda x: x[0]["updated"] or "", reverse=True)
        scored.sort(key=lambda x: tag_score(x[0]), reverse=True)
        scored.sort(key=lambda x: x[1])
    else:
        # 未显式指定 rank 且无关键词：保持既有默认（标签匹配度主）
        scored.sort(key=lambda x: x[0]["updated"] or "", reverse=True)
        scored.sort(key=lambda x: type_pri(x[0]), reverse=True)
        scored.sort(key=lambda x: tag_score(x[0]), reverse=True)
    if hook_paths:  # q_hooks 命中优先：最外层排序键，压过相关度/时间/类型
        scored.sort(key=lambda x: 0 if x[0]["path"] in hook_paths else 1)
    con.close()
    elapsed = (time.perf_counter() - t0) * 1000
    return scored[:limit], elapsed


def count_stale(kb):
    """库内 stale 笔记数，用于「被过滤了多少」的非静默提示。"""
    db = os.path.join(kb, "_meta", "search.db")
    if not os.path.isfile(db):
        return 0
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT count(*) FROM docs WHERE stale=1").fetchone()[0]
    finally:
        con.close()


def print_results(scored, elapsed):
    for rank_i, (d, score) in enumerate(scored, 1):
        flag = "  [stale]" if d["stale"] else ""
        hook = "  [hook]" if d.get("_hooks") else ""
        print(f"{rank_i:>2}. {d['title']}{hook}{flag}  [{score:.3f}]")
        print(f"     {d['path']}")
        if d.get("flow"):
            print(f"     主轴: {d['flow']} / {d.get('stage','')} / {d.get('substage','')}")
        if d.get("_hooks"):
            print(f"     命中问法: {'; '.join(d['_hooks'])}")
        if d["summary"]:
            print(f"     摘要: {d['summary'][:80]}")
        print(f"     维度: 领域{d['domains']} 形态{d['forms']} 工具{d['tools']} "
              f"类型{d['types']} 项目{d['projects']} 主题{d['topics']}")
    print(f"\n命中 {len(scored)} 条，耗时 {elapsed:.1f} ms")


def cmd_search(kb, query, dim_args, topics, flow, stage, substage, k,
               rank=None, include_stale=False, min_bigram_hits=DEFAULT_MIN_BIGRAM_HITS):
    filters = {}
    for item in dim_args or []:
        dim, vals = item.split("=", 1)
        filters[dim] = parse_list(vals)
    if topics:
        filters["topics"] = filters.get("topics", []) + parse_list(topics)
    primary = {}
    if flow:
        primary["flow"] = flow
    if stage:
        primary["stage"] = stage
    if substage:
        primary["substage"] = substage
    stats = {}
    scored, elapsed = run_query(kb, filters, query, [], rank, k, primary, include_stale,
                                min_bigram_hits, stats)
    if stats.get("floor_on") or stats.get("fts_filtered"):
        print(f"[search] FTS 命中 {stats['fts_raw']} 条 → 保留 {stats['fts_kept']} 条"
              f"（弱命中过滤 {stats['fts_filtered']} 条；查询切出 {stats['qgrams']} 个查询 gram，"
              f"门槛 ≥{stats['min_bigram_hits']}）；其他通道补回 0 条（search 只有 FTS 通道）")
        if stats.get("fts_filtered"):
            print(f"[search] 弱命中日志：{os.path.join(kb, FTS_FILTER_LOG)}")
    if not include_stale:
        n_stale = count_stale(kb)
        if n_stale:
            print(f"[search] 已按 stale 过滤 {n_stale} 篇（加 --include-stale 可召回）\n")
    print_results(scored, elapsed)


def cmd_pull(kb, recipe_path, k, include_stale=False):
    r = load_yaml(recipe_path)
    filters = r.get("filters") or {}
    exclude = r.get("exclude") or []
    rank = r.get("rank") or ["相关度", "时间"]
    limit = k or r.get("limit", 50)
    keywords = r.get("keywords") or ""
    units_type = r.get("units_type") or []
    units_conf = r.get("units_confidence") or []
    units_status = r.get("units_status") or []
    print(f"[pull] 项目：{r.get('project')}  条件："
          f"{ {dim: vals for dim, vals in filters.items()} }")
    if units_type or units_conf or units_status:
        print(f"[pull] 注意：recipe 声明了 units 过滤（type={units_type} "
              f"conf={units_conf} status={units_status}），但 pull 只拉笔记；"
              f"如需 units，请单独跑 `search_index.py units --type ... --confidence ... --status ...`")
    scored, elapsed = run_query(kb, filters, keywords, exclude, rank, limit,
                                primary=None, include_stale=include_stale)
    if not include_stale:
        n_stale = count_stale(kb)
        if n_stale:
            print(f"[pull] 已按 stale 过滤 {n_stale} 篇（加 --include-stale 可召回）\n")
    print_results(scored, elapsed)


def cmd_units(kb, type_, topic, conf, status, k):
    """层3 units 检索：按类型/主题/置信度/状态过滤 units.jsonl。"""
    path = os.path.join(kb, "_meta", "units.jsonl")
    if not os.path.isfile(path):
        print("[units] 无 _meta/units.jsonl（未启用或尚未抽取）。")
        return
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    out = []
    for u in rows:
        if type_ and u.get("type") != type_:
            continue
        if topic and topic not in u.get("topic_ids", []):
            continue
        if conf and u.get("confidence") != conf:
            continue
        if status and u.get("status") != status:
            continue
        out.append(u)
    out = out[:k]
    for u in out:
        text = (u.get("text") or u.get("question") or u.get("name")
                or u.get("goal") or "")
        print(f"- ({u.get('type')}/{u.get('confidence')}) {text}")
        ev = u.get("evidence") or {}
        if ev.get("quote"):
            print(f"    引文: {ev['quote'][:60]}  [{ev.get('locator','')}]")
    print(f"\n命中 {len(out)} / {len(rows)} 个知识单元")


# ---------- 查询路由（P1-2：大模型出 JSON，脚本只负责校验与执行） ----------
ROUTE_KEYS = ("keywords", "topics", "flow", "stage", "unit_type",
              "include_stale", "need_relations", "top_k")
ROUTE_DEFAULTS = {"keywords": [], "topics": [], "flow": None, "stage": None,
                  "unit_type": None, "include_stale": False,
                  "need_relations": True, "top_k": 10}
# 合并排序的通道权重：口语问法命中 > 全文 > 主题扩展 > 关系扩展
SRC_WEIGHT = {"hook": 4, "fts": 3, "topic": 2, "relation": 1}
# 路由软错日志：与 fts_filtered.jsonl 同一个目录、同一套追加语义
ROUTE_WARN_LOG = os.path.join("_meta", "logs", "route_warnings.jsonl")
# 校验原因码（snake_case，与 check_hooks.py 的 not_array/too_few 一套命名对齐）；
# 每个码的含义与触发条件见 references/06_retrieval.md 第 9.3 节。改名要连着文档改。
RC_JSON_PARSE_ERROR = "json_parse_error"        # 硬错：JSON 解析失败 / 路由文件不存在
RC_TYPE_ERROR = "type_error"                    # 硬错：顶层非对象、字段类型错、top_k 越界
RC_ROUTE_EMPTY = "route_empty"                  # 硬错：keywords/topics/--query 三者全空
RC_UNKNOWN_FIELD = "unknown_field"              # 软错：未知字段，忽略该字段
RC_TOPIC_NOT_FOUND = "topic_not_found"          # 软错：topics.json 里没有该主题 → 丢弃
RC_TOPICS_UNVERIFIABLE = "topics_unverifiable"  # 软错：topics.json 缺失，无法校验 → 全部丢弃
RC_FLOW_NOT_FOUND = "flow_not_found"            # 软错：库内无此 flow → 丢弃
RC_STAGE_FLOW_MISMATCH = "stage_flow_mismatch"  # 软错：stage 存在但不属于该 flow → 丢 stage
RC_UNIT_TYPE_INVALID = "unit_type_invalid"      # 软错：unit_type 不在受控类型里 → 丢弃
RC_STAGE_NOT_FOUND = "stage_not_found"          # 软错：库内无此 stage → 丢弃


def _route_fail(code, msg):
    """路由硬错：打到 stderr 并以退出码 2 结束（与 argparse 用法错误一致）。

    **硬错不写 route_warnings.jsonl**——没执行检索就没有"降级结果"可追溯；
    落盘只发生在软错确认之后（见 cmd_recall）。
    """
    print(f"[recall] ({code}) {msg}", file=sys.stderr)
    raise SystemExit(2)


def _warn(warnings, code, detail):
    """路由软错：丢值继续执行，同时记一条结构化 warning（severity 恒为 warn）。"""
    warnings.append({"code": code, "detail": detail, "severity": "warn"})


def log_route_warnings(kb, query, warnings):
    """软错追加写入 _meta/logs/route_warnings.jsonl；无 warning 时不建文件、不写空行。

    ts 用带时区的 ISO（同 build_topics.py 的 generated_at），不用 fts_filtered 的本地时间——
    跨机器/跨时区 diff 需要可比的时间戳。fts_filtered 的格式是待统一项，另轮处理。
    """
    if not warnings:
        return None
    path = os.path.join(kb, ROUTE_WARN_LOG)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        for w in warnings:
            fh.write(json.dumps({"ts": ts, "query": query, "code": w["code"],
                                 "detail": w["detail"], "severity": w["severity"]},
                                ensure_ascii=False, sort_keys=True) + "\n")
    return path


def load_route(route_arg, route_json_arg):
    """读取路由 JSON：--route <file|-> 或 --route-json '<json>'。返回 (dict|None, 来源)。"""
    if route_json_arg:
        try:
            return json.loads(route_json_arg), "--route-json 内联"
        except json.JSONDecodeError as e:
            _route_fail(RC_JSON_PARSE_ERROR, f"--route-json 不是合法 JSON：{e}")
    if route_arg:
        if route_arg == "-":
            text, src = sys.stdin.read(), "stdin"
        else:
            if not os.path.isfile(route_arg):
                _route_fail(RC_JSON_PARSE_ERROR, f"路由文件不存在：{route_arg}")
            with open(route_arg, "r", encoding="utf-8-sig") as fh:
                text = fh.read()
            src = route_arg
        try:
            return json.loads(text), src
        except json.JSONDecodeError as e:
            _route_fail(RC_JSON_PARSE_ERROR, f"路由 JSON 解析失败（{src}）：{e}")
    return None, "无（退化路由：仅用原查询切查询 gram——汉字/假名/韩文/泰文取 2-gram，字母词取整词）"


def _known_topics(kb):
    """读 _meta/topics.json 的 topic 全集；无该文件返回 None。"""
    p = os.path.join(kb, "_meta", "topics.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8-sig") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None
    # build_topics.py 写出的主题项键名是 "name"；兼容 "topic" 以容忍手改
    return {(t.get("name") or t.get("topic"))
            for t in (d.get("topics") or [])
            if (t.get("name") or t.get("topic"))}


def validate_route(raw, kb, warnings):
    """校验并净化路由 JSON。

    硬错（`_route_fail`：stderr + exit 2，**不落 warning 日志**）：顶层非对象、字段类型不对、
    top_k 越界 → `type_error`；JSON 解析失败 / 路由文件不存在 → `json_parse_error`。
    软错（`_warn`：丢值继续执行 + 结构化 warning）：`unknown_field` / `topic_not_found` /
    `topics_unverifiable` / `flow_not_found` / `stage_not_found` / `stage_flow_mismatch` /
    `unit_type_invalid`。校验口径与原因码含义见 `references/06_retrieval.md` 第 9.3 节。
    """
    if not isinstance(raw, dict):
        _route_fail(RC_TYPE_ERROR, "路由 JSON 顶层必须是对象 {…}")
    for k in raw:
        if k not in ROUTE_KEYS:
            _warn(warnings, RC_UNKNOWN_FIELD,
                  f"忽略未知字段 {k!r}（路由只认 {'/'.join(ROUTE_KEYS)}）")
    r = dict(ROUTE_DEFAULTS)
    for key in ("keywords", "topics"):
        v = raw.get(key, r[key])
        if v is None:
            v = []
        if not isinstance(v, list) or any(not isinstance(x, str) for x in v):
            _route_fail(RC_TYPE_ERROR, f"路由字段 {key!r} 必须是字符串数组，收到 {v!r}")
        r[key] = [x.strip() for x in v if x.strip()]
    for key in ("flow", "stage", "unit_type"):
        v = raw.get(key, r[key])
        if v is not None and not isinstance(v, str):
            _route_fail(RC_TYPE_ERROR, f"路由字段 {key!r} 必须是字符串或 null，收到 {v!r}")
        r[key] = v.strip() if isinstance(v, str) and v.strip() else None
    for key in ("include_stale", "need_relations"):
        v = raw.get(key, r[key])
        if not isinstance(v, bool):
            _route_fail(RC_TYPE_ERROR, f"路由字段 {key!r} 必须是 true/false，收到 {v!r}")
        r[key] = v
    v = raw.get("top_k", r["top_k"])
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 100:
        _route_fail(RC_TYPE_ERROR, f"路由字段 'top_k' 必须是 1–100 的整数，收到 {v!r}")
    r["top_k"] = v
    # —— 存在性校验：不存在的值一律丢弃，脚本不补造 ——
    known = _known_topics(kb)
    if r["topics"]:
        if known is None:
            _warn(warnings, RC_TOPICS_UNVERIFIABLE,
                  "无 _meta/topics.json，无法校验 topics，已全部丢弃（不编造）")
            r["topics"] = []
        else:
            drop = [t for t in r["topics"] if t not in known]
            if drop:
                _warn(warnings, RC_TOPIC_NOT_FOUND,
                      f"丢弃不存在的 topic {drop}（topics.json 无此项，不编造）")
            r["topics"] = [t for t in r["topics"] if t in known]
    if r["flow"] or r["stage"]:
        con = sqlite3.connect(os.path.join(kb, "_meta", "search.db"))
        try:
            flows = {x[0] for x in con.execute("SELECT DISTINCT flow FROM docs") if x[0]}
            stages = {x[0] for x in con.execute("SELECT DISTINCT stage FROM docs") if x[0]}
            # (flow, stage) 组合集合——只各自查存在性会漏掉"stage 存在但不属于这个 flow"，
            # 那种拼法两个值都能通过校验、结果却恒为 0 条，且不落任何 warning。
            pairs = {(x[0], x[1]) for x in con.execute(
                "SELECT DISTINCT flow, stage FROM docs") if x[0] and x[1]}
        finally:
            con.close()
        # 归一化视图：存在性与组合都按 `_stage_key` 比；**文案一律打原值**（B6）。
        stage_keys = {_stage_key(s) for s in stages}
        pair_keys = {}
        for f, s in pairs:
            pair_keys.setdefault(f, set()).add(_stage_key(s))
        if r["flow"] and r["flow"] not in flows:
            _warn(warnings, RC_FLOW_NOT_FOUND,
                  f"丢弃不存在的 flow {r['flow']!r}（库内 flow: {sorted(flows)}）")
            r["flow"] = None
        if r["stage"] and _stage_key(r["stage"]) not in stage_keys:
            _warn(warnings, RC_STAGE_NOT_FOUND,
                  f"丢弃不存在的 stage {r['stage']!r}（带/不带序号等价，"
                  f"如 3_x 与 x 同一环节；库内 stage: {sorted(stages)}）")
            r["stage"] = None
        # 两者都在库里，但组合不存在 → 丢 stage、**保留 flow**（宁可少过滤，不要静默 0 命中）
        if r["flow"] and r["stage"] and _stage_key(r["stage"]) not in pair_keys.get(r["flow"], set()):
            _warn(warnings, RC_STAGE_FLOW_MISMATCH,
                  f"flow {r['flow']!r} 下无 stage {r['stage']!r}，已丢弃 stage、保留 flow"
                  f"（该 flow 下的 stage: "
                  f"{sorted(s for f, s in pairs if f == r['flow'])}）")
            r["stage"] = None
    if r["unit_type"] and r["unit_type"] not in VALID_UNIT_TYPES:
        _warn(warnings, RC_UNIT_TYPE_INVALID,
              f"丢弃非法 unit_type {r['unit_type']!r}（合法值: {sorted(VALID_UNIT_TYPES)}）")
        r["unit_type"] = None
    return r


# ---------- relation 图遍历（P1-3） ----------
def load_units(kb):
    """读 _meta/units.jsonl（不存在或未启用时返回空列表）。"""
    p = os.path.join(kb, "_meta", "units.jsonl")
    if not os.path.isfile(p):
        return []
    out = []
    with open(p, "r", encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _endpoint_match(node, seeds):
    return node in seeds or any((s in node or node in s) for s in seeds if s)


def traverse_relations(units, seeds, hops=1):
    """从 seeds 出发做 hops 跳 relation 图遍历。

    返回 (命中的 relation 单元, 由边触达的邻居节点集)。邻居集只含**通过边发现**的
    节点，不含初始种子——否则种子里的原始关键词会被误当成「关联概念」。
    """
    rels = [u for u in units if u.get("type") == "relation"
            and u.get("subject") and u.get("object")]
    edges, frontier, seen, reached = [], set(seeds), set(seeds), set()
    for _ in range(max(0, hops)):
        nxt = set()
        for u in rels:
            if (_endpoint_match(u["subject"], frontier)
                    or _endpoint_match(u["object"], frontier)):
                if u not in edges:
                    edges.append(u)
                for n in (u["subject"], u["object"]):
                    if n not in seen:
                        seen.add(n)
                        reached.add(n)
                        nxt.add(n)
        frontier = nxt
        if not frontier:
            break
    return edges, reached


def _unit_doc_path(doc_id, by_path):
    """units 的 doc_id → 笔记路径（按路径 / 文件名 / 标题三种匹配）。"""
    if not doc_id:
        return None
    if doc_id in by_path:
        return doc_id
    for p in by_path:
        base = os.path.basename(p)
        if base == doc_id or base.rsplit(".", 1)[0] == doc_id:
            return p
    for p, d in by_path.items():
        if d.get("title") == doc_id:
            return p
    return None


# ---------- recall：四通道合并检索（P1-3） ----------
def cmd_recall(kb, query, route_arg, route_json_arg, k, hops, as_json,
               min_bigram_hits=DEFAULT_MIN_BIGRAM_HITS):
    t0 = time.perf_counter()
    warnings = []
    raw, src = load_route(route_arg, route_json_arg)
    if raw is None:
        route = dict(ROUTE_DEFAULTS)
        route["keywords"] = [query] if query else []
    else:
        route = validate_route(raw, kb, warnings)
    if k:
        route["top_k"] = k
    if not (query or route["keywords"] or route["topics"]):
        _route_fail(RC_ROUTE_EMPTY, "至少给 --query，或路由 JSON 里的 keywords / topics")
    # 落盘点：软错已确认、检索尚未执行。放在这条硬错之后，保证任何 exit 2 路径都不留日志行。
    log_route_warnings(kb, query, warnings)

    con = sqlite3.connect(os.path.join(kb, "_meta", "search.db"))
    docs = load_docs(con)
    by_path = {d["path"]: d for d in docs}
    hits = {}

    def entry(path):
        return hits.setdefault(path, {"src": set(), "bm25": None,
                                      "hooks": [], "topics": []})

    kw = " ".join(route["keywords"]) or query
    qgrams = set(gram_units(kw, drop_stopwords=True))   # 查询侧删停用词（红线②：不进分母）

    # 通道1 全文：查询 gram OR（+ 弱命中门槛）。被门槛滤掉的弱命中若被其他通道补回，
    # 仍会进结果——门槛只作用于 FTS 通道本身。
    fts_filtered, floor_on, fts_raw, fts_kept = [], False, 0, 0
    if qgrams:
        kept, fts_filtered, qgram_list, floor_on = fts_hits(con, kw, min_bigram_hits)
        log_fts_filtered(kb, kw, fts_filtered, len(qgram_list), min_bigram_hits)
        fts_kept, fts_raw = len(kept), len(kept) + len(fts_filtered)
        for path, bm in kept:
            e = entry(path)
            e["src"].add("fts")
            e["bm25"] = bm
    # 通道2 q_hooks：口语问法
    for d in docs:
        mh = matched_hooks(d, kw, qgrams)
        if mh:
            e = entry(d["path"])
            e["src"].add("hook")
            e["hooks"] = mh
    # 通道3 topics 扩展：种子只取「路由 topics ∪ 核心笔记的 topics」，
    # 核心 = q_hooks 命中 + FTS 前 2 名。若拿全部 FTS 命中的 topics 做种子，
    # 尾部弱命中（如只靠「视频」命中的剪辑类笔记）会把扩展带偏。
    seed_topics = set(route["topics"])
    core = [p for p, e in hits.items() if "hook" in e["src"]]
    fts_ranked = sorted((e["bm25"], p) for p, e in hits.items() if e["bm25"] is not None)
    core += [p for _, p in fts_ranked[:2]]
    for p in dict.fromkeys(core):
        if p in by_path:
            seed_topics |= set(by_path[p]["topics"])
    if seed_topics:
        for d in docs:
            ov = sorted(set(d["topics"]) & seed_topics)
            if ov:
                e = entry(d["path"])
                e["src"].add("topic")
                e["topics"] = ov
    # 通道4 relation 图遍历
    rel_edges, rel_nodes = [], set()
    rel_concepts = set()
    if route["need_relations"]:
        units = load_units(kb)
        seeds = set(route["topics"]) | set(route["keywords"]) | seed_topics
        seeds.discard("")
        if units and seeds:
            rel_edges, rel_nodes = traverse_relations(units, seeds, hops)
            if route["unit_type"] and route["unit_type"] != "relation":
                rel_edges = []          # unit_type 非 relation 时不返回关系结果
            for u in rel_edges:
                rel_concepts |= {u.get("subject"), u.get("object")}
                p = _unit_doc_path(u.get("doc_id"), by_path)
                if p:
                    entry(p)["src"].add("relation")
    rel_concepts.discard(None)
    con.close()

    rows = []
    for p, e in hits.items():
        d = by_path.get(p)
        if d is None:
            continue
        if d["stale"] and not route["include_stale"]:
            continue
        if route["flow"] and d["flow"] != route["flow"]:
            continue
        if route["stage"] and d["stage"] != route["stage"]:
            continue
        rows.append({"doc": d, "entry": e,
                     "weight": max(SRC_WEIGHT[c] for c in e["src"])})
    rows.sort(key=lambda r: r["doc"]["updated"] or "", reverse=True)
    rows.sort(key=lambda r: r["entry"]["bm25"]
              if r["entry"]["bm25"] is not None else 0.0)
    rows.sort(key=lambda r: -r["weight"])
    rows = rows[:route["top_k"]]
    # 被 FTS 门槛滤掉、但被 hook/topic/relation 通道补回并最终进结果的数量
    _filtered_paths = {f["doc_id"] for f in fts_filtered}
    rescued = [r["doc"]["path"] for r in rows if r["doc"]["path"] in _filtered_paths]
    elapsed = (time.perf_counter() - t0) * 1000

    def cnt(ch):
        return sum(1 for r in rows if ch in r["entry"]["src"])

    if as_json:
        print(json.dumps({
            "query": query, "route": route, "route_source": src,
            "warnings": warnings,
            "hits": [{"path": r["doc"]["path"], "title": r["doc"]["title"],
                      "channels": sorted(r["entry"]["src"], key=lambda c: -SRC_WEIGHT[c]),
                      "weight": r["weight"], "bm25": r["entry"]["bm25"],
                      "matched_hooks": r["entry"]["hooks"],
                      "matched_topics": r["entry"]["topics"],
                      "stale": r["doc"]["stale"]} for r in rows],
            "relations": [{"subject": u.get("subject"), "predicate": u.get("predicate"),
                           "object": u.get("object"), "id": u.get("id"),
                           "doc_id": u.get("doc_id")} for u in rel_edges],
            "relation_concepts": sorted(rel_concepts),
            "relation_new_nodes": sorted(rel_nodes),
            "fts_stats": {"raw": fts_raw, "kept": fts_kept,
                          "filtered": len(fts_filtered), "floor_on": floor_on,
                          "min_bigram_hits": min_bigram_hits,
                          "rescued_by_other_channels": len(rescued),
                          "filtered_detail": fts_filtered},
            "elapsed_ms": round(elapsed, 1),
        }, ensure_ascii=False, indent=2))
        return

    print(f"[recall] query={query!r}")
    print(f"[recall] 路由（{src}）：" + json.dumps(route, ensure_ascii=False))
    for w in warnings:
        print(f"[recall][校验] ({w['code']}) {w['detail']}")
    if warnings:
        print(f"[recall] 校验日志：{os.path.join(kb, ROUTE_WARN_LOG)}")
    print(f"[recall] 命中 {len(rows)} 条（hook {cnt('hook')} / fts {cnt('fts')} / "
          f"topic {cnt('topic')} / relation {cnt('relation')}）")
    if floor_on or fts_filtered:
        print(f"[recall] FTS 命中 {fts_raw} 条 → 保留 {fts_kept} 条"
              f"（弱命中过滤 {len(fts_filtered)} 条，门槛 ≥{min_bigram_hits}）；"
              f"其他通道补回 {len(rescued)} 条")
        if fts_filtered:
            print(f"[recall] 弱命中日志：{os.path.join(kb, FTS_FILTER_LOG)}")
    print()
    for i, r in enumerate(rows, 1):
        d, e = r["doc"], r["entry"]
        tags = "+".join(sorted(e["src"], key=lambda c: -SRC_WEIGHT[c]))
        bm = f"{e['bm25']:.3f}" if e["bm25"] is not None else "—"
        tail = "  [stale]" if d["stale"] else ""
        print(f"{i:>2}. {d['title']}  [{tags}]  [{bm}]{tail}")
        print(f"     {d['path']}")
        if e["hooks"]:
            print(f"     命中问法: {'; '.join(e['hooks'])}")
        if e["topics"]:
            print(f"     主题命中: {e['topics']}")
        if d["summary"]:
            print(f"     摘要: {d['summary'][:80]}")
    if rel_edges:
        print(f"\n## 关联结果（relation 图遍历 {hops} 跳，{len(rel_edges)} 条）")
        for u in rel_edges[:20]:
            pred = u.get("predicate") or u.get("relation_type") or ""
            print(f"- {u.get('subject')} —{pred}→ {u.get('object')}   [{u.get('id','')}]")
    if rel_concepts:
        print(f"\n## 关联概念（{len(rel_concepts)} 个，relation 边端点）："
              f"{'、'.join(sorted(rel_concepts))}")
    print(f"\n[recall] 耗时 {elapsed:.1f} ms")


def main():
    ap = argparse.ArgumentParser(description="确定性检索引擎")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--kb", required=True)
    b.add_argument("--notes", default=DEFAULT_NOTES_DIR)
    b.add_argument("--rebuild", action="store_true")

    s = sub.add_parser("search")
    s.add_argument("--kb", required=True)
    s.add_argument("--query", default="")
    s.add_argument("--dim", action="append", help="如 domains=AI 或 tools=Codex,剪辑")
    s.add_argument("--topics", default=None,
                   help="按内容主题过滤，逗号分隔，如 --topics 选品,关键词")
    s.add_argument("--flow", default=None, help="按工作流过滤")
    s.add_argument("--stage", default=None, help="按环节过滤（需配合 --flow）")
    s.add_argument("--substage", default=None, help="按子分组过滤（需配合 --flow --stage）")
    s.add_argument("--rank", action="append", default=None,
                   help="排序键，可重复：相关度 / 时间 / 类型优先级（按序级联）")
    s.add_argument("--include-stale", action="store_true",
                   help="把 stale 笔记纳入结果（默认过滤并在输出中提示被过滤数量）")
    s.add_argument("--k", type=int, default=20)
    s.add_argument("--min-bigram-hits", type=int, default=DEFAULT_MIN_BIGRAM_HITS,
                   help="FTS 通道门槛：查询切出 >=2 个查询 gram 时要求至少命中这么多个不同的 "
                        "gram（汉字/假名/韩文/泰文为 2-gram，字母词为整词）；1 表示关闭。"
                        "hook/topic/relation 通道不受此限制")

    p = sub.add_parser("pull")
    p.add_argument("--kb", required=True)
    p.add_argument("--recipe", required=True)
    p.add_argument("--include-stale", action="store_true",
                   help="覆盖 recipe 的 stale 过滤，召回 stale 笔记")
    p.add_argument("--k", type=int, default=0)

    u = sub.add_parser("units")
    u.add_argument("--kb", required=True)
    u.add_argument("--type", default=None,
                   help="claim/concept/relation/procedure/qa/open_question/conflict（asset 可选）")
    u.add_argument("--topic", default=None)
    u.add_argument("--confidence", default=None, help="high/medium/low")
    u.add_argument("--status", default=None, help="draft/confirmed")
    u.add_argument("--k", type=int, default=50)

    rc = sub.add_parser("recall")
    rc.add_argument("--kb", required=True)
    rc.add_argument("--query", default="")
    rc.add_argument("--route", default=None, help="路由 JSON 文件路径，- 表示读 stdin")
    rc.add_argument("--route-json", default=None, help="路由 JSON 内联字符串")
    rc.add_argument("--hops", type=int, default=1, help="relation 图遍历跳数（1–3，默认 1）")
    rc.add_argument("--k", type=int, default=0, help="覆盖路由里的 top_k")
    rc.add_argument("--min-bigram-hits", type=int, default=DEFAULT_MIN_BIGRAM_HITS,
                    help="FTS 通道门槛：查询切出 >=2 个查询 gram 时要求至少命中这么多个不同的 "
                         "gram（汉字/假名/韩文/泰文为 2-gram，字母词为整词）；1 表示关闭。"
                         "hook/topic/relation 通道不受此限制")
    rc.add_argument("--json", action="store_true", dest="as_json",
                    help="输出机器可读 JSON")

    args = ap.parse_args()
    if VALID_UNIT_TYPES is None:
        # 类型口径不可用：五个子命令一律红，不给"照常跑但偷偷不清洗 unit_type"的机会（P12-fb）
        raise SystemExit("[search_index] unit_type 口径不可用（build_units 导入失败），拒绝按猜测清洗路由")
    if args.cmd == "build":
        cmd_build(args.kb, args.notes, args.rebuild)
    elif args.cmd == "search":
        cmd_search(args.kb, args.query, args.dim, args.topics, args.flow,
                   args.stage, args.substage, args.k, args.rank, args.include_stale,
                   args.min_bigram_hits)
    elif args.cmd == "recall":
        cmd_recall(args.kb, args.query, args.route, args.route_json,
                   args.k, max(1, min(3, args.hops)), args.as_json,
                   args.min_bigram_hits)
    elif args.cmd == "units":
        cmd_units(args.kb, args.type, args.topic, args.confidence, args.status, args.k)
    else:
        cmd_pull(args.kb, args.recipe, args.k, args.include_stale)


if __name__ == "__main__":
    main()
