#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_hooks：q_hooks schema 校验（只读）—— 录入侧的「问法质检」。

定位（详见 references/06_retrieval.md 第 8 节）：

  - **生成者是深抽时的执行 AI，不是脚本**。脚本只校验，不生成内容。
  - 本脚本**不写笔记**：唯一可能的写动作是 `--warn-log` 指定的降级日志（append jsonl），
    默认不写。不合格的处置由 AI 执行（把该笔记 `q_hooks` 置空 `[]` 重落盘）——
    脚本对笔记零写入权，与 verify / audit 的只读边界一致。
  - **不给放宽开关**：条数与长度阈值写死在常量里，不暴露 `--min-len` 这类参数，
    避免「为了让校验通过而放宽质量红线」。

与相邻工具的分工：

  - `verify.py`      ：整库 PASS/FAIL 门禁。
  - `audit.py`       ：分布诊断（A3 只报 q_hooks **覆盖率**，不看内容）。
  - `check_hooks.py` ：只查 q_hooks 的**内容合规**（数组形态 / 条数 / 长度 / 去重 / 换行）。

为什么读 raw frontmatter：`search_index.parse_frontmatter` 会把 `q_hooks: a, b` 这类
**非数组写法**按逗号静默 split 成列表（检索侧宽容是有意的，见 06 第 8 节）。校验侧要判
「模型没按数组输出」，就必须看原文，不能看归一化结果。

退出码：
  0 = 无 `invalid`（`missing` / `empty` 是「待生成」信号，不算失败——降级允许空数组，
      且存量笔记按 06 第 8 节「缺失或为空数组时一切照旧」不迁移）
  1 = 存在 `invalid`
  2 = 用法错误

硬边界：只读笔记；零新依赖（只用标准库）；可复跑（两次运行 stdout 逐字节一致）；空库 exit 0。
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
from search_index import AGGREGATE_PAGES, DEFAULT_NOTES_DIR   # noqa: E402  单一真源（A2+A3 ⑥）：不再抄第二份字面量

CHECK_VERSION = 1

# ---- 质量阈值：写死，不暴露 CLI 开关 ----
MIN_COUNT = 3          # 每篇最少 3 条
MAX_COUNT = 5          # 每篇最多 5 条
MIN_LEN = 6            # 每条最少 6 字
MAX_LEN = 40           # 每条最多 40 字

DEFAULT_WARN_LOG = os.path.join("_meta", "logs", "q_hooks_warnings.jsonl")

FRONT_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
KEY_RE = re.compile(r"^q_hooks\s*:(.*)$")
ITEM_RE = re.compile(r"^\s+-\s*(.*)$")

# 标点/空白归一（用于「仅标点差异」判重）
_PUNCT_RE = re.compile(r"[\s,，。、；;：:！!？?“”\"'（）()\[\]【】《》〈〉…—\-~·]+")


# ---------------------------------------------------------------- 解析（只读）
def norm_for_dup(s):
    """判重归一：去掉标点与空白后比较，命中即「仅标点差异」。"""
    return _PUNCT_RE.sub("", s)


def char_len(s):
    """长度口径：`strip()` 后的 Unicode 字符数。中英文均按 1 字计，不折算英文单词。"""
    return len(s.strip())


def read_q_hooks_raw(text):
    """从 raw frontmatter 读 q_hooks，返回 (form, items, note)。

    form：
      - ``"missing"`` 无该键
      - ``"inline"``  内联写法（``q_hooks: [a, b]`` 或 ``q_hooks: a, b``）
      - ``"block"``   块列表写法（``q_hooks:`` 换行后 ``  - 值``）
    items：原始字符串列表（未去重、未过滤）；note：形态异常时的说明。
    """
    m = FRONT_RE.match(text)
    if not m:
        return "missing", [], "无 frontmatter"
    lines = m.group(1).split("\n")
    for i, ln in enumerate(lines):
        km = KEY_RE.match(ln)
        if not km:
            continue
        val = km.group(1).strip()
        if val.startswith("#"):          # 模板里 `q_hooks:   # 注释` 的写法
            val = ""
        if val:
            if val.startswith("[") and val.endswith("]"):
                body = val[1:-1].strip()
                if not body:
                    return "inline", [], ""
                items = [x.strip().strip('"').strip("'") for x in re.split(r"[,，]", body)]
                return "inline", items, ""
            return "inline", [val], "not_array"      # 自由文本，非数组
        items, j = [], i + 1
        while j < len(lines):
            im = ITEM_RE.match(lines[j])
            if im:
                items.append(im.group(1).strip())
            elif lines[j].strip() and not lines[j].startswith((" ", "\t")):
                break
            j += 1
        return "block", items, ""
    return "missing", [], ""


