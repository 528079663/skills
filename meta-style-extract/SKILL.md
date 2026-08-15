---
name: meta-style-extract
description: "本技能是公共元 skill（可组装构件），负责从网页源码中抽取结构化公众号排版样式配置。本身不含任何在线获取能力——只消费由 meta-web-fetch 取得的网页源码字符串。任何需要从参考文章反推排版风格（颜色/标题/引用/强调等）的上层 skill 都应委托本技能，避免各自实现。"
agent_created: true
disable-model-invocation: true
---

# meta-style-extract — 公众号样式抽取（纯本地源码提取）

> 公共可组装构件（Tier 2 领域能力）。**本 skill 不内置任何在线获取能力**——只消费「已由 meta-web-fetch 取得的网页源码字符串」。

## 抽取来源（单源）

`article-format-clone/scripts/clone_cli.py` 的 `extract_style()`（统计投票法，不写死颜色——已复制为 `clone_core.py`）。

## 接口契约

```python
from extract_api import extract
extract(html: str, ocr: bool = False, style_url: str = "") -> dict
# html: 网页源码字符串（非 URL），须由调用方从 meta-web-fetch 取得后传入
# ocr: 是否对引导图做 OCR 确认（默认 False，离线；True 需 meta-ocr 微服务就绪）
# 返回样式配置 dict：{body, headings, quote, strong_color, mark_bg, follow, end_img, ...}
```

## 关键能力

- 定位 `#js_content`；排除简介灰字；`classify_block` 打标；颜色众数投票（不写死）。
- 小标题居中识别；配色（强调色 + 主题色）整体统一。
- 引导图**须经 OCR 确认才采用**（默认离线跳过，避免盲取）。
- 仅消费内存 / 本地 HTML 源码，**不发起任何网络请求**。

## 调用方式

> **路径约定**：`<SKILL_DIR>` 指本 skill 自身根目录（user 级 `~/.workbuddy/skills/meta-style-extract`，项目级 `<workspace>/.workbuddy/skills/meta-style-extract`）。

**子进程 CLI：**
```bash
python <SKILL_DIR>/scripts/cli.py extract page.html
cat page.html | python <SKILL_DIR>/scripts/cli.py extract - --json
# 注意：传的是源码文件，不是 URL；在线获取请先调 meta-web-fetch
```

**import 函数：** 见上方接口契约。

## 消费者

clone、draft（二者须先经 `meta-web-fetch` 取得网页源码，再传入本 skill 提取）。

## 依赖

- **Python 解释器（固定）**：`~/.workbuddy/binaries/python\envs\base\Scripts\python.exe`（WorkBuddy base venv）。`beautifulsoup4` / `lxml` 已在 base venv 预装，先以该环境运行；若运行报错缺包（`No module named X`），再在该环境内 `pip install X`（不要换环境或自建 venv）；本机直接前台运行，不使用隔离 / 沙箱环境。下文 `python` 均指该解释器。

## 目录设计（输出约定）

> 本 skill 为**纯本地源码提取**，核心能力是内存态样式 dict（`extract(html)` 返回 dict），**默认不产生文件产物**，不占用统一会话目录（§1.1 仅约束有文件产物的 skill）。
> 仅当调用方显式 `--save-theme <名>` 时，才把样式归一化为主题写入 `article_formate/references/themes/<名>.json`（持久数据，非会话产物，类比 `meta-persona` 的 `~/.workbuddy/personas/`）。

- **无默认文件产物** → 不登记输出件登记表（内存态 dict 为主）。
- **`--save-theme` 持久数据**：`article_formate/references/themes/<名>.json`，跨会话复用，不计入会话目录、不受 `{序号}_{阶段}_{主题}` 命名约束。
- **克隆引擎持久共享库（`clone_core.py`，例外）**：`article_formate/data/guide_library/`（共享引导图素材库，按账号分档）、`article_formate/data/styles/`（保存的提取风格配置，跨会话复用）属 skill 持久共享数据，非会话交付物，已登记于中央查重表 §一（例外）。其渲染交付物（`clone` HTML + `0_images/`）仍落统一会话目录 `wechat-article-format_{ts}`（§1.1 / §6）。
- **源输入**：消费由 `meta-web-fetch` 取得的网页源码字符串（内存态），不发起网络请求、不绑定任何外部固定路径。
