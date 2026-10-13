#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backfill_hooks：q_hooks 存量回填（只补缺，默认不覆盖）。

**生成者仍是深抽时的大模型，不是脚本。** 脚本不生成 hook 内容，只做三件事：
扫描 → 校验（复用 `check_hooks.validate_items`，不重写规则）→ 落盘。

分工（沿用本 skill 既有的「大模型出 JSON、脚本校验后执行」契约，同 `search_index recall --route-json`）：

  1. `--emit-tasks <path>`   脚本导出待补清单（doc_id + 标题 + topics + 正文），供模型消费；
  2. 模型按 `references/08_topics_pipeline_units.md` 第 3.5 节的规约生成 hooks，
     写成 `<kb>/_meta/hooks_backfill.json`：``{"<doc_id>": ["hook1", ...], ...}``；
  3. 本脚本逐篇校验并写入。

行为：
  - 扫全库，列出 `q_hooks` 缺失或为空的笔记；
  - 已有 `q_hooks` 且非空的笔记**默认跳过**；`--force` 才纳入（这是本 skill 里唯一真实存在的覆盖开关）；
  - 校验过 → 写入笔记；不过 → 置空 `[]` + warning 到 `_meta/logs/q_hooks_warnings.jsonl`；
  - 单篇失败不影响其他篇（不阻塞）。

> ⚠️ **边界说明**：本脚本是本 skill 里**第一个会写笔记 frontmatter 的脚本**。增量路径（深抽时）
> 的置空仍由执行 AI 做；只有存量回填这条批量路径由脚本落盘，因为批量手改笔记不现实。
> 它只写 `q_hooks` 这一个字段，不动笔记的其他任何内容。

CLI：
  backfill_hooks.py [--notes-dir DIR] [--dry-run] [--force]
                    [--hooks-json PATH] [--emit-tasks PATH]

退出码：0 = 无失败；1 = 有失败（含校验不过 / 缺候选 / 写失败）；2 = 用法错误；3 = 缺 hooks JSON。
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_hooks as chk        # noqa: E402  复用同一套校验规则，不重写
from search_index import AGGREGATE_PAGES   # noqa: E402  B8 收口：聚合页认白名单不认前缀（真源在 search_index，
                                            # 实测本文件早已传递加载 search_index，这句不增加任何依赖）

BACKFILL_VERSION = 1
DEFAULT_NOTES_DIR = chk.DEFAULT_NOTES_DIR   # 沿用 check_hooks 的单一真源（A2+A3 ⑥），不另起
HOOKS_JSON_REL = os.path.join("_meta", "hooks_backfill.json")
WARN_LOG_REL = os.path.join("_meta", "logs", "q_hooks_warnings.jsonl")

TOPICS_RE = re.compile(r"^topics\s*:")


# ---------------------------------------------------------------- 扫描
def scan(notes_dir, kb):
    """返回 [(rel, full, text)]，口径同 build / check_hooks：只数 .md、跳过 `_` 前缀聚合页。"""
    out = []
    if not os.path.isdir(notes_dir):
        return out
    for dirpath, _, files in os.walk(notes_dir):
        for fn in sorted(files):
            if not fn.endswith(".md") or fn in AGGREGATE_PAGES:
                continue
            full = os.path.join(dirpath, fn)
            try:
                with io.open(full, encoding="utf-8", errors="ignore") as fh:
                    text = fh.read()
            except OSError:
                continue
            rel = os.path.relpath(full, kb).replace("\\", "/")
            out.append((rel, full, text))
    out.sort(key=lambda x: x[0])
    return out


def classify(text):
    """把一篇笔记分成 missing / invalid / ok 三类。"""
    sig, inv = chk.check_note("", text)
    if sig:
        return "missing", []
    if inv:
        return "invalid", inv
    return "ok", []


# ---------------------------------------------------------------- 写入
def _skip_block(lines, i):
    """跳过 lines[i] 之后属于该键的续行（缩进行与空行），返回下一行下标。"""
    j = i + 1
    while j < len(lines) and (not lines[j].strip() or lines[j].startswith((" ", "\t"))):
        j += 1
    return j


