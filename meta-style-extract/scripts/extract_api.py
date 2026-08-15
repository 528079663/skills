# -*- coding: utf-8 -*-
"""meta-style-extract 核心 API。

抽取自 article-format-clone/scripts/clone_cli.py 的 extract_style()（统计投票法，不写死颜色）。
本元 skill 不内置任何在线获取能力 —— 只消费「已由 meta-web-fetch 取得的网页源码字符串」，
从源码里提取结构化样式配置。

接口契约：extract(html: str, ocr: bool = False) -> dict
  - html: 网页源码字符串（非 URL），由调用方从 meta-web-fetch 取得后传入
  - ocr: 是否对引导图做 OCR 确认（默认 False，离线；True 需 meta-ocr 微服务就绪）
"""
from bs4 import BeautifulSoup

from clone_core import extract_style


def extract(html, ocr=False, style_url=""):
    """从网页源码字符串提取公众号样式配置 dict。

    html 必须是源码文本，不是 URL。如需在线获取，请先调用 meta-web-fetch。
    """
    soup = BeautifulSoup(html, "html.parser")
    return extract_style(soup, style_url=style_url, ocr=ocr)
