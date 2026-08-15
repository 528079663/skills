# article_formate

公众号文章排版 skill 整改后的工程目录（由 `wechat-article-format` 拆分重构而来），**已正式取代 `wechat-article-format`（旧版已废弃、不再维护）**。

## 目录结构

```
article_formate/
├── common/                     # 通用能力层（可独立复用）
│   ├── cli_bridge.py          # 子进程 CLI 桥接（preview → clone，进程级解耦，防命令注入）
│   └── audit.py               # 本地审计日志（JSON Lines，logs/audit.log）
├── article-format-clone/       # 子 skill：HTML 克隆排版 CLI
│   └── scripts/clone_cli.py
├── article-format-draft/        # 子 skill：草稿主题排版 CLI
│   └── scripts/draft_cli.py
├── article-format-preview/      # 子 skill：本地预览服务壳（端口 8004）
│   ├── serve.py
│   ├── preview.html
│   └── start_preview.bat
├── references/                 # 主题配置 + 校准文档（项目私有）
│   ├── themes/                 # 各账号主题 JSON
│   ├── archive/                # 过期文档归档（非删除）
│   ├── theme.json              # 主题分发器
│   ├── input_format.md         # 草稿输入规范（含五步法语义块）
│   ├── five_step_method.md     # 五步排版法方法论与决策清单
│   ├── five_step_template.css  # 标准模式模块 CSS（:root 令牌 + 语义 class）
│   └── style_guide.md
├── outputs/                    # 产物目录
│   ├── styles/                 # 提取的样式 JSON 预设
│   └── *.html / *.md
└── logs/                       # 审计日志（运行时生成）
```

## 设计要点（与原始 skill 的差异）

1. **物理拆分为 3 子 skill + 通用层**：通用能力（Markdown→内联 HTML 引擎 / 样式提取核心 / 预览壳）独立，项目私有配置（账号主题 / 端口 8004 / 引导图 / CLI 桥接）仅留在 `article_formate`。
2. **进程级解耦**：preview 经 `common/cli_bridge` 子进程调用 clone / draft，**禁止 import** 内部函数；参数数组化、禁 `shell=True`、防命令注入。预览页「排版模式」可在 **克隆**（偷参考样式）与 **草稿**（自家主题）间切换，draft 走 `/api/render?mode=draft` + `/api/themes`。
3. **OCR 整改（G4⑨）**：超时 **10s**、失败**重试 2 次**（共 3 次尝试），仍失败 → 跳过该图文 OCR 并按结构启发式降级 + 写审计日志（A010003 / A010004）。
4. **过期文档归档非删除（G4⑦）**：移入 `references/archive/`，绝不做物理删除。
5. **预览端口 8004**：与原始 8001 区分，避免冲突。
6. **预览页排版模式切换**：`动态渲染` 面板内可切「克隆 / 草稿」。草稿模式显式列出 `references/theme.json` 的可用主题（xiangxiang / proluo），纯本地套主题、不联网、不做 OCR、不套他人账号。
7. **五步排版法（draft 子 skill）**：draft 以「设计令牌（tokens）单一真源 + 语义块（intro/section/item/action/ps/footer）」落实五步法。默认 `inline` 输出微信兼容内联样式；`--emit standard` 额外产出带 `:root` 令牌与语义 class 的标准 HTML（本地预览/自托管用，贴微信会失效）。详见 `references/five_step_method.md` 与 `references/input_format.md`。

## 快速开始

```bash
# 克隆排版（给参考链接 → 提取真实样式 → 重排我的文章）
python article_formate/article-format-clone/scripts/clone_cli.py --style <参考URL> --content my.md -o out.html

# 草稿排版（按账号主题套用，内联样式贴公众号）
python article_formate/article-format-draft/scripts/draft_cli.py input.md -o out.html

# 草稿排版 · 标准模式（设计令牌 + 语义 class，本地预览/自托管用）
python article_formate/article-format-draft/scripts/draft_cli.py input.md --emit standard -o out.html

# 样式可移植：从参考文章提取风格 → 存为 draft 主题 → 复用排版我的草稿
python article_formate/article-format-clone/scripts/clone_cli.py --style <参考URL> --save-theme myclone --account "竞品A"
python article_formate/article-format-draft/scripts/draft_cli.py input.md -t myclone -o out.html

# 本地预览（手机外壳 + 动态渲染，端口 8004）
cd article_formate/article-format-preview && python serve.py --open
```

