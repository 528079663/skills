#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify.py — 知识库骨架/产物自检。

检查项（对应 references/04_pipeline.md 第 11 节）：
  C1 必备文件；C2 必备目录；C3 无未渲染 {{}} 槽位（笔记模板除外）；
  C4 笔记 frontmatter 合法；C5 样板源路径可达；C6 无原文复制（启发式）；
  C7 规则档与 AGENTS 一致；C8 问题资产库存在；C9 三段分标；C10 双链目标存在；
  C11 主轴物理位置一致；C12 检索索引 schema 版本与篇数；C13 主题层非空；
  C14 源目录只读（对 sha256 基线，见下）；C15 信心与归属（confidence 只 WARN）。
C5 = 样板源路径 + **全库每篇原子笔记的 `sources`**（非空且可达，缺即 FAIL）；
   路径基准两种都认：`source_root/<rel>` 与 `<kb>/<rel>`；拿不到 source_root 时只验非空并 WARN。
C9 = 三段分标缺失即 **FAIL**（此前两分支都返回 warn，等于从没拦过）。
C15 = `confidence` 为 low / 缺失 / 值域非法 → **WARN**（流程约束，绝不 FAIL，处置由人）。
C12/C13 为 Step 6 之后的硬门禁：索引 0 篇或主题层为空一律 fail，不能 PASS。
C12 除校验索引 schema 版本与篇数外，还比对 meta.notes_indexed 与磁盘实际笔记数
（目录口径同 build/build_topics 的 DEFAULT_NOTES_DIR）——不一致即 FAIL，提示 --rebuild。
早期步骤（Step 1–5，尚无索引/主题层）可用 --allow-empty-index 降级为 warn。
注意：该 flag **不跳过**比对，而是把 C12/C13 的 fail 降级为 warn——即它会绕过
C12/C13 这两道门禁（含磁盘篇数比对），**仅供探针/CI 使用，交付验收与生产不要开**。

C14 源目录只读——兑现 AGENTS 模板「源资料保护 / 重新扫描源目录，比对新增/变更/路径失效」：
  · 基线**只能显式** `--snapshot-source` 建立，写 `_meta/source_snapshot.json`，永不自动重建；
  · 只比 sha256（资料文档 md/pdf/txt/srt）与媒体数量，**不比 mtime**；
  · 删除 / 内容变 → fail；无基线、基线路径不存在（换盘挪目录）、新增未纳管 → warn；
  · 解析优先级：`--source-root` > `config.source_root` > 都没有则 warn 跳过。

**写文件范围**：只写 `_meta/` 下的报告（`--out`）与源目录基线（`--snapshot-source`）；
**没有 `--fix`**，也永不写笔记 / units / topics.json / 索引 / 源资料——修东西是执行 AI 的活。
输出 JSON 报告；有 fail 时退出码 1。
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

try:  # 与 search_index.py 的 SCHEMA_VERSION / 默认笔记目录保持同源，避免两处各写一份
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import search_index as _si
    EXPECTED_INDEX_SCHEMA = _si.SCHEMA_VERSION
    DEFAULT_NOTES_DIR = getattr(_si, "DEFAULT_NOTES_DIR", None)   # 属性被改名 → 宁可 None 也不要拿字面量继续跑
except Exception:  # pragma: no cover
    # 兜底**不产出可用值**（P12-fb）：期望版本/目录名一旦猜出来，C12 就会拿猜的值去判真库，
    # 旧索引被判"版本一致"、笔记目录被判"缺失"这类误诊都从这一行开始。置 None，由消费端显式报红。
    EXPECTED_INDEX_SCHEMA = None
    DEFAULT_NOTES_DIR = None

REQUIRED_FILES = ["README.md", "AGENTS.md"]
# 来源笔记的物理位置：这一段**保持字面不可配**（⑨ 定案，发现 28 的落点就是它）
SOURCE_NOTE_DIR_REL = "素材库/_来源地图"
# 聚合页**显式白名单**（乙批 B8）：豁免"这篇不是原子笔记"从此靠这张表，不靠 `_` 前缀——
# 前缀是会腐烂的暗号：`_临时.md` 这种文件从前被静默豁免，C4/C9/C11 都看不见它（负控见 P12-dir⑩）。
# `_主题地图.md` **本库不存在**（build_topics 写的是不带下划线的 `00_导航/主题地图.md`），
# 留着是为其他库形状预留；本库实际生效的是 `_流程.md`/`_总览.md`/`_提示词资产.md`/`_模板.md`。
AGGREGATE_PAGES = ("_流程.md", "_总览.md", "_主题地图.md", "_提示词资产.md", "_模板.md")
REQUIRED_DIRS_BASE = ["00_导航", "99_收件箱", "_meta"]
REQUIRED_DIRS = REQUIRED_DIRS_BASE + [DEFAULT_NOTES_DIR]   # 兼容旧引用；实际判定走 required_dirs()


def required_dirs(notes_dir):
    """无 config 分支的必备目录：笔记目录那一项跟着解析出的 notes_dir 走，其余三项不变。"""
    return REQUIRED_DIRS_BASE + [notes_dir]
# 仅校验本 Skill render 阶段应替换的槽位；不干涉资料里合法的 n8n 表达式/提示词示例 {{}}
RENDER_SLOTS = ["kb_name", "archetype_name", "purpose", "source_root",
                "directory_tree", "flow", "date", "rules_table",
                "privacy_rules", "output_rules", "unsorted_rules"]
