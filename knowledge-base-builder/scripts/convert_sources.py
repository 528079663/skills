#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""convert_sources.py —— 把 `needs_convert` 的二进制正文（docx/epub/odt）转成 Markdown，
让"登记了但抽不了"那格（发现 32）走通。**只写 `_meta/converted/`，源目录一字不动。**

契约（写死，勿改口径）：
  · 转换产物是**派生物**，与 `doc_maps.jsonl` / `search.db` 同级，可删可重建；
  · 产物路径以 `<kb>/_meta/converted/` 为**第二个源根**：笔记的 `sources` 写
    `_meta/converted/<相对路径>.md`（C5 认 `<kb>/<rel>` 这个基准），
    定位符（char 区间）也对**产物**计算，不是对原 docx 计算；
  · 产物**必须确定性**：同样输入两次转换 → 逐字节相同（头部注释不含时间戳；
    时间/unstructured 版本记在 `_meta/converted/_manifest.json` 边车里）。
  · 解析层用 Unstructured 的**显式分区器**（按扩展名分派），`magic` 只当"扩展名与真实
    类型不符"的兜底核验，且核验放在**子进程**里跑（本机实测 `magic` 载不到 DLL 时是
    native access violation，进程内 try/except 抓不住）。
  · 缺依赖 → **rc≠0 ＋ stderr 点名缺哪个包**，不静默跳过；
    `.pdf` 本轮明确不接（还要 poppler 外部二进制），计入"跳过"并大声打印。