## 本机联网 clone 示例（真实跑一次）

> 路径约定：下文 `<SKILL_DIR>` 指 `article_formate` 自身根目录（user 级 `~/.workbuddy/skills/article_formate`，项目级 `<workspace>/.workbuddy/skills/article_formate`）；`<WECHAT_SKILL_DIR>` 指 `wechat-article-extractor` skill 根目录。在本机把二者展开为 Windows 绝对路径即可（如 `C:/Users/你的用户名/.workbuddy/skills/...`）。

> 预览服务是本地服务，**请在你的本机运行**（隔离环境不要托管）。OCR 统一走**全局 OCR 微服务**（见 `~/.workbuddy/ocr-microservice.md`），不依赖任何单 skill 私有实现。

**方式 A：预览页可视化（推荐）**

```bash
# 1) 确保全局 OCR 微服务就绪（缺失则自动拉起；就绪返回 {"status":"ok"}，用法见 ~/.workbuddy/ocr-microservice.md）
python "<WECHAT_SKILL_DIR>/scripts/ocr_client.py" --ensure   # 统一客户端由 wechat-article-extractor 托管，详见全局文档

# 2) 启动预览服务（自动打开浏览器，端口 8004）
cd "<SKILL_DIR>/article-format-preview"
python serve.py --open
```

打开 http://127.0.0.1:8004/ 后：
- 排版模式选 **克隆** → 在「样式预设」粘贴一篇参考文章 URL 点「提取」→ 在「内容」粘贴/选择你的 Markdown → 自动实时渲染；
- 或排版模式选 **草稿** → 选 `xiangxiang` / `proluo` 主题 → 粘贴 Markdown → 实时渲染。

> **「已生成文件」面板**：切到「已生成文件」标签后，会列出 `outputs/` 下**所有**已生成 HTML（含 `demo_clone/` 子目录示例），每个选项带 `[克隆]`/`[草稿]` 类型标记——克隆产物（文件名含 `clone`）与 `draft_cli` 的草稿产物都在此汇总，点选即预览；「新标签打开」经 `/api/article?file=` 正确渲染（含子目录文件）。归档目录 `references/archive/` 不展示。

**方式 B：CLI 直跑（无需起服务）**

```bash
# 克隆：参考 URL + 我的 Markdown → 产出 HTML
python "<SKILL_DIR>/article-format-clone/scripts/clone_cli.py" \
  --style "https://mp.weixin.qq.com/s/xxxx" --content my_article.md -o out.html

# 草稿：按 xiangxiang 主题套用
python "<SKILL_DIR>/article-format-draft/scripts/draft_cli.py" \
  my_article.md -t xiangxiang -o out.html
```

> 注：clone 的 OCR 增强统一走**全局 OCR 微服务**（见 `~/.workbuddy/ocr-microservice.md`）；若未起，clone 会自动降级（结构启发式 + 审计 A010003/A010004），不影响产出。

## 详细文档

- `article_formate/article-format-clone/SKILL.md`
- `article_formate/article-format-draft/SKILL.md`
- `article_formate/article-format-preview/SKILL.md`

## 依赖

- 渲染 / 提取：beautifulsoup4 + lxml（`pip install beautifulsoup4 lxml`）
- OCR（可选增强）：统一走**全局 OCR 微服务**（见 `~/.workbuddy/ocr-microservice.md`）。
- 预览服务：零依赖（仅 Python 标准库）

## 说明

- 预览服务为本地服务，请在用户本机运行，不要在隔离环境长期托管。
- 源 skill `wechat-article-format` **已废弃**，由本目录（`article_formate`）正式取代，新任务请勿再使用旧目录。
