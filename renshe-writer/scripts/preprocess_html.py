#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preprocess_html.py —— HTML 文章预处理（解析正文 + 图片 OCR）

把公众号 / 网页 HTML 解析为正文文本，并把文中图片交给跨项目共用的
**paddleocr OCR 微服务**（基于 PaddleOCR，由 wechat-article-extractor 提供）做文字识别，
最终把「正文 + 各图 OCR 文本」合并为一份素材文件，供 renshe-writer 提炼人设。

OCR 调用方式与 wechat-article-extractor/scripts/extract_article.py 的 ocr_images() 同款：
只调已运行的 paddleocr-svc 微服务（HTTP POST /ocr），不起容器、不做任何引擎回退；
微服务不可用即明确报错，绝不静默用别的 OCR 方案顶替。

依赖：Python 3 + bs4（pip install beautifulsoup4 lxml）。图片识别走 paddleocr OCR 微服务，
本脚本不自带、也不回退任何本地 OCR 引擎。
"""

import os
import sys
import io
import json
import argparse
import urllib.request
import urllib.error
from bs4 import BeautifulSoup

DEFAULT_SVC = "http://localhost:9000"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def parse_body(html):
    """用 bs4 取 #js_content / article / body 正文，按段落/标题拼为纯文本。

    返回 (text, para_count)：para_count 为正文块级元素（section/p/h1..6）的叶子段数，
    供类型判定使用。取叶子块可避免父 section 包含子 section 导致的文本重复。
    """
    soup = BeautifulSoup(html, "html.parser")
    container = (soup.select_one("#js_content")
                 or soup.select_one("article")
                 or soup.body)
    if container is None:
        for tag in soup(["script", "style"]):
            tag.decompose()
        return soup.get_text("\n", strip=True), 0
    blocks = ["section", "p", "h1", "h2", "h3", "h4", "h5", "h6"]
    paras = []
    for el in container.find_all(blocks):
        if not el.find(blocks):  # 仅取叶子块级，避免父/子重复
            txt = el.get_text(strip=True)
            if txt:
                paras.append(txt)
    return "\n".join(paras), len(paras)


def extract_image_urls(html):
    """取文中图片 URL（优先 data-src，回退 src），过滤非 http(s)，去重。"""
    soup = BeautifulSoup(html, "html.parser")
    container = (soup.select_one("#js_content")
                 or soup.select_one("article")
                 or soup.body)
    urls = []
    if container is not None:
        for img in container.find_all("img"):
            src = img.get("data-src") or img.get("src") or ""
            if src.startswith("http://") or src.startswith("https://"):
                if src not in urls:
                    urls.append(src)
    return urls


# 非内容图关键词（头像/图标/二维码/动图等），文章型下不送 OCR
_SKIP_IMG_KEYS = ("avatar", "headimg", "logo", "icon", "qr", "qrcode",
                  "emoji", "wx_fmt=gif", ".gif")


def is_content_image(url):
    """文章型下过滤掉头像/图标/二维码等非正文配图。"""
    u = (url or "").lower()
    return not any(k in u for k in _SKIP_IMG_KEYS)


def classify(para_count, img_count):
    """自动判定来源类型：贴图型 / 文章型。

    贴图型：正文段落极少(<3)且图片较多(>=2)，说明文字主要在图片里。
    文章型：正文充足，以文字为主，图片仅作配图。
    返回 (doc_type, reason)。
    """
    if para_count < 3 and img_count >= 2:
        return ("贴图",
                "正文段落 %d 段(<3) 且图片 %d 张(>=2)，判定为贴图型："
                "文字主要在图片中，已对全部图片做 OCR" % (para_count, img_count))
    return ("文章",
            "正文段落 %d 段，判定为文章型：以文字正文为主，"
            "仅对内容配图(已滤除头像/图标/二维码)做 OCR" % para_count)


def ocr_images(image_urls, svc=None, timeout=180):
    """调用 paddleocr OCR 微服务提取图片文字，返回 (list_of_text, error)。

    与 extract_article.py 的 ocr_images() 同款：只调已运行的微服务，不起容器、不回退。
      - 服务没起 -> 返回错误并提示先 `python ocr_service.py start`；
      - 某张图识别失败 -> 该张返回 ⚠️ 提示，绝不静默用别的引擎顶替。
    """
    if not image_urls:
        return [], "没有可 OCR 的图片"
    import sys, os
    _ext = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "wechat-article-extractor", "scripts"))
    if _ext not in sys.path:
        sys.path.insert(0, _ext)
    import ocr_client
    items, err = ocr_client.ocr_images(image_urls, svc=svc, timeout=timeout)
    if err:
        return None, err
    texts = []
    for it in items:
        if it.error:
            texts.append(f"⚠️ 图片 OCR 失败：{it.error}")
        else:
            texts.append(it.text or "(未识别到文字)")
    return texts, None


def preprocess(html, svc=None):
    """端到端：自动判定类型 + 正文 + 图片 OCR -> 合并素材文本。返回 (material_text, error)。"""
    body, para_count = parse_body(html)
    urls_all = extract_image_urls(html)
    img_count = len(urls_all)
    doc_type, reason = classify(para_count, img_count)
    header = "# 类型判定\n\n[类型: %s]\n依据: %s\n" % (doc_type, reason)

    if doc_type == "贴图":
        urls = urls_all  # 贴图型：文字在图中，全部 OCR
    else:
        urls = [u for u in urls_all if is_content_image(u)]
        skipped = img_count - len(urls)
        if skipped > 0:
            header += ("已滤除非内容图(头像/图标/二维码等) %d 张，仅对 %d 张内容图 OCR。\n"
                       % (skipped, len(urls)))

    if not urls:
        # 没有(内容)图片也能产出（只有正文），不算 OCR 失败
        return header + "\n# 正文\n\n" + body + "\n", None
    texts, err = ocr_images(urls, svc=svc)
    if err:
        return None, err
    parts = [header, "# 正文\n\n" + body + "\n", "# 图片 OCR 文本\n"]
    for i, t in enumerate(texts, 1):
        parts.append(f"## 图{i}\n\n{t}\n")
    return "\n".join(parts), None


def _read_html(path_or_url, is_url):
    if is_url or path_or_url.lower().startswith(("http://", "https://")):
        req = urllib.request.Request(path_or_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="ignore")
    return io.open(path_or_url, encoding="utf-8", errors="ignore").read()


def main():
    ap = argparse.ArgumentParser(description="HTML 文章预处理（解析正文 + 图片 OCR）")
    ap.add_argument("html", help="本地 HTML 文件路径，或公众号文章链接 URL")
    ap.add_argument("--url", action="store_true",
                    help="把位置参数当 URL 抓取（默认当本地文件）")
    ap.add_argument("--output", help="输出素材 Markdown 路径（默认标准输出）")
    ap.add_argument("--svc", help="paddleocr OCR 微服务地址（默认 $PADDLEOCR_SVC 或 http://localhost:9000）")
    args = ap.parse_args()

    try:
        html = _read_html(args.html, args.url)
    except Exception as e:
        sys.stderr.write("[错误] 读取 HTML 失败：%s\n" % e)
        raise SystemExit(1)

    material, err = preprocess(html, svc=args.svc)
    if err:
        sys.stderr.write("[错误] 预处理失败：%s\n" % err)
        raise SystemExit(1)

    if args.output:
        io.open(args.output, "w", encoding="utf-8").write(material)
        sys.stderr.write("[完成] 素材已写入 %s\n" % args.output)
    else:
        sys.stdout.write(material + "\n")


if __name__ == "__main__":
    main()