def validate_items(items):
    """纯规则引擎：给一组 hook 字符串，返回 (signals, invalids)。

    `check_note`（校验已有笔记）与 `backfill_hooks.py`（校验待写入的候选）**共用这一个实现**，
    避免两套校验漂移。规则见 references/06_retrieval.md 第 8.2 节。
    """
    if not items:
        return ["empty"], []

    invalids = []
    clean = []
    for it in items:
        if it.startswith("{") or it.startswith("[") or ("text" in it and ":" in it):
            invalids.append({"code": "not_string", "detail": "条目不是纯字符串：%s" % it[:40]})
            continue
        if not it.strip():
            invalids.append({"code": "empty_item", "detail": "存在空条目"})
            continue
        if "," in it or "，" in it:
            # 逗号是内联写法 `[a, b]` 的分隔符：hook 里带逗号会在内联写法下被静默切成两条。
            # 规约要求 hook 内不得出现逗号，两种写法口径统一（块列表写法下本条可命中）。
            # **发现 15 登记**：这是为 YAML 兼容性做的**格式取舍，不是语义真理**，已记为**可放宽项**
            # （下一轮可做「强制 block 语法 + 允许条目内逗号」）。规约见 `08` §3.5 第 6 条注、
            # 原因码表见 `06` 第 8.2 节。**本轮不改这条判据的行为**，只把"它可以被放宽"写在刀口上。
            invalids.append({"code": "comma_in_item",
                             "detail": "条目内含逗号（内联写法下会被切成两条）：%s" % it[:40]})
            continue
        clean.append(it)

    n = len(items)
    if n < MIN_COUNT:
        invalids.append({"code": "too_few", "detail": "%d 条 < %d 条" % (n, MIN_COUNT)})
    if n > MAX_COUNT:
        invalids.append({"code": "too_many", "detail": "%d 条 > %d 条" % (n, MAX_COUNT)})

    for it in clean:
        L = char_len(it)
        if L < MIN_LEN:
            invalids.append({"code": "too_short",
                             "detail": "%d 字 < %d 字：%s" % (L, MIN_LEN, it)})
        elif L > MAX_LEN:
            invalids.append({"code": "too_long",
                             "detail": "%d 字 > %d 字：%s" % (L, MAX_LEN, it[:20])})
        if "\n" in it or "\r" in it or "\\n" in it or "\\r" in it:
            # 真换行在行式 frontmatter 解析下不可达（防御性保留）；可命中的是模型把 JSON 的
            # 转义序列原样写进 YAML 的情形——字面 `\n` 会被当成 hook 内容进索引。
            invalids.append({"code": "newline", "detail": "条目含换行/换行转义：%s" % it[:20]})

    seen = {}
    for it in clean:
        k = norm_for_dup(it)
        if not k:
            continue
        if k in seen:
            invalids.append({"code": "dup",
                             "detail": "与「%s」重复（完全相同或仅标点差异）：%s"
                                       % (seen[k], it)})
        else:
            seen[k] = it
    return [], invalids


def check_note(rel, text):
    """校验一篇**笔记文件**的 q_hooks，返回 (signals, invalids)。"""
    form, items, note = read_q_hooks_raw(text)
    if form == "missing":
        return ["missing"], []
    if note == "not_array":
        return [], [{"code": "not_array",
                     "detail": "q_hooks 不是数组写法（自由文本/字符串），应为块列表或 [..]"}]
    return validate_items(items)


def scan(notes_dir, kb):
    """扫笔记目录，口径与 audit / build 一致：只数 .md、跳过 `_` 前缀聚合页。"""
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
            out.append((rel, text))
    out.sort(key=lambda x: x[0])
    return out


