#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_topics.py — 内容主题层聚合（层1）。

扫 notes/ 下笔记 frontmatter 的 topics 字段（内容主题，AI 粗标、人工确认），
聚合成 _meta/topics.json，并渲染 00_导航/主题地图.md。

注意：topics 是「内容讲了哪几件事」，区别于六维属性标签（domains/tools/...）；
主题是生长式的，不在受控词表里；summary/open_questions/key_units 由人工或 AI 补充。
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

FRONT_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
# 笔记目录口径与 search_index.DEFAULT_NOTES_DIR / build_flows / verify / audit 统一（默认 工作流）。
# 口径只在这里写一次：优先取 search_index 的常量，取不到才回退，避免两处各写一份漂移。
try:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import search_index as _si
    DEFAULT_NOTES_DIR = getattr(_si, "DEFAULT_NOTES_DIR", None)   # 属性改名 → None，不拿字面量顶
except Exception:  # pragma: no cover
    # 兜底不产出可用目录名（P12-fb）：这里曾写死「工作流」，一旦 import 失败就会扫错目录、
    # 把已有的 topics.json 与主题地图覆盖成空还 exit 0（本节下方注释记过这起事故）。
    DEFAULT_NOTES_DIR = None
# topic_policy（与 taxonomy.json 一致的默认值）
MIN_TOPIC_LEN = 2
MAX_PER_DOC = 5
MERGE_SUGGEST_DOCS = 3


def parse_list(v):
    v = (v or "").strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1]
    return [x.strip().strip('"').strip("'") for x in re.split(r"[,，]", v) if x.strip()]


def _q(v):
    """剥**成对**的首尾引号再 strip：只认 `"..."` 与 `'...'`，单侧或不配对一律不动。
       YAML 写 `stage: "3_搭建与开发"` 时引号会连进值里，`endswith`/`==` 直接比就误红（乙批 B5）。
       只剥一层、不递归；半截引号**不额外造语法校验**（按裁决接受这个边界）。"""
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("\"", "'"):
        return v[1:-1].strip()
    return v


def parse_frontmatter(text):
    m = FRONT_RE.match(text)
    if not m:
        return None
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = _q(v)
    return fm


def collect(kb, notes_dir):
    root = os.path.join(kb, notes_dir)
    topic_docs = defaultdict(list)
    title_map = {}
    too_many_topics = []
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".md"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, kb).replace("\\", "/")
            with open(full, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
            fm = parse_frontmatter(text)
            if not fm:
                continue
            title_map[rel] = fm.get("title", os.path.splitext(fn)[0])
            # 过滤过短主题；记录每篇超量告警
            tlist = [t for t in parse_list(fm.get("topics", ""))
                     if len(t) >= MIN_TOPIC_LEN]
            if len(tlist) > MAX_PER_DOC:
                too_many_topics.append(rel)
            for t in tlist:
                topic_docs[t].append(rel)
    return topic_docs, title_map, too_many_topics


def render_map(topic_docs, title_map):
    lines = ["# 主题地图", "",
             "> 由 build_topics.py 按笔记 frontmatter 的 topics 自动聚合；",
             "> 每个主题下列出相关笔记。主题归并/别名/摘要由人工确认后补充到 topics.json。", ""]
    for topic in sorted(topic_docs, key=lambda t: -len(topic_docs[t])):
        docs = sorted(set(topic_docs[topic]))
        lines.append(f"## {topic}（{len(docs)} 篇）")
        for d in docs:
            lines.append(f"- [[{os.path.splitext(os.path.basename(d))[0]}]]  "
                         f"<sub>{title_map.get(d, '')}</sub>")
        lines.append("")
    if not topic_docs:
        lines.append("（暂无主题标注：在笔记 frontmatter 的 topics 中填写 1-5 个内容主题。）")
    return "\n".join(lines) + "\n"


def main():
    if DEFAULT_NOTES_DIR is None:
        # 在 argparse 之前停：既不把 None 当默认目录去 join，也不让 --help 打出"默认 None"（P12-fb）
        raise SystemExit("[topics] 无法确定笔记目录口径（search_index 导入失败）")
    ap = argparse.ArgumentParser(description="聚合内容主题层")
    ap.add_argument("--kb", required=True)
    ap.add_argument("--notes", default=DEFAULT_NOTES_DIR,
                    help="笔记目录（相对 KB 根，默认 %s；口径同 build/build_flows/verify/audit）"
                         % DEFAULT_NOTES_DIR)
    ap.add_argument("--out-map", default="00_导航/主题地图.md")
    args = ap.parse_args()

    # —— 守卫（口径同 search_index cmd_build）：宁可不写，也不写出空主题层 ——
    # 这两条不加的后果很实在：默认值一度是 `notes`，照 SKILL.md 原样跑 `--kb <KB>` 会扫到空目录，
    # 然后把**已有的** topics.json 与 主题地图 覆盖成空、还 exit 0，最后由 verify C13 才暴露。
    notes_abs = os.path.join(args.kb, args.notes)
    if not os.path.isdir(notes_abs):
        raise SystemExit(f"[topics] 笔记目录不存在：{notes_abs}"
                         f"（默认 --notes {DEFAULT_NOTES_DIR}；旧库请显式 --notes notes）")
    topic_docs, title_map, too_many = collect(args.kb, args.notes)
    if not title_map:
        raise SystemExit(f"[topics] {notes_abs} 下没有可解析笔记（0 篇）——"
                         f"拒绝写出空主题层（那会清空已有的 topics.json / 主题地图），"
                         f"请检查笔记目录与 frontmatter。")
    # 同名/近义主题累计 >= 阈值 → 归并候选（人工确认，不自动合并）
    merge_candidates = [t for t, d in topic_docs.items()
                       if len(set(d)) >= MERGE_SUGGEST_DOCS]
    topics = [{"name": t, "docs": sorted(set(d)), "doc_count": len(set(d)),
               "summary": "", "open_questions": []}
              for t, d in sorted(topic_docs.items(), key=lambda x: -len(x[1]))]
    data = {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "note": "summary/open_questions 由人工或 AI 补；主题是内容层，区别于六维属性标签。",
            "policy": {"min_len": MIN_TOPIC_LEN, "max_per_doc": MAX_PER_DOC,
                       "merge_suggest_docs": MERGE_SUGGEST_DOCS},
            "warnings": {"too_many_topics": too_many,
                         "merge_candidates": merge_candidates},
            "topics": topics}

    meta = os.path.join(args.kb, "_meta")
    os.makedirs(meta, exist_ok=True)
    topics_path = os.path.join(meta, "topics.json")
    with open(topics_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)

    map_path = os.path.join(args.kb, args.out_map.replace("/", os.sep))
    os.makedirs(os.path.dirname(map_path), exist_ok=True)
    with open(map_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_map(topic_docs, title_map))

    print(f"[topics] {len(topics)} 个内容主题；笔记 {len(title_map)} 篇")
    if too_many:
        print(f"[topics][warn] {len(too_many)} 篇主题数 >{MAX_PER_DOC}：{too_many[:5]}")
    if merge_candidates:
        print(f"[topics][建议] {len(merge_candidates)} 个主题跨 >=3 篇，可人工归并：{merge_candidates[:5]}")
    for t in topics[:10]:
        print(f"  · {t['name']} ({t['doc_count']} 篇)")
    print(f"[topics] → {topics_path}")
    print(f"[topics] → {map_path}")


if __name__ == "__main__":
    main()