def set_q_hooks(text, hooks):
    """把 q_hooks 写进 frontmatter，返回新文本；无 frontmatter 返回 None。

    - 已有 `q_hooks` 键 → 整段替换（含块列表续行）；
    - 没有该键 → 插在 `topics` 之后（无 topics 则追加到 frontmatter 末尾）。
    """
    m = chk.FRONT_RE.match(text)
    if not m:
        return None
    lines = m.group(1).split("\n")
    block = (["q_hooks:"] + ["  - %s" % h for h in hooks]) if hooks else ["q_hooks: []"]

    idx = next((i for i, ln in enumerate(lines) if chk.KEY_RE.match(ln)), None)
    if idx is not None:
        new = lines[:idx] + block + lines[_skip_block(lines, idx):]
    else:
        t = next((i for i, ln in enumerate(lines) if TOPICS_RE.match(ln)), None)
        if t is not None:
            j = _skip_block(lines, t)
            new = lines[:j] + block + lines[j:]
        else:
            new = lines + block
    return text[:m.start(1)] + "\n".join(new) + text[m.end(1):]


def write_atomic(path, text):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def warn(logp, doc_id, code, detail, notes_dir):
    d = os.path.dirname(logp)
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(logp, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({"doc_id": doc_id, "code": code, "detail": detail,
                             "notes_dir": notes_dir}, ensure_ascii=False,
                            sort_keys=True) + "\n")


def get_fm_value(text, key):
    m = chk.FRONT_RE.match(text)
    if not m:
        return ""
    for ln in m.group(1).split("\n"):
        if re.match(r"^%s\s*:" % re.escape(key), ln):
            v = ln.split(":", 1)[1].strip()
            return "" if v.startswith("#") else v
    return ""


