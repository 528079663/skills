# -*- coding: utf-8 -*-
"""meta-style-extract CLI —— 公众号样式抽取（纯本地源码，无在线获取）。

子命令：
  extract  从网页源码（文件或 stdin）提取样式配置 JSON
           注意：本 skill 不抓取 URL；源码须先由 meta-web-fetch 取得后传入。

调用示例：
  python cli.py extract style.html
  cat page.html | python cli.py extract - --ocr
  python cli.py extract page.html --json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_api import extract


def _read_src(arg):
    if arg == "-":
        return sys.stdin.read()
    with open(arg, encoding="utf-8") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser(description="meta-style-extract 公众号样式抽取（纯本地源码）")
    p = ap.add_subparsers(dest="cmd", required=True)

    pe = p.add_parser("extract", help="从网页源码提取样式配置")
    pe.add_argument("src", help="网页源码文件，或 - 表示 stdin（须为源码，非 URL）")
    pe.add_argument("--ocr", action="store_true", help="对引导图做 OCR 确认（需 meta-ocr 服务就绪）")
    pe.add_argument("--json", action="store_true", help="以 JSON 输出结果")

    args = pe.parse_args()
    html = _read_src(args.src)
    try:
        style = extract(html, ocr=args.ocr)
    except Exception as e:
        sys.stderr.write("[错误] %s\n" % e)
        raise SystemExit(1)
    print(json.dumps(style, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
