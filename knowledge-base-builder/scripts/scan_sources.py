#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scan_sources.py — 只读扫描源资料目录，产出 sources_manifest.json。

职责（对应 SKILL.md Step 1 与 references/04_pipeline.md 第 1 节）：
  - 分类统计全部文件；
  - 正文类（md/pdf/txt/srt）逐文件登记；图片只统计；压缩包/安装包/视频登记路径；
  - 配对检测：PDF↔同名md、妙记txt↔精华笔记、srt↔txt；
  - 读取源目录自带的 主题分类清单.csv（若存在）作为标签基线。

本脚本只读源目录，不做任何修改。
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

# 扩展名分组
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".gz"}
EXEC_EXT = {".exe", ".apk", ".msi", ".bat"}
MEDIA_DOC_EXT = {".mp3", ".wav", ".m4a"}
# 「资料文档」分两档——**登记与只读保护都覆盖两档，但深抽只吃第一档里 doc_map 认得的 .md**：
#   TEXT_READABLE_EXT  能直接当文本读（doc_map 未来可扩到这里；本批不扩）
#   NEEDS_CONVERT_EXT  必须先转换才能读（登记 + C14 保护 + **不深抽**，走人工/外部转换）
# TEXT_BODY_EXT 保持现名 = 两档并集；verify 的 DOC_EXT（C14 基线口径）读的就是它，不另写一份。
TEXT_READABLE_EXT = {".md", ".txt", ".srt", ".vtt", ".ass", ".html", ".htm", ".rtf"}
NEEDS_CONVERT_EXT = {".pdf", ".docx", ".epub", ".odt"}
TEXT_BODY_EXT = TEXT_READABLE_EXT | NEEDS_CONVERT_EXT

ESSENCE_RE = re.compile(r"·精华笔记\.md$", re.IGNORECASE)
TRANSCRIPT_RE = re.compile(r"\.transcript\.txt$", re.IGNORECASE)


def rel(path, root):
    return os.path.relpath(path, root).replace("\\", "/")


def essence_candidate(txt_path):
    # 注意 ChangeExtension 会自动补点号的坑：统一用正则替换；
    # 且只替换 basename，避免目录名含 .txt 时误伤
    d, b = os.path.split(txt_path)
    return os.path.join(d, re.sub(r"\.txt$", "·精华笔记.md", b, flags=re.IGNORECASE))


def scan(root):
    by_ext = Counter()
    md_files, pdf_files, txt_files, srt_files = [], [], [], []
    readable_other, needs_convert = [], []      # 可直读的非 md 正文 / 需转换的二进制正文
    images, videos, archives, execs, others = [], [], [], [], []
    tag_counts = Counter()
    fm_tag_re = re.compile(r"^tags:\s*(.*)$")

    for dirpath, dirnames, filenames in os.walk(root):
        # 跳过常见垃圾/回收站目录
        dirnames[:] = [d for d in dirnames if d not in {".trash", "__MACOSX", ".git"}]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            ext = os.path.splitext(fn)[1].lower()
            try:
                size = os.path.getsize(full)
            except OSError:
                size = -1
            by_ext[ext] += 1
            r = rel(full, root)

            if ext == ".md":
                md_files.append({"path": r, "size": size,
                                 "is_essence": bool(ESSENCE_RE.search(fn))})
                # 尝试读 frontmatter 标签（仅前 40 行，省开销）
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                        head = [next(fh, "") for _ in range(40)]
                    for line in head:
                        m = fm_tag_re.match(line.strip())
                        if m:
                            raw = m.group(1).strip("[]").strip()
                            for t in re.split(r"[,，;；]\s*", raw):
                                t = t.strip().strip('"').strip("'")
                                if t:
                                    tag_counts[t] += 1
                            break
                except OSError:
                    pass
            elif ext == ".pdf":
                pdf_files.append({"path": r, "size": size})
            elif ext == ".txt":
                txt_files.append({"path": r, "size": size,
                                  "is_transcript": bool(TRANSCRIPT_RE.search(fn)),
                                  "in_minutes": "妙记" in full})
            elif ext == ".srt":
                srt_files.append({"path": r, "size": size})
            elif ext in TEXT_READABLE_EXT:
                # .vtt/.ass/.html/.htm/.rtf：登记并受 C14 保护；doc_map 本批仍只吃 .md，不解析它们
                readable_other.append({"path": r, "size": size})
            elif ext in NEEDS_CONVERT_EXT:
                # .pdf 在上面已走既有 pdf_files / orphan_pdfs 路径，这里只收 docx/epub/odt
                needs_convert.append({"path": r, "size": size})
            elif ext in IMG_EXT:
                images.append({"path": r, "size": size})
            elif ext in VIDEO_EXT:
                videos.append({"path": r, "size": size})
            elif ext in ARCHIVE_EXT:
                archives.append({"path": r, "size": size})
            elif ext in EXEC_EXT:
                execs.append({"path": r, "size": size})
            else:
                others.append({"path": r, "size": size, "ext": ext})

    # ---- 配对检测 ----
    md_index = {m["path"]: m for m in md_files if not m["is_essence"]}
    def change_ext(path, newext):
        return re.sub(r"\.[^.]+$", newext, path)

    orphan_pdfs = []
    for p in pdf_files:
        md_path = change_ext(p["path"], ".md")
        if md_path not in md_index:
            orphan_pdfs.append(p["path"])

    minutes = []
    for t in txt_files:
        if not (t["in_minutes"] or t["is_transcript"]):
            continue
        full = os.path.join(root, t["path"])
        ess = rel(essence_candidate(full), root)
        srt = change_ext(t["path"], ".srt")
        minutes.append({
            "txt": t["path"],
            "is_transcript": t["is_transcript"],
            "essence": ess if any(m["path"] == ess for m in md_files) else None,
            "srt": srt if any(s["path"] == srt for s in srt_files) else None,
        })

    orphan_srts = []
    for s in srt_files:
        txt_path = change_ext(s["path"], ".txt")
        if not any(t["path"] == txt_path for t in txt_files):
            orphan_srts.append(s["path"])

    # ---- 源目录自带分类清单 ----
    csv_tag_counts = Counter()
    csv_rows = 0
    for candidate in [
        os.path.join(root, "00_索引·规范·日志", "主题分类清单.csv"),
    ]:
        if os.path.isfile(candidate):
            with open(candidate, "r", encoding="utf-8", errors="ignore", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    csv_rows += 1
                    for t in re.split(r"[;；]\s*", (row.get("主题") or "")):
                        t = t.strip()
                        if t:
                            csv_tag_counts[t] += 1
            break

    manifest = {
        "source_root": os.path.abspath(root),
        "scanned_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "totals": {
            "files": sum(by_ext.values()),
            "by_extension": dict(by_ext.most_common()),
            "other_readable": len(readable_other),
            "needs_convert_incl_pdf": len(needs_convert) + len(pdf_files),
        },
        "documents": {
            "md": md_files,
            "pdf": pdf_files,
            "txt": txt_files,
            "srt": srt_files,
            # 下面两键是 A4 新增；四个老键一字未动（tag_documents / build_profile 在读它们）
            "other_readable": sorted(readable_other, key=lambda x: x["path"]),
            "needs_convert": sorted(needs_convert, key=lambda x: x["path"]),
        },
        "media": {
            "images_count": len(images),
            "images_size": sum(i["size"] for i in images),
            "videos": videos,
            "archives": archives,
            "executables": execs,
            "others": others,
        },
        "pairing": {
            "orphan_pdfs": orphan_pdfs,
            "minutes": minutes,
            "essenceless_minutes": [m["txt"] for m in minutes if not m["essence"]],
            "orphan_srts": orphan_srts,
        },
        "tag_baseline": {
            "from_frontmatter": dict(tag_counts.most_common()),
            "from_classification_csv": dict(csv_tag_counts.most_common()),
            "csv_rows": csv_rows,
        },
    }
    return manifest


