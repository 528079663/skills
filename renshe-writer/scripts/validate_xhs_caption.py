#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
贴图小红书文案（caption）校验脚本。

公式来源：tuwen-md-convert 的「小红书文案」规则（route A ③ 步前移产出）。
校验维度（程序化）：
  - 正文字数 200–400（标题与 #标签 不计入）
  - 无 markdown 语法（**, # 标题 等）
  - emoji 分点 ≥ 3
  - 结尾有开放式互动引导（评论区/聊聊/说说/留言等）

用法：python validate_xhs_caption.py <小红书文案.md>
"""
import re
import sys


def validate(path: str) -> bool:
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines()
    body_lines = []
    for l in lines:
        s = l.strip()
        # 跳过 markdown 一级标题（纯文本文案不应有，兼容历史文件）
        if s.startswith("# ") and not s.startswith("## "):
            continue
        body_lines.append(l)
    body = "\n".join(body_lines)
    body = re.sub(r"#[\u4e00-\u9fa5A-Za-z]+", "", body)  # 去掉行内 #标签

    n = len("".join(body.split()))
    has_md = ("**" in body) or bool(re.search(r"(?m)^#+\s", body))
    emoji = len(re.findall(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", body))
    has_interact = bool(re.search(r"评论区|聊聊|说说|留言|告诉我|来[评论聊]+", body))

    print(f"正文字数={n}", "✅" if 200 <= n <= 400 else "⚠(需200-400)")
    print(f"markdown语法(**,#标题)={'有 ⚠需清除' if has_md else '无 ✅'}")
    print(f"emoji分点={emoji}(需≥3)", "✅" if emoji >= 3 else "⚠")
    print("结尾互动引导(开放式):", "✅" if has_interact else "⚠")

    ok = (200 <= n <= 400) and (not has_md) and (emoji >= 3) and has_interact
    print("RESULT:", "全部达标 ✅" if ok else "存在不达标项 ⚠")
    return ok


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python validate_xhs_caption.py <小红书文案.md>")
        sys.exit(2)
    sys.exit(0 if validate(sys.argv[1]) else 1)
