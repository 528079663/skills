---
name: article-format-draft
description: 公众号草稿排版 CLI。按统一 Markdown
  规范写草稿，套用已校准的账号主题（references/themes/）一键排版，输出内联样式
  HTML，可直接粘公众号。当用户说"公众号排版""文章排版""按主题排个版""用 xiangxiang 主题排"时使用。
agent_created: true
disable-model-invocation: true
---

# 公众号草稿排版（article-format-draft）

把按规范写好的轻量标记草稿，套用账号主题，转换成符合公众号阅读习惯的内联样式 HTML。

## 何时使用

- 用户需要把一篇草稿排成公众号文章（"帮我排个版""公众号排版"等）。
- 首次使用前必须先**校准风格**：提供 2-3 篇带排版的公众号文章，提取公共排版逻辑写入 `references/style_guide.md`，具体数值填入 `references/themes/<账号名>.json`，并在 `references/theme.json` 分发器登记。

## 方法论

本子 skill  embodiment 了「五步排版法」（内容解构 → 设计令牌 → CSS 框架 → 内容填充 → 间距校准），详见 `references/five_step_method.md`。核心：样式集中在 `tokens`（设计令牌）单一真源，`blocks` 用 `@token` 引用，改一处全局换肤。

## 运行环境（固定，最高优先级）

- **Python 解释器（固定）**：`~/.workbuddy/binaries/python\envs\base\Scripts\python.exe`（WorkBuddy base venv）。本 CLI 依赖 `beautifulsoup4` / `lxml` 等已在 base venv 预装，先以该环境运行；若运行报错缺包（`No module named X`），再在该环境内 `pip install X`（不要换环境或自建 venv）。
- **运行方式**：在用户本机（Windows）直接前台执行，**不使用隔离 / 沙箱环境**。
- 下文命令中的 `python` 均指上述 base venv 解释器。

## CLI 用法

```bash
# 用默认主题（内联样式，贴公众号）
python scripts/draft_cli.py input.md -o out.html

# 指定账号主题（多账号共用时）
python scripts/draft_cli.py input.md -t proluo -o out.html

# 标准模式（设计令牌 + 语义 class，本地预览/自托管用）
python scripts/draft_cli.py input.md --emit standard -o out.html

# 列出全部可用主题
python scripts/draft_cli.py --list-themes

# 草稿作为标准输入
cat input.md | python scripts/draft_cli.py -t proluo
```

> `--emit`：`inline`（默认，内联样式，微信兼容）/ `standard`（`:root` 令牌 + 语义 class，仅本地预览/自托管，贴微信会失效）。

## 可用主题（直接 `-t` 选用）

所有主题均遵循《公众号排版完全指南》：全程内联样式、卡片统一用 `<blockquote>`、分割线用 `<hr>`、`<section>`/`flex`/`box-shadow`/卡片圆角一律禁用。主题配色由 `tokens` 单一真源驱动，改一处全局换肤。

| 主题名 (`-t`) | 风格 / 适用 | 主色 | 备注 |
|---|---|---|---|
| `xiangxiang`（默认） | 红标题育儿号（已校准真实账号） | 红 `#d92142` | 浅蓝引用块 + 黄底高亮 |
| `proluo` | 蓝标育儿号（已校准真实账号） | 蓝 `#2E81DA` | 浅蓝底蓝顶边小标题 + 黄底高亮 |
| `warm-brown` | 暖棕金 · 理财/成长/生活 | 暖棕 `#8d6e63` | 小标题带圆形数字徽章 |
| `deep-blue` | 深蓝灰 · 职场/干货/科技 | 深蓝灰 `#2c3e50` | 小标题带圆形数字徽章 |
| `sage-green` | 莫兰迪绿 · 治愈/母婴/自我成长 | 莫兰迪绿 `#6b8e7f` | 清新柔和 |
| `rose-red` | 胭脂红 · 情感/女性/国风 | 胭脂红 `#c0392b` | 温暖有力 |
| `forest` | 墨绿文艺 · 读书/观点 | 墨绿 `#2e5d4b` | 文艺沉静 |
| `purple` | 星河紫 · 年轻/科技/创意 | 星河紫 `#6c5b9e` | 年轻时尚 |

