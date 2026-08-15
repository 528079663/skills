# -*- coding: utf-8 -*-
"""meta-web-fetch CLI —— 网页抓取与本地落盘。

子命令：
  fetch  抓取/读取网页，输出干净正文+图片列表 JSON；可加 --download-to 落盘整页
  health 留空（本 skill 无外部服务依赖）

调用示例：
  python cli.py fetch "https://mp.weixin.qq.com/s/xxx"
  python cli.py fetch article.html --download-to ./out
  python cli.py fetch "https://example.com" --download-to ./out --json
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import fetch_page


# —— Skill 统一输出目录规范：落盘默认会话目录（规范 §1.1 / §1.2）——
_OUTPUT_ROOT = os.environ.get("WORKBUDDY_OUTPUT_ROOT", os.path.expanduser("~/WorkBuddy"))


def _default_download_dir():
    """未传 --download-to 时，在本机唯一产物根下创建 meta-web-fetch_{ts} 会话目录，
    并在其内建 0_webpage 整页包（index.html + images/），避免裸 images/ 与落到运行目录。"""
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    base = os.path.join(_OUTPUT_ROOT, "meta-web-fetch_%s" % ts)
    if os.path.exists(base):
        i = 2
        while os.path.exists("%s-%d" % (base, i)):
            i += 1
        base = "%s-%d" % (base, i)
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "0_webpage")


def main():
    ap = argparse.ArgumentParser(description="meta-web-fetch 网页抓取与本地落盘")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fetch", help="抓取/读取网页，返回正文+图片列表")
    p.add_argument("src", help="http(s) URL 或本地 .html 路径")
    p.add_argument("--download-to", help="把整页（HTML+图片）下载到此目录")
    p.add_argument("--json", action="store_true", help="以 JSON 输出结果")

    args = ap.parse_args()
    if args.cmd == "fetch":
        try:
            download_to = args.download_to or _default_download_dir()
            result = fetch_page(args.src, download_to=download_to)
        except Exception as e:
            sys.stderr.write("[错误] %s\n" % e)
            raise SystemExit(1)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("标题：%s" % result["title"])
            print("图片数：%d  链接数：%d" % (len(result["images"]), len(result["urls"])))
            if result.get("local_dir"):
                print("已下载到本地：%s" % result["local_dir"])
            print("\n----- 正文 -----\n%s" % result["text"][:4000])


if __name__ == "__main__":
    main()
