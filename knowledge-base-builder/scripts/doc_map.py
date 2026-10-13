#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doc_map.py — 两阶段入库之「文档地图」（层2）。

深抽前，先为每篇正文产出章节地图：按标题切块、估算知识密度、标记高价值块、
给出候选主题；只对高价值块深抽，低密度块记 skip 原因。避免对几千篇逐块全量深抽。

密度为确定性启发式（代码块/数字/命令/链接加权）；每章主题与候选主题的语义判断
由执行 AI 在本地图基础上补充。coverage 里的 chunks_processed / high_value_done 是生成时的
**快照字段**（恒 0 / false），不由任何脚本回填——进度与续跑起点用 progress.py 从笔记反推。
输出 JSONL：每行一篇文档（含 chunks 与 coverage）。
"""
import argparse
import hashlib
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
# 妙记逐字稿时间戳锚点：[00:01:23] 或 00:01:23 / 01:23 开头一行
TS_RE = re.compile(r"^\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?\s*\S", re.MULTILINE)
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
LINK_RE = re.compile(r"https?://\S+")
NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
SKIP_TOP = {"tmp", "00_索引·规范·日志", ".trash", "__MACOSX"}
SKIP_NAME_KW = ["清单", "索引", "日志", "待下载", "报告", "总览", "说明"]
OVERLAP_RATIO = 0.1  # 跨标题边界保留衔接句，深抽上下文回退比例

CODE_W = 0.6
NUM_W = 0.3
CMD_W = 0.3
LINK_W = 0.1
# 非技术文档特征（课程/理论/SOP/分析），避免误判为低密度
HEADING_TERMS = ["定义", "概念", "原理", "方法", "步骤", "流程", "注意", "结论"]
CAUSAL_WORDS = ["因为", "所以", "导致", "意味着", "关键在于"]
# 可落地特征：出现"照着做"的动作词，说明这段是操作不是空话。
# 只收高信噪比的词，两条硬约束（都是实测踩出来的）：
#   ① 不放"工具""方法""认知"这类泛词——泛词会把方法论空话一起放进来；
#   ② 不放"执行""输入""打开""设置"这类中文比喻常用词——"执行力""打开认知""设置目标"
#      会让纯大道理段命中（实测"执行力决定下限"就误放进来过一次）。
ACTION_WORDS = ["命令", "步骤", "点击", "安装", "脚本", "参数",
                "复制", "粘贴", "导出", "导入", "改成", "运行"]
HEADING_W = 0.3
CAUSAL_W = 0.2
NARRATIVE_W = 0.2
ACTION_W = 0.3
NARRATIVE_LEN = 80
MIN_LEN = 50          # 低于此字数的块视为低价值（目录/纯标题）
HIGH_THRESHOLD = 0.5  # 密度加权分超此值为高价值


def is_body(path, size, source_root=None):
    """判断是否为正文 md。

    - 根目录文件（无 /）直接接受，不再硬限制必须在子目录。
    - 精华笔记：对应原文存在才跳过；原文缺失时作为 body（不能丢主题）。
    - SKIP_NAME_KW 仅小文件（<500B）才跳过，避免误伤正文标题含这些词。
    """
    if size < 200:
        return False
    parts = path.split("/")
    top = parts[0]
    if top.startswith(".") or top in SKIP_TOP:
        return False
    base = parts[-1]
    # 精华笔记：对应原文存在才跳过
    if base.endswith("·精华笔记.md"):
        if source_root:
            orig_name = base[:-len("·精华笔记.md")] + ".md"
            orig_dir = os.path.dirname(os.path.join(source_root, path))
            if os.path.exists(os.path.join(orig_dir, orig_name)):
                return False
        # 无 source_root 或原文不存在 → 作为 body
    # SKIP_NAME_KW 仅小文件才跳过
    if size < 500 and any(k in base for k in SKIP_NAME_KW):
        return False
    return True


def doc_id(path):
    return "doc-" + hashlib.md5(path.encode("utf-8")).hexdigest()[:8]


def split_chunks(text):
    """按标题或妙记时间戳切块；返回 [(heading, char_start, char_end)]。"""
    anchors = [(m.start(), m.group(2).strip()) for m in HEADING_RE.finditer(text)]
    anchors += [(m.start(), m.group(1).strip()) for m in TS_RE.finditer(text)]
    anchors.sort()
    if not anchors:
        return [("", 0, len(text))]
    chunks = []
    for i, (pos, heading) in enumerate(anchors):
        end = anchors[i + 1][0] if i + 1 < len(anchors) else len(text)
        chunks.append((heading, pos, end))
    return chunks


def chunk_density(seg, heading=""):
    features = []
    score = 0.0
    body = FENCE_RE.sub("", seg)
    if FENCE_RE.search(seg):
        score += CODE_W; features.append("code")
    if len(NUM_RE.findall(body)) >= 3:
        score += NUM_W; features.append("numbers")
    if INLINE_CODE_RE.search(body):
        score += CMD_W; features.append("cmd")
    if LINK_RE.search(body):
        score += LINK_W; features.append("link")
    # 非技术特征
    if any(t in heading for t in HEADING_TERMS):
        score += HEADING_W; features.append("concept_heading")
    if any(w in body for w in CAUSAL_WORDS):
        score += CAUSAL_W; features.append("causal")
    if any(w in body for w in ACTION_WORDS):
        score += ACTION_W; features.append("actionable")
    if any(len(p.strip()) >= NARRATIVE_LEN
           for p in re.split(r"\n\s*\n", body)):
        score += NARRATIVE_W; features.append("narrative")
    return score, features


def candidate_topics(heading):
    h = re.sub(r"[|\*#\[\]()（）:：]", "", heading).strip()
    return [h] if 2 <= len(h) <= 20 else []


def map_one(path, text):
    chunks = []
    for i, (heading, start, end) in enumerate(split_chunks(text)):
        seg = text[start:end]
        length = end - start
        score, features = chunk_density(seg, heading)
        high = length >= MIN_LEN and (score >= HIGH_THRESHOLD or "code" in features)
        overlap_start = max(0, start - int(length * OVERLAP_RATIO))
        chunks.append({
            "chunk_id": f"{doc_id(path)}-{i}",
            "heading": heading,
            "char_start": start, "char_end": end, "char_len": length,
            "overlap_start": overlap_start,
            "features": features, "density": round(score, 2),
            "high_value": high,
            "candidate_topics": candidate_topics(heading),
            "skip_reason": None if high else ("过短/目录" if length < MIN_LEN else "低密度"),
        })
    return {
        "doc_id": doc_id(path), "path": path,
        "title": os.path.splitext(os.path.basename(path))[0],
        "chunks": chunks,
        "coverage": {
            "chunks_total": len(chunks),
            "high_value": sum(1 for c in chunks if c["high_value"]),
            "low_value": sum(1 for c in chunks if not c["high_value"]),
            "chunks_processed": 0, "chunks_skipped": 0,
            "high_value_done": False, "status": "mapped",
        },
    }


def main():
    ap = argparse.ArgumentParser(description="生成文档地图（两阶段之粗筛）")
    ap.add_argument("--source-root", required=True)
    ap.add_argument("--out", required=True, help="输出 JSONL（通常 _meta/doc_maps.jsonl）")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--append", action="store_true",
                    help="把本次结果**按 path 合并**进 --out（同名条目被本次覆盖，其余原样保留）；"
                         "不给这个开关时行为与以前逐字节相同（整文件重写）。"
                         "用途：把 `_meta/converted/` 这类第二源根并进同一份 doc_maps（丙批后新需求）。")
    args = ap.parse_args()

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    n_docs = n_high = n_chunks = 0
    fresh = []                                           # --append 时先收进内存，最后按 path 合并写回
    fh = None if args.append else open(args.out, "w", encoding="utf-8")
    try:
        for dirpath, dirnames, files in os.walk(args.source_root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, args.source_root).replace("\\", "/")
                size = os.path.getsize(full)
                if not is_body(rel, size, args.source_root):
                    continue
                with open(full, "r", encoding="utf-8", errors="ignore") as fh2:
                    text = fh2.read()
                m = map_one(rel, text)
                if args.append:
                    fresh.append(m)
                else:
                    fh.write(json.dumps(m, ensure_ascii=False) + "\n")
                n_docs += 1
                n_chunks += len(m["chunks"])
                n_high += m["coverage"]["high_value"]
                if args.limit and n_docs >= args.limit:
                    break
            if args.limit and n_docs >= args.limit:
                break
    finally:
        if fh is not None:
            fh.close()

    n_merged = 0
    if args.append:
        # 按 path 合并：本次覆盖同名旧条目，其余原样保留 ⇒ 重跑幂等、path 唯一。
        by_path = {}
        order = []
        if os.path.isfile(args.out):
            with open(args.out, "r", encoding="utf-8") as fin:
                for line in fin:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        old = json.loads(line)
                    except ValueError:
                        raise SystemExit("[doc_map] --append 要求 --out 每行是合法 JSON，"
                                         "但有一行解析不了：%.60s" % line)
                    p = old.get("path")
                    if p not in by_path:
                        order.append(p)
                    by_path[p] = old
        for m in fresh:
            if m["path"] not in by_path:
                order.append(m["path"])
            by_path[m["path"]] = m
        n_merged = len(fresh)
        with open(args.out, "w", encoding="utf-8") as fout:
            for p in order:
                fout.write(json.dumps(by_path[p], ensure_ascii=False) + "\n")

    print(f"[doc_map] 文档 {n_docs} 篇；切块 {n_chunks}；高价值块 {n_high}")
    if args.append:
        print(f"[doc_map] --append：本次并入 {n_merged} 篇（同名覆盖、path 唯一、重跑幂等）")
    print(f"[doc_map] → {args.out}")
    print("[doc_map] 下一步：用 progress.py 看进度与续跑起点")


if __name__ == "__main__":
    main()