> 新增主题：复制 `references/themes/` 下任一文件改名，`tokens` 改成你的品牌色，并在 `references/theme.json` 的 `available`/`themes` 登记即可；开启 `heading_badge: true` 可让 `##` 小标题自动加圆形数字徽章。

## 输入格式（要点，完整规范见 references/input_format.md）

- `# 大标题` / `## 小标题` / `### 子标题`
- 空行分隔段落
- `**加粗**`、`*斜体*`、`` `代码` ``、`==高亮==`
- `> 引用`
- `- 列表项` 或 `1. 列表项`
- `---` 分割线
- `![图注](图片URL)` 图片
- `::: tip` / `::: warning` / `::: info` ... `::: end` 提示框
- 五步法语义块：`::: intro` / `::: section` / `::: item` / `::: action` / `::: ps` / `::: footer` ... `::: end`
- 引导关注 / 二维码 / 往期回顾不用写：平台自动注入；正文要带图用 `![图注](图片URL)`

## 多主题切换（多账号共用）

- 每个账号一套配置：`references/themes/<账号名>.json`，结构为 `tokens`（设计令牌）+ `blocks`（语义块样式，用 `@token` 引用）。
- `references/theme.json` 仅作**分发器**（`default_theme` / `available`）。
- 运行时 `-t / --theme <账号名>`；省略用 `default_theme`。
- 新增账号：复制 `themes/xiangxiang.json` 改名，改 `tokens` 数值，加入 `theme.json` 的 `available`。

> 注意：校准风格时写的是 `references/themes/<账号名>.json`，**不是** `theme.json` 本身。`theme.json` 只保留分发器结构。

---

## 目录设计（输出约定）

> 遵循《Skill 统一输出目录规范》`skill-output-convention.md`。`draft_cli.py` 默认输出已改落到统一会话目录（取代旧 `outputs/`）：`~/WorkBuddy/wechat-article-format_{YYYYMMDD-HHMM}/0_draft_<主题>.html`（§1.1 / §6）。`-o/--output` 仍可显式指定路径（便于跨 skill 编排传入上游同一会话目录，§3.4）。

### 输出件登记表（依据本 skill 实际推导）

| 阶段功能名称 | 格式 | 类型 | 说明 | 是否多文件 | 合规命名示例 |
|---|---|---|---|---|---|
| `draft` | html | 文件 | 按账号主题排版的内联样式 HTML（直接粘公众号） | 否 | `0_draft_我的文章.html` |

- 主题取自输入文件名（`args.input` 的 stem）；stdin 时回退 `草稿`。
- 跨 skill：本子 skill 作为 `wechat-article-format` 下游，会话目录前缀沿用 `wechat-article-format`，与 clone 的 `0_clone_*.html` 同目录共存无冲突（stage 名不同）。
- 源草稿（`.md`）只读，不修改 / 不回写。

## 输出约束

- 默认 `inline` 模式：全部使用**内联 style**，不依赖外部 CSS / JS，兼容公众号编辑器。
- `standard` 模式：输出带 `:root` 令牌与语义 class 的标准 HTML（CSS 见 `references/five_step_template.css`），用于本地预览/自托管；class 在微信会失效，**贴公众号请用 inline**。
- 图片宽度 `100%` 自适应，不引入固定宽度导致移动端溢出。
- 默认输出到统一会话目录 `~/WorkBuddy/wechat-article-format_{YYYYMMDD-HHMM}/0_draft_<主题>.html`（取代旧 `outputs/`，遵循规范 §1.1 / §6）；`-o/--output` 可显式指定路径；**绝不写回源文件目录**，源文件只读。

## 与同项目其他子 skill 的关系

- 本 CLI 与 article-format-clone 各自独立产出 HTML，互不 import 内部函数。
- **样式可移植（新增）**：article-format-clone 支持 `--save-theme <名>`，把从参考文章提取的样式归一化为本 skill 同款「设计令牌 + blocks（@token 引用）」主题，直接写入 `references/themes/<名>.json` 并登记进 `theme.json`。随后即可用 `draft_cli.py -t <名>` 复用该风格排版你的草稿。闭环命令见 `references/five_step_method.md` 末节。
- article-format-preview 仅桥接 clone 做动态渲染；draft 产物在统一会话目录下经"已生成文件"模式预览。