UNFILLED_RE = re.compile(r"\{\{\s*(" + "|".join(RENDER_SLOTS) + r")\s*\}\}")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
THREE_PARTS = ["资料原话", "归纳结论", "AI 推断"]

# 两个口径**分家**（发现 28：模板要求原子笔记「关联」节留 `来源：[[来源笔记链接]]`，
# 而来源笔记物理上在 素材库/_来源地图/——stem 全集只收 工作流/ 就会把这条合法链判成失效链）：
#   SCAN_DIRS        = 被检对象：C4/C5/C9/C10/C11/C15 扫哪些笔记里的**内容**。不变。
#   STEM_SOURCE_DIRS = 双链目标全集：`[[目标]]` 的"目标存在"允许在哪些目录里解析。
#                    （乙批 B7：config.link_target_dirs 只能在它后面**追加**，前两段口径不动。）
# 这不是放宽判据——C10 仍然只判「目标存在」，一个字没改；改的是**在哪找目标**。
# 两个常量现在只是**默认值**：main() 会按解析出的 notes_dir 就地生成 scan_dirs / stem_dirs，
# 无参数 + 无 config 时 notes_dir 必然等于 DEFAULT_NOTES_DIR → 三个集合与从前逐元素相同。
SCAN_DIRS = (DEFAULT_NOTES_DIR,)
STEM_SOURCE_DIRS = (DEFAULT_NOTES_DIR, SOURCE_NOTE_DIR_REL)
# 单篇笔记异常大（疑似复制原文）；阈值 200KB
NOTE_SIZE_LIMIT = 200 * 1024


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def _q(v):
    """剥**成对**的首尾引号再 strip：只认 `"..."` 与 `'...'`，单侧或不配对一律不动。
       YAML 写 `stage: "3_搭建与开发"` 时引号会连进值里，`endswith`/`==` 直接比就误红（乙批 B5）。
       只剥一层、不递归；半截引号**不额外造语法校验**（按裁决接受这个边界）。"""
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("\"", "'"):
        return v[1:-1].strip()
    return v


def parse_frontmatter(text):
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = _q(v)
    return fm


FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")


def strip_code(text):
    """移除围栏/行内代码：n8n 表达式、代码片段里的 {{}} 属合法技术内容。"""
    return INLINE_CODE_RE.sub("", FENCE_RE.sub("", text))


def count_disk_notes(kb, notes_dir=None):
    """磁盘实际笔记数——与 build / build_topics 同口径：

    目录取 DEFAULT_NOTES_DIR（默认 `工作流`）；只数 `.md`；跳过 `_` 前缀的聚合页
    （`_流程.md`/`_总览.md`）；frontmatter 解析不出来的不计。目录不存在返回 None。
    """
    root = os.path.join(kb, notes_dir or DEFAULT_NOTES_DIR)
    if not os.path.isdir(root):
        return None
    n = 0
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".md") or fn in AGGREGATE_PAGES:   # B8：显式白名单
                continue
            try:
                with open(os.path.join(dirpath, fn), "r", encoding="utf-8",
                          errors="ignore") as fh:
                    text = fh.read()
            except OSError:
                continue
            if parse_frontmatter(text) is None:
                continue
            n += 1
    return n


def check_index_consistency(kb, notes_dir=None):
    """C12 的索引一致性判定——**单一实现**，verify 与 audit 共用。

    返回 (status, message)，status ∈ {"pass", "fail", "na"}：
      - "pass"：schema 版本一致、索引篇数 > 0 且等于磁盘实际篇数
      - "fail"：索引缺失之外的不一致（schema 不符 / 0 篇 / 与磁盘不符 / 读失败）
      - "na"  ：索引文件不存在——audit 标 N/A（不 FAIL）；verify 视为 fail（门禁口径）
    """
    db_path = os.path.join(kb, "_meta", "search.db")
    if not os.path.isfile(db_path):
        return "na", "未找到 _meta/search.db（先跑 search_index.py build）"
    try:
        con = sqlite3.connect(db_path)
        row_v = con.execute(
            "SELECT value FROM meta WHERE key='schema_version'").fetchone()
        row_n = con.execute(
            "SELECT value FROM meta WHERE key='notes_indexed'").fetchone()
        con.close()
        ver = row_v[0] if row_v else None
        cnt = int(row_n[0]) if row_n else 0
        if ver is None:
            return "fail", "索引缺 meta.schema_version（旧索引，请 --rebuild 重建）"
        if EXPECTED_INDEX_SCHEMA is None:
            return "fail", "无法确定期望索引版本（search_index 导入失败）"
        if int(ver) != EXPECTED_INDEX_SCHEMA:
            return "fail", (f"索引 schema v{ver} ≠ 期望 v{EXPECTED_INDEX_SCHEMA}，"
                            f"请 --rebuild 重建")
        if cnt <= 0:
            return "fail", "索引笔记 0 篇，不能 PASS"
        # 索引自述篇数 vs 磁盘实际篇数：笔记增删后忘了 rebuild 会在这里暴露
        nd = notes_dir or DEFAULT_NOTES_DIR
        disk_n = count_disk_notes(kb, notes_dir)
        if disk_n is None:
            return "fail", (f"磁盘笔记目录缺失：{nd}"
                            f"（索引自述 {cnt} 篇），请检查笔记目录或 --rebuild")
        if disk_n != cnt:
            return "fail", (f"索引 {cnt} 篇 ≠ 磁盘实际 {disk_n} 篇"
                            f"（目录 {nd}），请 --rebuild 重建")
        return "pass", f"schema v{ver}；索引 {cnt} 篇 = 磁盘 {disk_n} 篇"
    except (sqlite3.Error, ValueError) as e:
        return "fail", f"读索引失败: {e}"


