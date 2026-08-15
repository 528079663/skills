# HTML 文章预处理：正文解析 + 图片 OCR

当用户提供的来源是 **HTML 文件/网页**（如微信公众号文章、博客导出）时，正文被包裹在
大量 UI 噪音（菜单、点赞、分享、小程序）与图片中。提取人设前需先做如下预处理，把"可分析
的文本"尽可能完整地抽出来——尤其是图片里可能藏着关键文字（金句、清单、研究结论）。

## 1. 解析正文

用 `bs4` 定位正文容器，剥离脚本/样式与 UI 噪音，优先取 `<p>` 段落文本：

```python
from bs4 import BeautifulSoup

def extract_body(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # 正文容器解析顺序：#js_content -> article -> body（与 scripts/preprocess_html.py 实际逻辑一致）
    el = soup.select_one("#js_content") or soup.select_one("article") or soup.body
    for t in el(["script", "style", "noscript"]):
        t.decompose()
    paras = [p.get_text(strip=True) for p in el.find_all("p")]
    paras = [t for t in paras if t]
    if len(paras) >= 3:
        return "\n".join(paras)
    return el.get_text("\n", strip=True)
```

要点：微信公众号正文通常在 `#js_content`；`<p>` 标签里是真实行文，点赞/分享等 UI 多在
其它标签，优先取 `<p>` 可大幅降噪。

## 1.5 自动类型判定（preprocess_html.py 内置）

`scripts/preprocess_html.py` 在预处理时会**自动区分「贴图型」与「文章型」**，无需手动加开关：

- **贴图型**：正文 `<p>` 段落 < 3 且图片 ≥ 2 张 → 判定文字主要在图片中，对**全部图片**做 OCR。
- **文章型**：正文充足 → 判定以文字为主，仅对**内容配图**做 OCR（自动滤除头像/图标/二维码/动图等非内容图），避免照片类噪声混入素材。

两种类型都会在输出素材顶部标注 `# 类型判定` 章节（含 `[类型: …]` 与判定依据），便于后续提炼人设时区分配图值与正文噪声。

## 2. 提取并下载图片

图片多为懒加载（`data-src`）或 `src`，常托管在远程（如 `mmbiz.qpic.cn`）：

```python
import os, re, urllib.request

def download_images(el, out_dir: str, ua: str = "Mozilla/5.0") -> list:
    os.makedirs(out_dir, exist_ok=True)
    urls = []
    for img in el.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        if src.startswith("http"):
            urls.append(src)
    local = []
    for i, u in enumerate(urls):
        m = re.search(r"\.(png|jpe?g|gif|webp)", u, re.I)
        ext = ("." + m.group(1).lower()) if m else ".jpg"
        dst = os.path.join(out_dir, f"img_{i}{ext}")
        try:
            req = urllib.request.Request(u, headers={"User-Agent": ua})
            data = urllib.request.urlopen(req, timeout=25).read()
            if len(data) > 3000:   # 跳过图标/占位小图
                open(dst, "wb").write(data)
                local.append(dst)
        except Exception:
            pass
    return local
```

## 3. 对图片做 OCR（调用全局 OCR 微服务）

> OCR 统一走**全局 OCR 微服务**（集群 / 单机两版、端口统一），用法、启动、health / ensure、调用方式、集群与单机差异见 `~/.workbuddy/ocr-microservice.md`。本 skill 不自带 OCR 引擎，**不得自行引入其他 OCR 引擎**。

- 一键脚本 `scripts/preprocess_html.py`：运行 `python scripts/preprocess_html.py <html 文件或文章链接>` 即可自动解析正文、把图片送 OCR 微服务、合并输出素材 Markdown；微服务不可用时明确报错，绝不回退其他 OCR 引擎。

## 4. 合并后提取

把"正文文本 + 各图片 OCR 文本"拼接为一份素材，再按 `persona_schema.md` 的维度提炼人设。
注意：

- OCR 对照片类图片往往提取不到有效文字，属正常；对金句图、清单图、研究数据图价值高。
- 不要把 OCR 噪声（乱码、误识字符）当作事实写入人设；OCR 结果仅作风格/补充佐证。
- 若某图 OCR 为空或明显无意义，可忽略，不强行使用。