"""
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_sources import NEEDS_CONVERT_EXT          # 单一真源：哪些扩展名属"必须先转换"

DISPATCH = {".docx": ("docx", "unstructured.partition.docx", "partition_docx", "python-docx"),
            ".epub": ("epub", "unstructured.partition.epub", "partition_epub", "pypandoc-binary"),
            ".odt": ("odt", "unstructured.partition.odt", "partition_odt", "pypandoc-binary（**本库未验证**）")}
HEADER = "<!-- 派生物：由 %s 转换而来｜源 sha256 %s｜勿手改，可重生成 -->\n"


def die(msg, code=1):
    sys.stderr.write("[convert] %s\n" % msg)
    raise SystemExit(code)


def sha12(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(65536), b""):
            h.update(blk)
    return h.hexdigest()[:12]


def list_candidates(source_root, formats, only):
    # `.pdf` 永远进候选集：它由调用方分流成「跳过（本轮不接）」并**点名**。
    # 若让它跟着 --formats 走，默认 docx,epub,odt 会把库里的 pdf 静默吞掉——一句都不报。
    exts = {e for e in NEEDS_CONVERT_EXT if e in formats} | {".pdf"}
    out = []
    for dirpath, dirnames, files in os.walk(source_root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in sorted(files):
            ext = os.path.splitext(fn)[1].lower()
            if ext not in exts:
                continue
            rel = os.path.relpath(os.path.join(dirpath, fn), source_root).replace("\\", "/")
            out.append((rel, os.path.join(dirpath, fn), ext))
    if only:
        keep = {x.strip().replace("\\", "/") for x in only.split(",") if x.strip()}
        out = [x for x in out if x[0] in keep or os.path.basename(x[0]) in keep]
    return out


def detect_type_child(path):
    """在子进程里跑 magic 的 detect_filetype：本机实测 magic 载不到 DLL 会 native crash，
       进程内抓不住，所以宁可让子进程崩、父进程按"兜底核验不可用"处理。"""
    code = ("import sys, json\n"
            "from unstructured.file_utils.filetype import detect_filetype\n"
            "print(json.dumps(str(detect_filetype(sys.argv[1]).name)))\n")
    try:
        p = subprocess.run([sys.executable, "-c", code, path], capture_output=True,
                           text=True, encoding="utf-8", timeout=60)
    except Exception:
        return None
    if p.returncode != 0:
        return None
    m = re.search(r'"([A-Za-z0-9_]+)"', p.stdout or "")
    return m.group(1) if m else None


def partition_explicit(ext, path):
    mod, fn, need = DISPATCH[ext][1], DISPATCH[ext][2], DISPATCH[ext][3]
    try:
        import importlib
        m = importlib.import_module(mod)
        part = getattr(m, fn)
    except ImportError as e:
        die("缺依赖：%s 不可导入（%s）→ 这份文件没转。装法：pip install \"%s\"\n"
            "        （缺依赖不静默跳过：本脚本就此 rc≠0）" % (mod, e, need), 3)
    els = part(filename=path)
    texts, kinds = [], {}
    for e in els:
        t = str(e).strip()
        if not t:
            continue
        kinds[type(e).__name__] = kinds.get(type(e).__name__, 0) + 1
        texts.append(t)
    return "\n\n".join(texts) + "\n", kinds


def main():
    ap = argparse.ArgumentParser(description="needs_convert 二进制正文 → Markdown（只写 _meta/converted/）")
    ap.add_argument("--kb", required=True, help="知识库根（产物写到 <kb>/_meta/converted/）")
    ap.add_argument("--source-root", required=True, help="源资料根（登记 needs_convert 的那个根）")
    ap.add_argument("--only", default=None, help="逗号分隔，只做这些文件（按相对路径或文件名匹配）")
    ap.add_argument("--formats", default="docx,epub,odt",
                    help="本次允许转换的扩展名（pdf 本轮不接；默认 docx,epub,odt）")
    ap.add_argument("--dry-run", action="store_true", help="只报计划，零写盘")
    ap.add_argument("--no-doc-map", action="store_true", help="转完不调 doc_map --append")
    args = ap.parse_args()

    kb = os.path.abspath(args.kb)
    src_root = os.path.abspath(args.source_root)
    conv_root = os.path.join(kb, "_meta", "converted")
    # 守卫①：源根不得在 kb 内（否则 _meta/converted 会被自己再扫一遍，无限套娃）
    if src_root == kb or src_root.startswith(kb + os.sep):
        die("守卫①拒绝：--source-root 不得落在 --kb 内（防 _meta/converted 自吞再转换）。"
            "源根=%s kb=%s" % (src_root, kb))
    formats = {"." + f.strip().lstrip(".") for f in args.formats.split(",") if f.strip()}
    unknown = formats - set(DISPATCH) - {".pdf"}
    if unknown:
        die("--formats 里有不支持的项：%s（可选：docx,epub,odt；pdf 本轮不接）" % sorted(unknown))

    cands = list_candidates(src_root, formats, args.only)
    pdfs = [c for c in cands if c[2] == ".pdf"]
    todo = [c for c in cands if c[2] != ".pdf"]
    print("[convert] 待转 %d 篇｜跳过（pdf 本轮不接）%d 篇" % (len(todo), len(pdfs)))
    if pdfs:
        print("[convert] 跳过的 pdf（不是失败，是本轮明确不做）：%s"
              % ", ".join(p[0][:40] for p in pdfs[:5]))
    if not todo:
        print("[convert] 没有要转的文件，零写盘。")
        return 0
    if args.dry_run:
        for rel, _full, ext in todo:
            print("[dry-run] 将写 %s" % ("_meta/converted/" + rel + ".md"))
        print("[dry-run] 零写盘（未建目录、未调 doc_map）。")
        return 0

    try:
        from unstructured.__version__ import __version__ as uver
    except Exception:
        die("未安装 unstructured：pip install unstructured markdown python-docx pypandoc-binary"
            "（缺依赖不静默跳过，就此 rc≠0）")

    os.makedirs(conv_root, exist_ok=True)
    sidecar_path = os.path.join(conv_root, "_manifest.json")
    sidecar = {}
    if os.path.isfile(sidecar_path):
        try:
            sidecar = json.loads(io.open(sidecar_path, encoding="utf-8").read())
        except ValueError:
            sidecar = {}
    written = []
    for rel, full, ext in todo:
        want = DISPATCH[ext][0].upper()
        got = detect_type_child(full)
        if got and got != "UNKNOWN" and got != want:
            die("兜底核验不一致：%s 扩展名说 %s，magic 读出 %s —— 不敢按扩展名转，停。"
                % (rel, DISPATCH[ext][0], got))
        text, kinds = partition_explicit(ext, full)
        dst = os.path.join(conv_root, rel + ".md")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        body = HEADER % (rel, sha12(full)) + text
        io.open(dst, "w", encoding="utf-8", newline="\n").write(body)
        written.append(rel + ".md")
        sidecar[rel + ".md"] = {"source": rel, "source_sha256_12": sha12(full),
                                "converted_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "unstructured": uver, "elements": kinds,
                                "chars": len(text)}
        print("[convert] %s → _meta/converted/%s.md｜元素 %s" % (rel, rel, kinds))
    io.open(sidecar_path, "w", encoding="utf-8", newline="\n").write(
        json.dumps(sidecar, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
    print("[convert] 写了 %d 篇产物（源目录未动；C14 基线不涉及）→ %s" % (len(written), conv_root))

    if not args.no_doc_map and written:
        dm = os.path.join(os.path.dirname(os.path.abspath(__file__)), "doc_map.py")
        r = subprocess.run([sys.executable, dm, "--source-root", conv_root,
                            "--out", os.path.join(kb, "_meta", "doc_maps.jsonl"), "--append"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        print((r.stdout or "").rstrip()[:400])
        if r.returncode != 0:
            die("doc_map --append 失败（rc=%d）：%s" % (r.returncode, (r.stderr or "")[:300]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