# ---------- C14 源目录只读校验 ----------
# 实现依据：AGENTS 模板第 2 节「源资料保护」+ 第 6 节「重新扫描源目录，比对新增/变更/路径失效」
# —— 那句承诺过去没有任何脚本兑现，C14 就是它的载体。
SOURCE_SNAPSHOT_REL = os.path.join("_meta", "source_snapshot.json")
# 哪些扩展名算「资料文档」（逐篇 sha256）、哪些只算「媒体」（只计数量）——
# **口径来自 scan_sources.py，不在这里另写一份**，避免两处漂移。
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import scan_sources as _ss
    # 直接取属性、不给默认值：改名即 AttributeError → 走 except 置 None（兜底不得产出可用口径）
    DOC_EXT = set(_ss.TEXT_BODY_EXT)
    MEDIA_GROUPS = {"images": set(_ss.IMG_EXT), "videos": set(_ss.VIDEO_EXT),
                    "archives": set(_ss.ARCHIVE_EXT), "executables": set(_ss.EXEC_EXT),
                    "audio": set(_ss.MEDIA_DOC_EXT)}
except Exception:  # pragma: no cover
    DOC_EXT = None
    MEDIA_GROUPS = None
OTHER_GROUP = "other"


def _sha256_of(path):
    """流式哈希；读不到返回 None（交给调用方判 warn，不当成"被修改"）。"""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _media_group(ext):
    for name, exts in MEDIA_GROUPS.items():
        if ext in exts:
            return name
    return OTHER_GROUP


def scan_source_tree(source_root):
    """walk 全目录，返回 (docs, media_counts)。

    docs: {相对路径: size}——只有这类文件逐篇 sha256；
    media_counts: {分组: 数量}——媒体/杂项只计数量，不读内容（大库才跑得起）。
    """
    docs, media_counts = {}, {}
    for dirpath, dirnames, filenames in os.walk(source_root):
        dirnames.sort()
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, source_root).replace("\\", "/")
            ext = os.path.splitext(fn)[1].lower()
            try:
                size = os.path.getsize(full)
            except OSError:
                size = -1
            if ext in DOC_EXT:
                docs[rel] = size
            else:
                g = _media_group(ext)
                media_counts[g] = media_counts.get(g, 0) + 1
    return docs, media_counts


def build_source_snapshot(source_root):
    """建基线：documents 逐篇 sha256 + 媒体计数。"""
    docs, media_counts = scan_source_tree(source_root)
    files = {}
    unreadable = []
    for rel in sorted(docs):
        full = os.path.join(source_root, rel.replace("/", os.sep))
        digest = _sha256_of(full)
        if digest is None:
            unreadable.append(rel)
            continue
        files[rel] = {"size": docs[rel], "sha256": digest}
    return {"created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_root": os.path.abspath(source_root),
            # 基线是用哪一份「资料文档」清单建的，随基线一起存：清单口径变了（如 A4 把
            # .html/.docx 纳进来）就能与当前口径比对，不会把口径差误报成"源目录新增"。
            "text_body_ext": sorted(DOC_EXT),
            "files": files,
            "media_counts": dict(sorted(media_counts.items())),
            "skipped_unreadable": sorted(unreadable)}, files, unreadable


def write_source_snapshot(kb, snapshot):
    """原子写 _meta/source_snapshot.json。"""
    path = os.path.join(kb, SOURCE_SNAPSHOT_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)
    return path


def load_source_snapshot(kb):
    p = os.path.join(kb, SOURCE_SNAPSHOT_REL)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}     # 存在但读坏 → 空 dict，调用方按"基线不可用"处理


