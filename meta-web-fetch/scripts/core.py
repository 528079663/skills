# -*- coding: utf-8 -*-
"""meta-web-fetch 核心实现。

抽取自 article-format-clone/scripts/clone_cli.py 的网页抓取与本地落盘方法
（fetch / load / fetch_image / _localize_images），并补充「干净正文提取」
与「整页下载到本地」能力。

接口契约：
  - fetch(url) -> str：底层原始抓取，返回解码后的 HTML 字符串（Chrome UA 伪装）。
  - fetch_page(src, download_to=None) -> dict：统一入口，返回 {title,text,images,urls}，
    download_to 给定目录时把整页 HTML 与图片落盘、src 改写为本地相对路径。
  ⚠️ fetch 与 fetch_page 同名曾导致 load→fetch→load 无限递归（已改为 fetch_page 消除冲突）。
"""
import os
import re
import sys
import hashlib
import urllib.request
import urllib.parse

from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 微信图床防盗链：图片经本机（带来源 Referer）下载到本地，HTML 改写为本地相对路径
_IMG_SRC_RE = re.compile(r'src="(https?://[^"]+)"')
_WX_REFERER = "https://mp.weixin.qq.com/"


def fetch(url):
    """抓取 URL，返回解码后的 UTF-8 文本（Chrome UA 伪装）。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")


def load(url_or_path):
    """URL 则抓取，本地路径则读文件。"""
    if url_or_path.startswith(("http://", "https://")):
        return fetch(url_or_path)
    with open(url_or_path, encoding="utf-8") as fh:
        return fh.read()


def fetch_image(url, referer=""):
    """下载图片字节（公众号图床需带 Referer 否则 403）。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": referer or url,
    })
    return urllib.request.urlopen(req, timeout=30).read()


def _ext_from_data(data, url):
    """根据文件头魔数与 URL 后缀判定图片扩展名。"""
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    p = urllib.parse.urlparse(url).path
    _, ext = os.path.splitext(p)
    if ext and ext.lower() in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"):
        return ext.lower()
    return ".jpg"


def _localize_images(html, images_dir, referer, prefix):
    """将 HTML 中所有 http(s) 图片下载到 images_dir，src 改写为本地相对路径 prefix/<file>。

    下载 / 落盘失败则保留原 URL（黏公众号时微信自身允许引用），不中断渲染。
    """
    os.makedirs(images_dir, exist_ok=True)
    seen = {}

    def repl(m):
        url = m.group(1)
        if url in seen:
            return 'src="%s"' % seen[url]
        try:
            data = fetch_image(url, referer=referer)
        except Exception as e:
            print("[warn] 图片下载失败，保留原链接：%s (%s)" % (url[:60], e), file=sys.stderr)
            seen[url] = url
            return m.group(0)
        ext = _ext_from_data(data, url)
        fn = hashlib.md5(url.encode("utf-8")).hexdigest()[:16] + ext
        fp = os.path.join(images_dir, fn)
        try:
            with open(fp, "wb") as f:
                f.write(data)
        except OSError as e:
            print("[warn] 图片落盘失败，保留原链接：%s (%s)" % (url[:60], e), file=sys.stderr)
            seen[url] = url
            return m.group(0)
        local = prefix + "/" + fn
        seen[url] = local
        return 'src="%s"' % local

    return _IMG_SRC_RE.sub(repl, html)


def _extract_body(html):
    """从 HTML 解析出标题 / 干净正文 / 图片列表 / 链接列表。"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "iframe"]):
        tag.decompose()

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    h1 = soup.find("h1")
    if not title and h1 and h1.get_text(strip=True):
        title = h1.get_text(strip=True)

    text = soup.get_text("\n")
    # 折叠多余空行
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    text = "\n".join(lines)

    base = ""
    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if src and src.startswith("http"):
            images.append(src)
        elif src and not src.startswith("data:"):
            # 相对路径转绝对
            if base and not src.startswith("/"):
                images.append(urllib.parse.urljoin(base, src))
    images = list(dict.fromkeys(images))  # 去重保序

    urls = []
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        if href and href.startswith("http"):
            urls.append(href)
    urls = list(dict.fromkeys(urls))

    return title, text, images, urls


def fetch_page(src, download_to=None):
    """统一入口：抓取/读取网页，返回干净正文 + 图片列表；可选下载到本地。

    返回 dict：
      {title, text, images:list[str], urls:list[str], local_dir?:str}
    - src 为 http(s) URL 或本地 .html 路径
    - download_to 给定目录时：把页面 HTML 与文中图片下载落盘、src 改写为
      本地相对路径，返回 local_dir（产物自包含、可离线预览）
    """
    raw = load(src)
    title, text, images, urls = _extract_body(raw)
    result = {"title": title, "text": text, "images": images, "urls": urls}

    if download_to:
        os.makedirs(download_to, exist_ok=True)
        referer = src if src.startswith("http") else _WX_REFERER
        localized = _localize_images(raw, os.path.join(download_to, "images"),
                                     referer=referer, prefix="images")
        html_path = os.path.join(download_to, "index.html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(localized)
        result["local_dir"] = download_to
    return result