# ---------------------------------------------------------------- 报告
def render_markdown(rep, kb_explicit=False):
    L = []
    L.append("# q_hooks 校验报告\n")
    L.append("- 笔记目录：`%s`（%s）"
             % (rep["notes_dir"],
                "KB 根取其父目录" if not kb_explicit
                else "KB 根由 --kb 显式给出：`%s`" % rep["kb_root"]))
    L.append("- 笔记 %d 篇；**不合格 %d 篇**；待生成（缺失/空）%d 篇"
             % (rep["notes_total"], rep["invalid_notes"], rep["signal_notes"]))
    L.append("- 口径：条数 %d–%d、每条 %d–%d 字、去重（含仅标点差异）、不含换行；"
             "**角度覆盖不硬判**（靠深抽规约约束）"
             % (MIN_COUNT, MAX_COUNT, MIN_LEN, MAX_LEN))
    L.append("- 本脚本只校验，**不生成、不写笔记**；不合格的置空由深抽 AI 执行\n")

    if rep["invalid_notes"]:
        L.append("## 不合格（必须处置）\n")
        L.append("| doc_id | 原因码 | 明细 |")
        L.append("| --- | --- | --- |")
        for r in rep["invalid"]:
            for v in r["issues"]:
                L.append("| `%s` | `%s` | %s |" % (r["doc_id"], v["code"], v["detail"]))
        L.append("")
    else:
        L.append("## 不合格\n\n无。\n")

    if rep["signal_notes"]:
        L.append("## 待生成（缺失 / 空数组）\n")
        L.append("| doc_id | 形态 |")
        L.append("| --- | --- |")
        for r in rep["signals"]:
            L.append("| `%s` | `%s` |" % (r["doc_id"], r["code"]))
        L.append("")
        L.append("> 缺失/空数组**不算失败**（降级允许空数组；存量笔记不迁移）。"
                 "刚深抽完仍为空 → 按规约补生成一次。\n")

    L.append("## 原因码统计\n")
    L.append("| 原因码 | 篇数 |")
    L.append("| --- | --- |")
    if rep["code_counts"]:
        for k in sorted(rep["code_counts"]):
            L.append("| `%s` | %d |" % (k, rep["code_counts"][k]))
    else:
        L.append("| — | 0 |")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(
        description="q_hooks schema 校验（只读；不生成、不写笔记）")
    ap.add_argument("--notes-dir", default=DEFAULT_NOTES_DIR,
                    help="笔记目录本身（默认 %s）；KB 根取其父目录，或用 --kb 显式给出" % DEFAULT_NOTES_DIR)
    ap.add_argument("--kb", default=None,
                    help="KB 根；缺省＝笔记目录的父目录（嵌套布局如 kb/content/notes 时显式给出）")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    ap.add_argument("--warn-log", default=None,
                    help="降级日志路径（append jsonl，每行一条 invalid：doc_id + 原因）；"
                         "默认不写。这是本脚本唯一的写动作，且不写笔记")
    args = ap.parse_args()

    notes_dir = args.notes_dir
    kb = os.path.abspath(args.kb) if args.kb else (os.path.dirname(os.path.abspath(notes_dir)) or ".")
    if not os.path.isdir(notes_dir):
        # 空库 / 目录不存在：输出空分布，exit 0（与 audit 一致）
        pass

    notes = scan(notes_dir, kb)
    invalid, signals, code_counts = [], [], {}
    for rel, text in notes:
        sig, inv = check_note(rel, text)
        if sig:
            signals.append({"doc_id": rel, "code": sig[0]})
            code_counts[sig[0]] = code_counts.get(sig[0], 0) + 1
        if inv:
            invalid.append({"doc_id": rel, "issues": inv})
            for v in inv:
                code_counts[v["code"]] = code_counts.get(v["code"], 0) + 1

    rep = {
        "check_version": CHECK_VERSION,
        "notes_dir": notes_dir,
        "kb_root": kb,
        "notes_total": len(notes),
        "thresholds": {"min_count": MIN_COUNT, "max_count": MAX_COUNT,
                       "min_len": MIN_LEN, "max_len": MAX_LEN},
        "invalid_notes": len(invalid),
        "signal_notes": len(signals),
        "invalid": invalid,
        "signals": signals,
        "code_counts": code_counts,
    }

    if args.format == "json":
        out = json.dumps(rep, ensure_ascii=False, indent=2, sort_keys=True)
    else:
        out = render_markdown(rep, bool(args.kb))
    sys.stdout.write(out + "\n")

    if args.warn_log and invalid:
        logp = args.warn_log
        d = os.path.dirname(logp)
        if d:
            os.makedirs(d, exist_ok=True)
        with io.open(logp, "a", encoding="utf-8", newline="\n") as fh:
            for r in invalid:
                for v in r["issues"]:
                    fh.write(json.dumps({"doc_id": r["doc_id"], "code": v["code"],
                                         "detail": v["detail"], "notes_dir": notes_dir},
                                        ensure_ascii=False, sort_keys=True) + "\n")

    return 1 if invalid else 0


if __name__ == "__main__":
    sys.exit(main())
