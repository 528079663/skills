---
name: article-format-clone
description: 公众号 HTML 克隆排版 CLI。给定一篇风格参考文章链接，自动解析其真实 HTML
  样式（正文/多种小标题版式/引用/加粗/高亮/引导关注卡/点亮图），再按该样式重排"我的文章"（另一篇链接或
  Markdown），实现换皮不换字。当用户说"克隆这个号的样式""按这个链接的风格排""看到一篇好看的文章想排同款""换皮不换字"时使用。
agent_created: true
disable-model-invocation: true
---

# 公众号 HTML 克隆排版（article-format-clone）

把"我的文章"按一篇参考公众号文章的真实排版基因重排，输出内联样式 HTML，可直接粘公众号。

## 何时使用

- 用户给一篇风格参考链接，想让自己的文章变成同款风格（"克隆这个号的样式""按这个链接的风格排"）。
- 与 article-format-draft（按固定主题排版）不同，本子 skill 直接解析参考文章真实 HTML，不依赖预置主题。

## CLI 用法

```bash
# 我的文章是另一篇已发布链接 → 换皮不换字
python scripts/clone_cli.py --style <风格参考URL> --content <我的文章URL> -o out.html

# 我的文章是 Markdown / 文本
python scripts/clone_cli.py --style <风格参考URL> --content my.md -o out.html
cat my.md | python scripts/clone_cli.py --style <风格参考URL> -o out.html

# 仅查看从参考文章提取到的样式（调试 / 供 preview 调用）
python scripts/clone_cli.py --style <URL> --dump-style
```

- `--style` 支持 URL / `data/styles` 下文件名 / 原始 JSON 字符串。
- `--content` 支持 URL / `.md` / `.txt` / `-`（标准输入）。
- 可选：`--no-follow` 不要引导关注卡和关注引导图；`--no-end` 不要结尾点亮图；`--no-ocr` 关闭 OCR（此时无法确认引导图来源，文首/文末图默认排除并提示自备）；`--keep-account` 引导关注卡沿用参考账号身份（默认用占位卡，避免照搬他人账号）；`--no-random-guide` 关闭素材库随机复用（默认开启）。
- 输出 = 引导关注卡 + 按参考样式重排的正文 + 点亮图，内联样式，直接粘公众号。

## 引导图素材库（按账号分档，无图时随机复用）

- **入库**：只有 OCR 识别通过的**通用引导图**（`follow` 关注图 / `end` 点亮图）才会存入 `data/guide_library/<账号键>/{follow,end}/`。二维码名片、原号 CTA 横幅（如"求求了点个推荐"）等**一律不入库**。
- **账号键**：优先参考账号昵称（`mp-common-profile` 的 nickname），无则用 style URL 摘要，再无则 `default`。
- **随机复用**：本次未识别到引导图时——若该账号素材档**有货** → 自动随机取一张复用（带告警说明是复用历史图）；若该档**为空** → 回退到"排除 + 提示自备"。`--no-random-guide` 可关闭随机复用。
- **水印可控**：按账号分档意味着排 X 号只会复用 X 号自己历史存过的引导图，不跨账号串用。

## 提取内容（全部自动，不写死颜色）

- 正文样式：字号 / 字色 / 行距 / 对齐 / 字间距
- 多种小标题版式：按"样式签名"聚类，一篇文章有几套标题风格就识别几套
- 引用块、加粗色、高亮底色
- 小标题居中：自动识别标题外层的居中包裹器，渲染时还原
- 配色（强调色 + 主题色）：提取正文里出现频次最高的强调色与主题蓝，整体统一
- 引导关注卡：从头部的 `mp-common-profile` 提取头像/名称/简介；默认不照搬参考账号身份，渲染成占位卡；`--keep-account` 才沿用
- 引导图片（点亮图/关注引导图）：**OCR 判定为主，绝不盲取，无法确认即排除**
  - OCR 命中二维码/名片 → 账号专属，绝不沿用原文，改为渲染占位框
  - OCR 命中在看/点赞/点亮/分享 → 结尾点亮图（并入库）
  - OCR 命中关注/公众号/蓝字 → 关注引导图（并入库）
  - OCR 读到非引导词（如原号 CTA）/ 无法识别 / OCR 不可用 → **默认排除该图并提示自备**，不盲目采用（规则4：兜底须确认）

## OCR（可选增强，统一走全局 OCR 微服务）

> OCR 统一调用**全局 OCR 微服务**（集群 / 单机两版、端口统一，用法见 `~/.workbuddy/ocr-microservice.md`），不依赖任何单 skill 私有实现。

- 超时 **10s**、失败**重试 2 次**（共 3 次尝试），仍失败 → 跳过该图文 OCR，按结构启发式降级，并写审计日志（A010003 / A010004）。
- 注：OCR 调用现由委托的 `meta-style-extract` 在 `extract_style` 内部触发（clone 不再直接持有 OCR 客户端），OCR 失败审计仍经 `article_formate/common/audit` 落盘（A010003 / A010004）。