def check_c14_source_readonly(kb, source_root, snapshot, wrote_new=False):
    """C14：源目录只读校验。返回 (status, message, changed)。

    `changed` = 被删/被改的源文件相对路径清单，供上层出「该给哪些笔记标 stale」的工单。

    只比 sha256 与数量，**不比 mtime**——touch 过但内容不变 = 未修改。
      fail：基线里的文件消失 / 内容变了（sha256 不同）
      warn：没有基线 / 基线指向的路径不存在（换盘挪目录）/ 新增未纳管文件 / 有文件读不了
            / **清单口径与基线不一致**（A4：基线自带 `text_body_ext`，与当前 DOC_EXT 不同时
              只赦免 added，其余判据一律照旧——见下面的比对块）
      pass：documents 全部 sha256 一致，且媒体数量没变
    """
    if wrote_new:
        n = len(snapshot.get("files", {}))
        return "pass", f"已建立基线：{n} 篇资料文档入 sha256（此后源目录变动会被 C14 抓到）", []

    if not source_root:
        return "warn", "无源目录（config.source_root 与 --source-root 都没有），跳过只读校验", []

    snap = load_source_snapshot(kb)
    if snap is None:
        return "warn", "无源目录基线，请先跑 verify.py --kb <KB> --snapshot-source", []
    if not snap:
        return "warn", f"基线文件不可读（{SOURCE_SNAPSHOT_REL} 解析失败），请重建快照", []

    if not os.path.isdir(source_root):
        # 换机器/挪盘是常态，不是事故——红在这里只会让人不信这个门禁
        return "warn", (f"基线指向的源目录不存在：{source_root}"
                        f"（路径挪过了？在新位置重跑 --snapshot-source）"), []

    base_files = snap.get("files", {})
    docs, media_counts = scan_source_tree(source_root)

    deleted = sorted(set(base_files) - set(docs))
    added = sorted(set(docs) - set(base_files))
    modified, unreadable = [], []
    for rel in sorted(set(base_files) & set(docs)):
        digest = _sha256_of(os.path.join(source_root, rel.replace("/", os.sep)))
        if digest is None:
            unreadable.append(rel)
        elif digest != base_files[rel].get("sha256"):
            modified.append(rel)

    media_diff = []
    for grp in sorted(set(snap.get("media_counts", {})) | set(media_counts)):
        was, now = snap.get("media_counts", {}).get(grp, 0), media_counts.get(grp, 0)
        if was != now:
            media_diff.append(f"{grp} {was}→{now}")

    def brief(items, n=8):
        return "、".join(items[:n] + ([f"…共 {len(items)} 个"] if len(items) > n else []))

    fails, warns = [], []
    # —— 清单口径比对（A4）：基线自带的 text_body_ext 与当前 DOC_EXT 不一致时，差额属"口径变了"，
    #    不是源目录被动过。**只赦免 added**：deleted / modified / unreadable / 媒体计数一律照旧判，
    #    该 FAIL 还是 FAIL——赦免不能变成放松校验。旧基线没有这个键 → 按"口径未知"同样走文案 A。
    base_ext = snap.get("text_body_ext")
    cur_ext = sorted(DOC_EXT)
    ext_mismatch = base_ext != cur_ext
    if ext_mismatch:
        was = "%d 类" % len(base_ext) if base_ext else "基线侧未知（早于清单版本字段）"
        warns.append(f"基线是旧清单口径（{was} → 当前 {len(cur_ext)} 类），"
                     f"需重跑 verify.py --kb <KB> --snapshot-source 重建基线后才可比")
        if added:
            warns.append(f"因清单变宽而多出的 {len(added)} 篇本轮不计为新增"
                         f"（重建基线后若仍存在，才是真新增）")
            added = []
    if deleted:
        fails.append(f"源文件被删除 {len(deleted)} 个：{brief(deleted)}")
    if modified:
        fails.append(f"源文件被修改 {len(modified)} 个：{brief(modified)}")
    if added:
        warns.append(f"源目录新增 {len(added)} 个文档未纳管：{brief(added)}"
                     f"；请重建基线并走 intake（Step 1 盘点 → 深抽），别直接改快照文件")
    if media_diff:
        warns.append(f"源目录媒体数量变化：{'；'.join(media_diff)}")
    if unreadable:
        warns.append(f"有文件读不了、本轮未校验：{brief(unreadable)}")

    if fails:
        return ("fail", "；".join(fails) + "。源目录按规则只读" + (
            "（另有 warning：" + "；".join(warns) + "）" if warns else ""),
            sorted(set(deleted) | set(modified)))
    if warns:
        return "warn", "；".join(warns), []
    return ("pass", f"{len(base_files)} 篇资料文档 sha256 全一致，媒体数量不变（不比 mtime）", [])


def _fm_clean(v):
    """去掉 frontmatter 值后面的行内注释，返回裸字符串。"""
    return (v or "").split("#", 1)[0].strip().strip('"').strip("'")


def fm_list(text, key):
    """从 frontmatter 原文取一个列表字段，**两种写法都认**：
       内联 `sources: [a.md, b.md]` 与 块列表 `sources:\\n  - a.md\\n  - b.md`。
       （sources 的两种写法在 04 与模板里都出现过，只认一种会把合法笔记整批判红。）
    """
    m = FRONTMATTER_RE.match(text or "")
    if not m:
        return []
    lines, out, i = m.group(1).split("\n"), [], 0
    pat = re.compile(r"^%s\s*:" % re.escape(key))
    while i < len(lines):
        ln = lines[i]
        if pat.match(ln):
            v = ln.split(":", 1)[1].strip()
            if v.startswith("[") and v.endswith("]"):
                out += [x.strip().strip('"').strip("'") for x in re.split(r"[,，]", v[1:-1])]
            elif v and not v.startswith("#"):
                out.append(_fm_clean(v))
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j][:1] in (" ", "\t")):
                s = lines[j].strip()
                if s.startswith("- "):
                    out.append(_fm_clean(s[2:]))
                j += 1
            i = j
            continue
        i += 1
    return [x for x in out if x]


def src_exists(rel, source_root, kb):
    """sources 的路径基准有两种：源资料根（模板写法）与 KB 根（04 的 `素材库/...` 写法）。
    任一命中即算存在——**不能只认一种**。"""
    rel_c = rel.replace("/", os.sep)
    bases = ([source_root] if source_root else []) + [kb]
    return any(os.path.isfile(os.path.join(b, rel_c)) for b in bases)


