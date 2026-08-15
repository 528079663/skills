---
name: meta-web-fetch
description: "本技能是公共元 skill（基础设施层），负责网页/本地 HTML 抓取与正文提取，并支持把访问到的网页（HTML+图片）下载到本地目录，产出自包含、可离线预览的产物。任何需要取网页源码或正文的上层 skill 都应委托本技能，不再各自实现抓取。"
agent_created: true
disable-model-invocation: true
---

# meta-web-fetch — 网页抓取与本地落盘（含正文提取）

> 公共可组装构件（Tier 1 基础设施）。单一职责：抓取 / 读取网页，返回干净正文 + 图片列表，并能把整页下载到本地。

## 抽取来源（单源）

`article-format-clone/scripts/clone_cli.py` 的 `fetch()` / `load()` / `fetch_image()` / `_localize_images()`（Chrome UA 伪装、Referer 防盗链、图片按文件头魔数判扩展名、src 改写为本地相对路径）。

## 接口契约

```python
fetch_page(src: str, download_to: str | None = None) -> dict
# 返回 {title, text, images: list[str], urls: list[str], local_dir?: str}
# src: http(s) URL 或本地 .html 路径
# download_to: 给定目录时，把页面 HTML 与文中图片下载落盘、src 改写为本地相对路径，返回 local_dir
```

## 关键能力

- Chrome UA 伪装；`load()` 统一 URL / 本地路径双入口。
- `<meta charset>` 解析防中文乱码；清 script/style/nav/footer 噪声，提取标题 + 干净正文 + 图片列表 + 链接列表。
- `fetch_image` 带 Referer 防盗链下载图片并按文件头魔数判扩展名。
- `_localize_images` 把全部 http(s) 图片下载到本地、src 改写为相对路径，产物自包含、离线可预览。
- **整页下载到本地**：`download_to` 给定目录时，写 `index.html` + `images/`，支持二次处理 / 离线打开。

## 调用方式

> **路径约定**：`<SKILL_DIR>` 指本 skill 自身根目录（user 级 `~/.workbuddy/skills/meta-web-fetch`，项目级 `<workspace>/.workbuddy/skills/meta-web-fetch`）。

**子进程 CLI：**
```bash
python <SKILL_DIR>/scripts/cli.py fetch "https://example.com/a.html"
python <SKILL_DIR>/scripts/cli.py fetch page.html --download-to ./out --json
```

**import 函数：**
```python
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
from core import fetch_page
result = fetch_page("https://example.com/a.html", download_to="./out")
```

## 消费者

extractor、article-rewriter、clone、draft、tuwen、xianyu。

## 依赖

- **Python 解释器（固定）**：`~/.workbuddy/binaries/python\envs\base\Scripts\python.exe`（WorkBuddy base venv）。`beautifulsoup4` / `lxml` 已在 base venv 预装，先以该环境运行；若运行报错缺包（`No module named X`），再在该环境内 `pip install X`（不要换环境或自建 venv）；本机直接前台运行，不使用隔离 / 沙箱环境。下文 `python` 均指该解释器。

---

## 目录设计（输出约定）

> 本 skill 是公共元 skill；通过 `fetch(src, download_to)` 的 `download_to` 把整页落盘到**调用方传入的会话目录**（统一根 `~/WorkBuddy/{skill}_{ts}`），自身不绑定固定输出路径（§1.1 / §3.4）。

### 输出件登记表（依据本 skill 实际推导）

| 阶段功能名称 | 格式 | 类型 | 说明 | 是否多文件 | 合规命名示例 |
|---|---|---|---|---|---|
| `source` | html | 文件 | 抓取 / 本地化的整页（自包含离线快照，含 `index.html`） | 否 | `0_source_参考文章.html`（由调用方命名） |
| `images` | （文件夹） | 文件夹 | 文中图片本地化集合（`images/`，随 `source` 页自包含） | 是 | `images/`（被 clone 重新前缀为 `0_images/`） |

- 仅当调用方传入 `download_to` 时才落盘；内存态返回（`text` / `images` 列表）不落盘时无任何文件产物。
- `source` 已登记统一输出目录（中央查重）；`images` 文件夹名由调用方（如 `article-format-clone`）按 §2.4 重新前缀为 `0_images/`。
- 跨 skill：被 clone / draft / extractor / xianyu 委托；产出经 `download_to` 入站到上层同一会话目录（§3.4）。