def main():
    ap = argparse.ArgumentParser(description="只读扫描源资料目录")
    ap.add_argument("--source", required=True, help="源资料目录")
    ap.add_argument("--out", required=True, help="manifest 输出 JSON 路径")
    args = ap.parse_args()

    if not os.path.isdir(args.source):
        raise SystemExit(f"源目录不存在或不可读：{args.source}")

    manifest = scan(args.source)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    t = manifest["totals"]
    p = manifest["pairing"]
    print(f"[scan] 文件总数={t['files']}")
    print(f"[scan] md={len(manifest['documents']['md'])} "
          f"pdf={len(manifest['documents']['pdf'])} "
          f"txt={len(manifest['documents']['txt'])} "
          f"srt={len(manifest['documents']['srt'])}")
    print(f"[scan] 孤儿PDF={len(p['orphan_pdfs'])} "
          f"无精华妙记={len(p['essenceless_minutes'])} "
          f"孤儿srt={len(p['orphan_srts'])}")
    print(f"[scan] 可直读其他={t['other_readable']} "
          f"需转换={t['needs_convert_incl_pdf']}（含 PDF；documents.needs_convert 只列 docx/epub/odt）"
          f"｜两档都只登记，深抽仍只吃 .md")

    # —— 把"有多少资料根本不入库"量化出来。以前只有上面那句一语带过，
    #    用户扫完不知道自己一半资料其实永远进不了库，跑到 Step 7 才发现。
    # 取值一律 .get 兜底：P12-src 的负控会把 manifest 还原成"A4 之前"的副本
    # （other_readable / needs_convert 两键不存在），直接下标取值会让旧副本 KeyError，
    # 负控就不是"旧口径跑不通"而是"脚本崩了"——断言会误判。
    def _n(v):
        return v if isinstance(v, int) else len(v or [])

    docs = manifest["documents"]
    media = manifest.get("media", {})
    md_n = len(docs.get("md", []))
    non_md = (_n(docs.get("pdf", [])) + _n(docs.get("txt", [])) + _n(docs.get("srt", []))
              + _n(docs.get("other_readable", [])) + _n(docs.get("needs_convert", [])))
    media_n = (_n(media.get("images_count", 0)) + _n(media.get("videos", []))
               + _n(media.get("archives", [])) + _n(media.get("executables", []))
               + _n(media.get("others", [])))
    if non_md or media_n:
        print(f"[scan] ⚠ 不进深抽：非 md 文档 {non_md} 篇 + 媒体 {media_n} 个"
              f" —— doc_map 只吃 .md，这些内容不会被抽成笔记；"
              f"要入库须先转成 .md 再走 intake")
    nc = docs.get("needs_convert", [])
    if nc:
        # needs_convert 的项是 {"path":…, "size":…} 的 dict，不是裸路径字符串
        nc_paths = [x.get("path") if isinstance(x, dict) else x for x in nc]
        exts = sorted({os.path.splitext(p)[1].lower() for p in nc_paths if p})
        print(f"[scan] 其中可转 {len(nc)} 篇（{'/'.join(exts)}）：装依赖后跑 "
              f"convert_sources.py 可转成 md；不装则这 {len(nc)} 篇只登记、不入库")
    print(f"[scan] 可深抽的 .md 共 {md_n} 篇"
          f"（注意：小于 200 字节的 .md 会被 doc_map 当作目录/标题跳过）")
    print(f"[scan] 已写出：{args.out}")


if __name__ == "__main__":
    main()