## 运行环境（固定，最高优先级）

- **Python 解释器（固定）**：`~/.workbuddy/binaries/python\envs\base\Scripts\python.exe`（WorkBuddy base venv）。`beautifulsoup4` / `lxml` 已在 base venv 预装，先以该环境运行；若运行报错缺包（`No module named X`），再在该环境内 `pip install X`（不要换环境或自建 venv）。
- **运行方式**：在用户本机（Windows）直接前台执行，**不使用隔离 / 沙箱环境**。
- 下文命令中的 `python` 均指上述 base venv 解释器。
- OCR 为可选增强，统一走**全局 OCR 微服务**（见 `~/.workbuddy/ocr-microservice.md`）。

## 基础能力委托（元 skill）

本 CLI 只保留「渲染引擎 + 内容解析 + 引导图素材库 + --save-theme 归一化闭环」等独有逻辑；以下基础能力已委托给元 skill，**不再自行实现**（运行期实际执行的是元 skill 内的同名函数）：

- **网页抓取 / 图片下载 / 图片本地化** → `meta-web-fetch`。代码中以 `from core import fetch, load, fetch_image, _localize_images, _ext_from_data, _WX_REFERER, _IMG_SRC_RE` 导入。
- **样式提取（含引导图 OCR 判定）** → `meta-style-extract`。代码中以 `from extract_api import extract_style` 导入。

> 因此元 skill 的升级（如防盗链逻辑、样式统计投票法优化）会自动惠及本 CLI，无需在本文件同步维护副本。

## 与同项目其他子 skill 的关系

- article-format-preview 经 common/cli_bridge 子进程调用本 CLI 完成 `/api/render` 与 `/api/extract-style`（进程级解耦，**禁止 import** 内部函数）。
- 本 CLI **不 import 同项目其他子 skill（draft / preview）的内部函数**；但会委托元 skill 获取基础能力（见上节）：从 `meta-web-fetch` 导入网页抓取/图片下载/本地化，从 `meta-style-extract` 导入样式提取。

---

## 目录设计（输出约定）

> 遵循《Skill 统一输出目录规范》`skill-output-convention.md`。关键改动（已落实到 `scripts/clone_cli.py`）：
> - 渲染产物根由废止的 `article_formate/outputs/` 改为统一会话目录 `~/WorkBuddy/wechat-article-format_{YYYYMMDD-HHMM}/`（§1.1 / §6）。本子 skill 作为 `wechat-article-format` 的下游，**会话目录前缀沿用最外层入口 skill 名 `wechat-article-format`**（规范 §2.1 子 skill 体系规则）。
> - 产物命名由 stdout / 裸 `out.html` 改为 `{序号}_{阶段功能名称}_{主题}`：`0_clone_<主题>.html` + `0_images/`（本地化图片集合）（§2.4）。
> - 持久素材库（样式/主题/引导图）移出会话目录，落到 skill 内部的 `article_formate/data/`（styles / themes / guide_library），属 skill 持久数据，非会话交付物（§0.3）。

### 输入约定（源材料）

- `--style` / `--content` 为 URL、本地 `.md`/`.txt` 或标准输入（文件态源材料 (b)）。
- 网页抓取 / 图片下载 / 本地化由委托的 `meta-web-fetch` 完成；源 URL 不假设固定外部路径，抓取结果入站到本次会话目录（§3）。
- 用户提供的 `.md`/`.txt` 原文只读，不修改 / 不回写。

### 输出件登记表（依据本 skill 实际推导）

| 阶段功能名称 | 格式 | 类型 | 说明 | 是否多文件 | 合规命名示例 |
|---|---|---|---|---|---|
| `clone` | html | 文件 | 克隆排版 HTML（按参考样式重排后的正文 + 引导卡 + 点亮图） | 否 | `0_clone_我的文章.html` |
| `images` | （文件夹） | 文件夹 | 本地化图片集合（正文图 + 引导图，按原 URL 文件名归组） | 是 | `0_images/` |

- 主题 `<主题>` 由 `--content` 文件名 / `--style` 摘要 / 兜底推导，并经文件系统安全处理（§2.4）。
- `clone` / `images` 阶段名已登记于中央查重表 `skill-output-registry.md`；与 `easy-tuwen` 的 `cover`/`card`、`meta-export` 的 `export_*` 无前缀冲突。
- 跨 skill：本 CLI 委托 `meta-web-fetch`（抓取）与 `meta-style-extract`（样式提取，含 OCR 判定）；二者产出经参数串接进同一 `wechat-article-format_{ts}` 会话目录（§3.4）。`meta-style-extract` 的 `--save-theme` 写 `article_formate/data/`（持久数据，非会话产物）。
