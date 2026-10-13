#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_flows.py — 从原子笔记 frontmatter 聚合生成 _流程.md 和 _总览.md。

扫描 工作流/<flow>/<n>_<stage>/ 下的原子笔记（目录名由 `--notes` 决定，默认取
search_index.DEFAULT_NOTES_DIR＝`工作流`），读 frontmatter 的 flow/stage/substage/title，
为每个 flow 生成 _流程.md（环节顺序 + 关键 SOP），为每个 stage 生成 _总览.md（按 substage 5 组）。

每批原子笔记写完后必须重跑本脚本。
"""
import argparse
import os
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from search_index import AGGREGATE_PAGES, DEFAULT_NOTES_DIR   # 单一真源（A2+A3 ⑥）；实测无循环依赖、导入代价 +~6ms

SUBSTAGES = ["总览", "子技巧", "案例", "工具", "坑"]
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
FIELD_RE = re.compile(r"^(\w+):\s*(.+?)\s*$", re.MULTILINE)


def parse_frontmatter(text):
    """简单解析 frontmatter（不依赖 PyYAML）。"""
    m = FM_RE.match(text)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).split("\n"):
        f = FIELD_RE.match(line)
        if f:
            key, val = f.group(1), f.group(2)
            # 去掉引号和列表标记
            val = val.strip().strip('"').strip("'")
            if val.startswith("["):
                val = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",") if v.strip()]
            fm[key] = val
    return fm


def list_notes(stage_dir):
    """列出环节目录下的原子笔记（聚合页按 `AGGREGATE_PAGES` 白名单跳过，不再按 `_` 前缀豁免）。"""
    notes = []
    for fn in os.listdir(stage_dir):
        if not fn.endswith(".md") or fn in AGGREGATE_PAGES:
            continue
        path = os.path.join(stage_dir, fn)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read(2000)
        except OSError:
            continue
        fm = parse_frontmatter(text)
        title = fm.get("title", fn[:-3])
        substage = fm.get("substage", "子技巧")
        if substage not in SUBSTAGES:
            substage = "子技巧"
        notes.append({
            "file": fn,
            "title": title,
            "substage": substage,
        })
    return notes


def build_stage_overview(flow_name, stage_name, notes):
    """生成 _总览.md 内容。"""
    lines = [f"# {stage_name} · 总览", ""]
    lines.append(f"> 工作流：[[../_流程|{flow_name}]] ｜ 本环节笔记 {len(notes)} 篇")
    lines.append("")

    by_sub = defaultdict(list)
    for n in notes:
        by_sub[n["substage"]].append(n)

    for sub in SUBSTAGES:
        items = by_sub.get(sub, [])
        lines.append(f"## {sub}（{len(items)}）")
        if not items:
            lines.append("（暂无）")
        else:
            for n in sorted(items, key=lambda x: x["file"]):
                lines.append(f"- [[{n['file'][:-3]}|{n['title']}]]")
        lines.append("")

    return "\n".join(lines) + "\n"


def build_flow_overview(flow_name, stages):
    """生成 _流程.md 内容。stages 为 [(stage_name, note_count), ...]。"""
    lines = [f"# {flow_name} · 流程", ""]
    lines.append("> 本工作流的环节顺序与关键 SOP。每环节链接到其 _总览。")
    lines.append("")
    lines.append("## 环节")
    lines.append("")
    for stage_name, note_count in stages:
        stage_link = f"[[{stage_name}/_总览|{stage_name}]]"
        lines.append(f"- {stage_link}（{note_count} 篇笔记）")
    lines.append("")
    lines.append("## 关键 SOP")
    lines.append("")
    lines.append("（从各环节「总览」类笔记聚合，待 build_flows 后续版本自动提取）")
    lines.append("")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description="生成工作流 _流程.md 和环节 _总览.md")
    ap.add_argument("--kb", required=True, help="知识库根目录")
    ap.add_argument("--notes", default=DEFAULT_NOTES_DIR,
                    help="笔记目录名（相对 KB 根；默认 %s，与 build_topics/search_index 同口径）"
                         % DEFAULT_NOTES_DIR)
    args = ap.parse_args()

    flows_dir = os.path.join(args.kb, args.notes)
    if not os.path.isdir(flows_dir):
        # 输入守卫：目录都不存在不是"没活干"，而是"找错了地方"——与 progress 的
        # 「doc_maps 不存在」同性质（显式动作失败要响），所以走 stderr + 非 0 退出。
        print(f"[build_flows] 未找到 {args.notes} 目录：{flows_dir}"
              f"（笔记目录不叫这个名时用 --notes <相对 KB 根的名字>）", file=sys.stderr)
        return 1
        return

    n_flows = n_stages = n_notes = 0
    for flow_name in sorted(os.listdir(flows_dir)):
        flow_dir = os.path.join(flows_dir, flow_name)
        if not os.path.isdir(flow_dir):
            continue
        n_flows += 1

        def _stage_sort_key(name):
            # 按目录名开头的数字前缀排序；无数字的排最后
            m = re.match(r"^(\d+)_", name)
            return (0, int(m.group(1))) if m else (1, name)

        stages_info = []
        for stage_name in sorted(os.listdir(flow_dir), key=_stage_sort_key):
            stage_dir = os.path.join(flow_dir, stage_name)
            # 这里跳的是 `_` 开头的**环节目录**（如 `_草稿区/`），与上面 `AGGREGATE_PAGES`（文件名白名单）
            # 语义不同，**不并进来**：目录没有"固定名单"可依，按前缀跳是刻意的。
            if not os.path.isdir(stage_dir) or stage_name.startswith("_"):
                continue

            notes = list_notes(stage_dir)
            n_notes += len(notes)
            n_stages += 1
            stages_info.append((stage_name, len(notes)))

            # 写 _总览.md
            overview_path = os.path.join(stage_dir, "_总览.md")
            content = build_stage_overview(flow_name, stage_name, notes)
            with open(overview_path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)

        # 写 _流程.md
        flow_path = os.path.join(flow_dir, "_流程.md")
        content = build_flow_overview(flow_name, stages_info)
        with open(flow_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)

    print(f"[build_flows] 工作流 {n_flows} 个；环节 {n_stages} 个；原子笔记 {n_notes} 篇")
    print(f"[build_flows] 已更新所有 _流程.md 和 _总览.md")


if __name__ == "__main__":
    sys.exit(main())