def get_body(text):
    m = chk.FRONT_RE.match(text)
    return text[m.end():] if m else text


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(
        description="q_hooks 存量回填（只补缺，默认不覆盖；脚本不生成 hook 内容）")
    ap.add_argument("--notes-dir", default=DEFAULT_NOTES_DIR,
                    help="笔记目录本身（默认 %s）；KB 根取其父目录，或用 --kb 显式给出" % DEFAULT_NOTES_DIR)
    ap.add_argument("--kb", default=None,
                    help="KB 根；缺省＝笔记目录的父目录（嵌套布局如 kb/content/notes 时显式给出）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只报告哪些笔记缺 q_hooks，不生成、不写")
    ap.add_argument("--force", action="store_true",
                    help="覆盖已有 q_hooks（默认关闭；本 skill 里唯一真实存在的覆盖开关）")
    ap.add_argument("--hooks-json", default=None,
                    help="模型生成的 hooks JSON（默认 <kb>/%s）" % HOOKS_JSON_REL)
    ap.add_argument("--emit-tasks", default=None,
                    help="导出待补清单 JSON（doc_id + 标题 + topics + 正文），供模型生成")
    args = ap.parse_args()

    notes_dir = args.notes_dir
    kb = os.path.abspath(args.kb) if args.kb else (os.path.dirname(os.path.abspath(notes_dir)) or ".")
    hooks_json = args.hooks_json or os.path.join(kb, HOOKS_JSON_REL)
    warn_log = os.path.join(kb, WARN_LOG_REL)

    notes = scan(notes_dir, kb)
    missing, invalid, ok = [], [], []
    for rel, full, text in notes:
        kind, inv = classify(text)
        (missing if kind == "missing" else invalid if kind == "invalid" else ok).append(
            {"doc_id": rel, "full": full, "text": text, "issues": inv})

    targets = missing + (invalid + ok if args.force else [])
    skipped = [] if args.force else (invalid + ok)

    L = []
    L.append("# q_hooks 存量回填\n")
    L.append("- 笔记目录：`%s`（%s）"
             % (notes_dir, "KB 根取其父目录" if not args.kb
                else "KB 根由 --kb 显式给出：`%s`" % kb))
    L.append("- 模式：%s%s" % ("--dry-run（只读）" if args.dry_run else "写入",
                              " + --force（覆盖已有）" if args.force else "（只补缺，不覆盖）"))
    L.append("")
    L.append("## 扫描结果\n")
    L.append("| 项 | 篇数 |")
    L.append("| --- | --- |")
    L.append("| 总篇数 | %d |" % len(notes))
    L.append("| 缺失 / 空（待补） | **%d** |" % len(missing))
    L.append("| 已有非空（合格） | %d |" % len(ok))
    L.append("| 已有但不合格 | %d |" % len(invalid))
    L.append("")
    if missing:
        L.append("待补清单：\n")
        for r in missing:
            L.append("- `%s`" % r["doc_id"])
        L.append("")
    if invalid:
        L.append("已有但不合格（默认跳过，`--force` 才覆盖）：\n")
        L.append("| doc_id | 原因码 |")
        L.append("| --- | --- |")
        for r in invalid:
            L.append("| `%s` | `%s` |" % (r["doc_id"], "、".join(v["code"] for v in r["issues"])))
        L.append("")

    if args.dry_run:
        L.append("> `--dry-run`：未生成、未写任何文件。")
        if args.emit_tasks:
            L.append("> ⚠️ 本次带了 `--emit-tasks`，但 `--dry-run` 优先（只读）——**未导出清单**。"
                     "要去掉 `--dry-run` 才会导出。")
        sys.stdout.write("\n".join(L) + "\n")
        return 0

    # 导出待补清单（供模型生成）
    if args.emit_tasks:
        tasks = [{"doc_id": r["doc_id"], "title": get_fm_value(r["text"], "title"),
                  "topics": get_fm_value(r["text"], "topics"), "body": get_body(r["text"])}
                 for r in targets]
        d = os.path.dirname(args.emit_tasks)
        if d:
            os.makedirs(d, exist_ok=True)
        write_atomic(args.emit_tasks, json.dumps(tasks, ensure_ascii=False, indent=2,
                                                 sort_keys=True))
        L.append("- 待补清单已导出：`%s`（%d 篇）" % (args.emit_tasks, len(tasks)))

    if not os.path.exists(hooks_json):
        L.append("")
        L.append("> ⚠️ 未找到 `%s`。backfill 的生成者是**深抽 AI**，脚本不生成内容——"
                 "请先按 `references/08_topics_pipeline_units.md` 第 3.5 节的规约生成 hooks JSON"
                 "（可用 `--emit-tasks` 导出待补清单），再重跑本命令。" % hooks_json)
        sys.stdout.write("\n".join(L) + "\n")
        return 3

    with io.open(hooks_json, encoding="utf-8") as fh:
        data = json.load(fh)

    success, failed, warn_n = [], [], 0
    for r in targets:
        doc_id, full = r["doc_id"], r["full"]
        try:
            cand = data.get(doc_id)
            if cand is None:
                cand = data.get(os.path.basename(doc_id))
            if cand is None:
                failed.append({"doc_id": doc_id, "code": "no_candidate"})
                warn(warn_log, doc_id, "no_candidate", "模型未为该笔记提供 q_hooks", notes_dir)
                warn_n += 1
                continue
            if not isinstance(cand, list):
                cand = [cand]
            cand = [str(x) for x in cand]

            _, inv = chk.validate_items(cand)
            if inv:
                new = set_q_hooks(r["text"], [])
                if new is None:
                    failed.append({"doc_id": doc_id, "code": "no_frontmatter"})
                    warn(warn_log, doc_id, "no_frontmatter", "无 frontmatter，无法写入", notes_dir)
                    warn_n += 1
                    continue
                write_atomic(full, new)
                failed.append({"doc_id": doc_id,
                               "code": "、".join(sorted({v["code"] for v in inv}))})
                for v in inv:
                    warn(warn_log, doc_id, v["code"], v["detail"], notes_dir)
                    warn_n += 1
                continue

            new = set_q_hooks(r["text"], cand)
            if new is None:
                failed.append({"doc_id": doc_id, "code": "no_frontmatter"})
                warn(warn_log, doc_id, "no_frontmatter", "无 frontmatter，无法写入", notes_dir)
                warn_n += 1
                continue
            write_atomic(full, new)
            success.append({"doc_id": doc_id, "count": len(cand)})
        except Exception as exc:                                  # noqa: BLE001
            failed.append({"doc_id": doc_id, "code": "error:%s" % type(exc).__name__})
            warn(warn_log, doc_id, "write_error", str(exc), notes_dir)
            warn_n += 1

    L.append("")
    L.append("## 执行结果\n")
    L.append("| 项 | 篇数 |")
    L.append("| --- | --- |")
    L.append("| 成功写入 | **%d** |" % len(success))
    L.append("| 失败（置空 + warning） | %d |" % len(failed))
    L.append("| 跳过（已有非空） | %d |" % len(skipped))
    L.append("| warning 条数 | %d |" % warn_n)
    L.append("")
    if success:
        L.append("| 成功写入 | 条数 |")
        L.append("| --- | --- |")
        for r in success:
            L.append("| `%s` | %d |" % (r["doc_id"], r["count"]))
        L.append("")
    if failed:
        L.append("失败明细：\n")
        L.append("| doc_id | 原因码 |")
        L.append("| --- | --- |")
        for r in failed:
            L.append("| `%s` | `%s` |" % (r["doc_id"], r["code"]))
        L.append("")
    sys.stdout.write("\n".join(L) + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