def main():
    ap = argparse.ArgumentParser(description="知识库产物自检")
    ap.add_argument("--kb", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--notes", default=None,
                    help="笔记目录名（相对 --kb）；优先级 CLI > config.notes_dir > %s。"
                         "注意与 progress/check_hooks 的 --notes-dir（目录本身）口径不同"
                         % DEFAULT_NOTES_DIR)
    ap.add_argument("--out", default=None, help="报告 JSON 输出路径")
    ap.add_argument("--source-root", default=None,
                    help="C14 用：源资料目录，**优先级高于 config.source_root**（换盘/挪目录时用）")
    ap.add_argument("--snapshot-source", action="store_true",
                    help="显式建立源目录基线，写 _meta/source_snapshot.json，然后继续常规自检。"
                         "不自动重建——源资料有正常增补时由人显式确认")
    ap.add_argument("--allow-empty-index", action="store_true",
                    help="【仅探针/CI】Step 1–5 尚无索引/主题层时把 C12/C13 降级为 warn；"
                         "此 flag 会绕过 C12/C13 门禁（含磁盘篇数比对），交付验收不要开")
    args = ap.parse_args()

    kb = args.kb
    config = load_json(args.config) if args.config and os.path.isfile(args.config) else None
    source_root = config["source_root"] if config else None

    # —— 笔记目录口径：CLI --notes > config.notes_dir > DEFAULT_NOTES_DIR ——
    # 三者都缺省时结果就是「工作流」，scan_dirs/stem_dirs/REQUIRED_DIRS 与从前逐元素相同（兼容红线）。
    if DEFAULT_NOTES_DIR is None and not (args.notes or (config or {}).get("notes_dir")):
        # 口径来源不可用，且调用方没自己给目录：显式红，绝不带着 None 去 join 路径（P12-fb fb-a）
        raise SystemExit("[verify] 无法确定笔记目录口径（search_index 导入失败）")
    notes_dir = args.notes or (config or {}).get("notes_dir") or DEFAULT_NOTES_DIR
    scan_dirs = (notes_dir,)
    # —— C10「目标全集」的追加档（乙批 B7）——
    #   config.link_target_dirs = ["外部来源", …]：**只做追加**，且**只有 config 一档、没有 CLI 开关**（按裁决，
    #   不新增 --link-target-dirs）。第一段仍跟 notes_dir；第二段 SOURCE_NOTE_DIR_REL 是字面常量，
    #   **不可被 config 覆盖或删**——P12-dir⑨ 钉的就是"第二段不跟 notes_dir 动"，这里也不给它绕开的口子。
    extra_stems = []
    for d in ((config or {}).get("link_target_dirs") or []):
        v = _q(str(d)).replace("\\", "/").strip("/")
        if (not v) or v.startswith("..") or v.startswith("/") or ":" in v:
            raise SystemExit("[verify] config.link_target_dirs 有非法项：要相对 kb 根的目录，"
                             "不许绝对路径或越界（%r）" % d)
        if v not in (notes_dir, SOURCE_NOTE_DIR_REL) and v not in extra_stems:
            extra_stems.append(v)
    stem_dirs = (notes_dir, SOURCE_NOTE_DIR_REL) + tuple(extra_stems)

    # —— C14 的源目录解析：CLI 覆盖 > config.source_root > 无（后面 warn） ——
    c14_source = args.source_root or source_root
    c14_ext_guard = DOC_EXT is None or MEDIA_GROUPS is None
    c14_snapshot, c14_wrote_new = None, False
    if c14_ext_guard and args.snapshot_source:
        # 建基线会把口径写进 _meta/source_snapshot.json，写错一次后面每次都"自己跟自己对齐"
        raise SystemExit("[verify] 资料清单口径不可用（scan_sources 导入失败），拒绝建基线")
    if args.snapshot_source:
        # 显式要求建基线却建不出来，不能只 warn 了事——那会让人以为基线已经在了
        if not c14_source:
            raise SystemExit("[verify] --snapshot-source 需要源目录：给 --source-root <路径>，"
                             "或让 config.json 带 source_root")
        if not os.path.isdir(c14_source):
            raise SystemExit(f"[verify] --snapshot-source 的源目录不存在：{c14_source}")
        c14_snapshot, _files, _unreadable = build_source_snapshot(c14_source)
        p = write_source_snapshot(kb, c14_snapshot)
        print(f"[verify] 源目录基线已写出：{p}（{len(_files)} 篇入 sha256"
              + (f"，{len(_unreadable)} 篇读不了被跳过）" if _unreadable else "）"))
        c14_wrote_new = True

    checks = []

    def add(cid, name, status, message=""):
        checks.append({"id": cid, "name": name, "status": status, "message": message})

    # C1 必备文件
    for f in REQUIRED_FILES + (["_meta/问题资产库.md"]):
        ok = os.path.isfile(os.path.join(kb, f.replace("/", os.sep)))
        add("C1", f"必备文件 {f}", "pass" if ok else "fail",
            "" if ok else "缺失")

    # C2 必备目录（+ config 中应落地目录）
    expect_dirs = list(required_dirs(notes_dir))
    if config:
        expect_dirs = [d["path"] for d in config["directories"] if d["create"]]
    missing_dirs = [d for d in expect_dirs
                    if not os.path.isdir(os.path.join(kb, d.replace("/", os.sep)))]
    add("C2", "目录齐全", "pass" if not missing_dirs else "fail",
        f"缺失: {missing_dirs}" if missing_dirs else f"{len(expect_dirs)} 个目录")

    # C3 未渲染槽位（排除 _meta/模板）
    unfilled = []
    for dirpath, dirnames, filenames in os.walk(kb):
        rel_dir = os.path.relpath(dirpath, kb).replace("\\", "/")
        if rel_dir.startswith("_meta/模板") or rel_dir.startswith("."):
            continue
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            p = os.path.join(dirpath, fn)
            with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            scan = strip_code(FRONTMATTER_RE.sub("", text, count=1))
            hits = UNFILLED_RE.findall(scan)
            if hits:
                unfilled.append(f"{rel_dir}/{fn}: {hits[:3]}")
    add("C3", "无未渲染槽位", "pass" if not unfilled else "fail",
        "; ".join(unfilled[:5]) if unfilled else "")

    # C4 笔记 frontmatter（检查 工作流/ 下的原子笔记；素材库/概念索引 不检查）
    # 顺带把每篇正文收进 note_rows——C5 的逐篇 sources、C15 的 confidence、C14 的 stale 工单
    # 都要用它，避免为同一批文件再走一遍盘。
    bad_fm, note_count = [], 0
    note_rows = []
    note_dir_prefixes = scan_dirs           # 被检对象：只扫解析出的笔记目录（见常量处两条口径的分家说明）
    for dirpath, dirnames, filenames in os.walk(kb):
        rel_dir = os.path.relpath(dirpath, kb).replace("\\", "/")
        if not rel_dir.startswith(note_dir_prefixes):
            continue
        for fn in filenames:
            if not fn.endswith(".md"):
                continue
            if fn in AGGREGATE_PAGES:      # B8：C4 只豁免白名单里的聚合页
                continue  # _流程.md / _总览.md 是聚合页，不是原子笔记
            note_count += 1
            with open(os.path.join(dirpath, fn), "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            fm = parse_frontmatter(text)
            rel = f"{rel_dir}/{fn}"
            note_rows.append((rel, text, fm))
            if fm is None or not fm.get("flow") or not fm.get("stage") or not fm.get("substage"):
                bad_fm.append(rel)
    add("C4", "原子笔记 frontmatter（主轴三字段）", "pass" if not bad_fm else
        ("warn" if note_count == 0 else "fail"),
        f"检查 {note_count} 篇；缺 flow/stage/substage: {bad_fm[:5]}" if bad_fm else f"{note_count} 篇合法")

    # C5 来源可达：样板抽样 + **全库原子笔记逐篇**（AGENTS §4.3「每条结论挂 sources」）
    bad_src = []
    if config and source_root:
        for s in config.get("sample_notes", []):
            if not os.path.isfile(os.path.join(source_root, s["source"].replace("/", os.sep))):
                bad_src.append(s["source"])
    no_sources, unreachable = [], []
    for rel, text, fm in note_rows:
        srcs = fm_list(text, "sources")
        if not srcs:
            no_sources.append(rel)
            continue
        if source_root:      # 拿不到源目录时不判"不可达"——那只说明本次没法验它
            for s in srcs:
                if not src_exists(s, source_root, kb):
                    unreachable.append(f"{rel} → {s}")
    if no_sources or unreachable or bad_src:
        parts = []
        if bad_src:
            parts.append(f"样板失效 {len(bad_src)}: {bad_src[:3]}")
        if no_sources:
            parts.append(f"sources 为空 {len(no_sources)} 篇: {no_sources[:3]}")
        if unreachable:
            parts.append(f"来源路径不可达 {len(unreachable)} 处: {unreachable[:3]}")
        add("C5", "来源可达（样板 + 全库逐篇 sources）", "fail", f"检查 {note_count} 篇；" + "；".join(parts))
    elif note_rows and not source_root:
        add("C5", "来源可达（样板 + 全库逐篇 sources）", "warn",
            f"{len(note_rows)} 篇 sources 均非空；**没拿到 source_root（不带 --config），"
            f"可达性未验**——只验了非空")
    else:
        add("C5", "来源可达（样板 + 全库逐篇 sources）", "pass",
            f"{len(note_rows)} 篇原子笔记 sources 非空且可达"
            + (f"；样板 {len(config.get('sample_notes', []))} 篇可达" if config else ""))

    # C6 原文复制启发：笔记异常大
    big = []
    for dirpath, dirnames, filenames in os.walk(kb):
        for fn in filenames:
            if fn.endswith(".md"):
                p = os.path.join(dirpath, fn)
                if os.path.getsize(p) > NOTE_SIZE_LIMIT:
                    big.append(os.path.relpath(p, kb))
    add("C6", "无原文复制(启发)", "pass" if not big else "warn",
        f"异常大文件: {big[:5]}" if big else "")

    # C7 规则一致
    if config and os.path.isfile(os.path.join(kb, "AGENTS.md")):
        with open(os.path.join(kb, "AGENTS.md"), "r", encoding="utf-8") as fh:
            agents = fh.read()
        missing_levels = [v for v in config["rules"].values() if v not in agents]
        add("C7", "规则档一致", "pass" if not missing_levels else "fail",
            f"AGENTS 缺少档位: {set(missing_levels)}" if missing_levels else "")
    else:
        add("C7", "规则档一致", "warn", "无 config/AGENTS，跳过")

    # C8 问题资产库
    ok = os.path.isfile(os.path.join(kb, "_meta", "问题资产库.md"))
    add("C8", "问题资产库", "pass" if ok else "fail", "" if ok else "缺失")

    # C9 三段分标（原子笔记必须含三标记）
    # C10 双链目标存在 —— **只做目标存在校验**：
    #   · 有 [[目标]] 且解析不到本库笔记 → warn（不 fail，见下方判定）；
    #   · 一个 [[ ]] 都没有 → pass。「没有链」不是缺陷：双链的加链规约见
    #     references/08_topics_pipeline_units.md 第 3.6 节——无明确引用则不加链、允许孤岛。
    #   · **禁止**在此新增边密度 / 出流入链 / 连通性校验，也不要加自动补链能力。
    # C11 主轴物理位置一致性（笔记路径中的 flow/stage 与 frontmatter 一致）
    note_stems, missing_parts, broken_links, bad_phys = set(), [], [], []
    pending_links = []  # (所在文件, 目标名)——stem 收齐后再判，见下方说明
    # ---- stem 全集（C10 的"去哪儿找目标"）：先收 STEM_SOURCE_DIRS ----
    # 模板的「关联」节要求留 `来源：[[来源笔记链接]]`（08 §3.6.5 明写"来源指向是真引用"），
    # 而来源笔记物理上在 `素材库/_来源地图/`——只收 工作流/ 会把这条**合法**链判成失效链（发现 28）。
    # 注意：这一步只扩"目标在哪找"，不改判据；下面的循环仍只扫 SCAN_DIRS（谁的内容被检）。
    for dirpath, dirnames, filenames in os.walk(kb):
        rel_dir = os.path.relpath(dirpath, kb).replace("\\", "/")
        if not rel_dir.startswith(stem_dirs):
            continue
        for fn in filenames:
            if fn.endswith(".md") and fn not in AGGREGATE_PAGES:   # B8
                note_stems.add(os.path.splitext(fn)[0])
    for dirpath, dirnames, filenames in os.walk(kb):
        rel_dir = os.path.relpath(dirpath, kb).replace("\\", "/")
        if not rel_dir.startswith(note_dir_prefixes):
            continue
        for fn in filenames:
            if not fn.endswith(".md") or fn in AGGREGATE_PAGES:   # B8：显式白名单
                continue
            stem = os.path.splitext(fn)[0]
            note_stems.add(stem)
            p = os.path.join(dirpath, fn)
            with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            body = FRONTMATTER_RE.sub("", text, count=1)
            fm = parse_frontmatter(text) or {}
            # 三段分标
            miss = [m for m in THREE_PARTS if m not in text]
            if miss:
                missing_parts.append(f"{rel_dir}/{fn} 缺{miss}")
            # 双链：先收着，等 stem 全集齐了再判（同趟边收边判会误伤"引用排在后面的笔记"）
            for link in WIKILINK_RE.findall(text):
                if link.strip():
                    pending_links.append((f"{rel_dir}/{fn}", link.strip()))
            # C11 物理位置一致性：路径应为 工作流/<flow>/<n>_<stage>/xxx.md
            parts = rel_dir.split("/")
            if len(parts) >= 3:
                path_flow = parts[1]
                path_stage_dir = parts[2]  # 如 "1_找素材"
                fm_flow = fm.get("flow", "")
                fm_stage = fm.get("stage", "")
                if fm_flow and path_flow != fm_flow:
                    bad_phys.append(f"{rel_dir}/{fn}: 路径flow={path_flow} vs frontmatter={fm_flow}")
                if fm_stage and not path_stage_dir.endswith(fm_stage):
                    bad_phys.append(f"{rel_dir}/{fn}: 路径stage={path_stage_dir} vs frontmatter={fm_stage}")
    # C10 判定：stem 全集已就绪，此时才可判目标存在
    for src_file, link in pending_links:
        if link not in note_stems:
            broken_links.append(f"{src_file} → [[{link}]]")
    # 缺三段分标 = **fail**（对齐 04 第 11 节「任何 error 级项未清零，不得宣布完成」）。
    # 这里原来写的是 `("warn" if note_count == 0 else "warn")`——两分支同值，等于永远是 warn，
    # 三段分标这条硬约束从来没有真门禁过。
    add("C9", "三段分标(资料/归纳/推断)",
        "pass" if not missing_parts else "fail",
        f"{len(missing_parts)} 篇缺标记: {missing_parts[:5]}" if missing_parts else "原子笔记齐全")
    add("C10", "双链目标存在",
        "pass" if not broken_links else "warn",
        f"{len(broken_links)} 个失效链接: {broken_links[:5]}" if broken_links else "无失效双链")
    add("C11", "主轴物理位置一致",
        "pass" if not bad_phys else ("warn" if note_count == 0 else "fail"),
        f"{len(bad_phys)} 处不一致: {bad_phys[:5]}" if bad_phys else "flow/stage 与路径一致")

    # C12 检索索引：schema 版本 + 篇数（0 篇不能 PASS）；判定逻辑与 audit 共用同一函数
    # 这里**必须把 notes_dir 传下去**：以前不传，函数内部回落到默认名，换名库里 C12 会按
    # 「工作流」数磁盘篇数 → 报成「索引 N 篇 ≠ 磁盘 0 篇」，把参数没接上的问题伪装成没 rebuild。
    idx_status, idx_msg = check_index_consistency(kb, notes_dir)
    if idx_status == "na":
        # 磁盘 0 篇笔记＝还停在 Step 1–5 的空库，此时没有内容可索引，不是错误。
        # 磁盘**有**笔记却没索引＝忘了 build，必须 FAIL —— 这条门禁一点没松。
        # （不用 --allow-empty-index：那个 flag 会连「磁盘篇数比对」一起绕过，会把
        #   "忘了 rebuild" 也放过，故仅限探针/CI，这里改的是判定本身不是开关。）
        if note_count == 0:
            idx_status = "pass"
            idx_msg = ("空库：磁盘 0 篇笔记，尚无内容可索引"
                       "（Step 6 产出笔记后须跑 search_index.py build）")
        else:
            idx_status = "fail"      # 门禁口径：有笔记却无索引即 FAIL
    add("C12", "检索索引 schema 版本、篇数与磁盘一致", idx_status, idx_msg)

    # C13 主题层非空
    topics_path = os.path.join(kb, "_meta", "topics.json")
    tp_status, tp_msg = (
        ("pass", "空库：尚无笔记，主题层待 Step 6 后由 build_topics.py 生成")
        if note_count == 0 else
        ("fail", "未找到 _meta/topics.json（先跑 build_topics.py）"))
    if os.path.isfile(topics_path):
        try:
            tj = load_json(topics_path)
            tlist = tj.get("topics") or []
            if tlist:
                tp_status, tp_msg = "pass", f"{len(tlist)} 个内容主题"
            else:
                tp_status, tp_msg = "fail", "主题层为空（0 个主题），不能 PASS"
        except (ValueError, OSError) as e:
            tp_status, tp_msg = "fail", f"topics.json 解析失败: {e}"
    add("C13", "主题层非空", tp_status, tp_msg)

    # C14 源目录只读校验（快照基线 vs 现状；只比 sha256 与数量，不比 mtime）
    if c14_ext_guard:
        c14_status, c14_changed = "fail", []
        c14_msg = "资料清单口径不可用（scan_sources 导入失败），拒绝比对基线"
    else:
        c14_status, c14_msg, c14_changed = check_c14_source_readonly(
            kb, c14_source, c14_snapshot or {}, c14_wrote_new)

    # T3：C14 的下游工单——源资料被改/被删时，指出**哪几篇笔记还挂着它们**，
    # 提示人工确认是否标 stale。**只列不写**：绝不碰笔记文件、绝不自动改 frontmatter。
    c14_ticket = []
    if c14_changed:
        changed_set = set(c14_changed)
        changed_base = {os.path.basename(p) for p in c14_changed}
        for rel, text, _fm in note_rows:
            for s in fm_list(text, "sources"):
                if s in changed_set or os.path.basename(s) in changed_base:
                    c14_ticket.append(rel)
                    break
        c14_ticket.sort()
        if c14_ticket:
            c14_msg += f"；{len(c14_ticket)} 篇笔记依赖已变更的源资料（工单见下）"

    add("C14", "源目录只读（对基线）", c14_status, c14_msg)

    # C15 信心与归属（AGENTS §4.2 / 08 §3 硬约束 5）：low 或缺 confidence 的原子笔记
    # 不该直接躺在 工作流/ 里，应进 99_收件箱。**这是流程约束不是门禁——只 warn，绝不 fail。**
    low_conf, no_conf, bad_conf = [], [], []
    for rel, text, fm in note_rows:
        v = _fm_clean((fm or {}).get("confidence", ""))
        if not v:
            no_conf.append(rel)
        elif v == "low":
            low_conf.append(rel)
        elif v not in ("high", "medium"):
            bad_conf.append(f"{rel}（值 {v!r}）")
    if low_conf or no_conf or bad_conf:
        seg = []
        if low_conf:
            seg.append(f"low {len(low_conf)} 篇: {low_conf[:3]}")
        if no_conf:
            seg.append(f"缺 confidence {len(no_conf)} 篇: {no_conf[:3]}")
        if bad_conf:
            seg.append(f"值域非法 {len(bad_conf)} 篇: {bad_conf[:3]}")
        add("C15", "信心与归属（low/缺 confidence）", "warn",
            "；".join(seg) + "。按 08 §3 硬约束 5 应进 99_收件箱、不直接入工作流"
            "（warn 不拦路，处置由人）")
    else:
        add("C15", "信心与归属（low/缺 confidence）", "pass",
            f"{len(note_rows)} 篇 confidence 均为 high/medium" if note_rows else "无原子笔记，跳过")

    if args.allow_empty_index:
        for c in checks:
            if c["id"] in ("C12", "C13") and c["status"] == "fail":
                c["status"] = "warn"
                c["message"] += "（--allow-empty-index 已降级）"

    fails = [c for c in checks if c["status"] == "fail"]
    warns = [c for c in checks if c["status"] == "warn"]
    report = {"kb": os.path.abspath(kb), "checks": checks,
              "c14_stale_ticket": c14_ticket,
              "summary": {"pass": len(checks)-len(fails)-len(warns),
                          "fail": len(fails), "warn": len(warns)}}

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)

    for c in checks:
        mark = {"pass": "[PASS]", "fail": "[FAIL]", "warn": "[WARN]"}[c["status"]]
        line = f"{mark} {c['id']} {c['name']}"
        if c["message"]:
            line += f" — {c['message']}"
        print(line)
    if c14_ticket:
        print("\n[C14 工单] 以下笔记依赖已变更源资料，请确认是否标 stale: true")
        for rel in c14_ticket:
            print(f"  - {rel}")
        print("[C14 工单] 本工单只列不改：verify 不写任何笔记，stale 由人确认后落。")
    print(f"\n汇总：pass={report['summary']['pass']} "
          f"fail={report['summary']['fail']} warn={report['summary']['warn']}")

    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
