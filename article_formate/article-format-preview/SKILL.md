---
name: article-format-preview
description: 公众号排版本地预览服务壳（article-format 预览子 skill）。零依赖（仅 Python 标准库）在 iPhone
  外壳中预览 outputs/*clone*.html，并支持"样式预设 + 内容草稿"实时切换渲染（动态渲染模式，经子进程调用
  article-format-clone 完成）。不负责渲染逻辑，仅做预览与接口中转。当用户说"本地预览排版""手机里看看排版效果""起个预览服务"时使用。
agent_created: true
disable-model-invocation: true
---

# 公众号排版本地预览（article-format-preview）

零依赖预览服务壳：手机外壳预览 + 动态渲染。

## 运行环境（固定，最高优先级）

- **Python 解释器（固定）**：`~/.workbuddy/binaries/python\envs\base\Scripts\python.exe`（WorkBuddy base venv）。本预览服务零依赖（仅 Python 标准库 `http.server`），**无需 `pip install`**。
- **运行方式**：预览服务一律在用户本机（Windows）直接前台运行，**不使用隔离 / 沙箱环境**。
- 下文命令中的 `python` 均指上述 base venv 解释器。

## 启动（在本目录执行）

> `<SKILL_DIR>` = 本 skill 根目录（user 级 `~/.workbuddy/skills/article_formate/article-format-preview`，项目级 `<workspace>/.workbuddy/skills/article_formate/article-format-preview`）。

```bash
cd <SKILL_DIR>
python serve.py                  # 默认 http://127.0.0.1:8004/
python serve.py --port 8080     # 自定义端口
python serve.py --no-reload     # 关闭文件改动自动重载
python serve.py --open          # 启动后自动打开默认浏览器
```

- Windows 一键：双击 `start_preview.bat`（等价于 `python serve.py --open`）。
- 热重载：改动 `serve.py` / `clone_cli.py` / `preview.html` 后自动热重载 + 浏览器刷新。

## 解耦说明（重要，系统设计 V2 / P3）

- 本服务进程**禁止 import** clone / draft 内部函数。
- `/api/render` 与 `/api/extract-style` 全部经 `common/cli_bridge` **子进程调用** `article-format-clone/scripts/clone_cli.py` 完成，参数数组化、禁 `shell=True`、禁字符串拼接，防命令注入。
- 渲染 / 提取的真实逻辑在 `clone_cli.py`，本服务只做接口中转与前端托管。

## 预览模式

- **动态渲染**：左侧选"样式预设"+"内容草稿"，实时 `POST /api/render` 重渲并注入手机外壳；支持编辑内容文本框、开关关注卡/点亮图/沿用账号；可填参考文章 URL 点"提取"→ `POST /api/extract-style` 实时写入 `outputs/styles/`。
- **已生成文件**：列 `outputs/*clone*.html` 静态预览。

## 接口

`/api/styles`（列预设）、`/api/contents`（列草稿）、`/api/render`（style+content→HTML 片段）、`/api/extract-style`（URL→存 JSON）、`/api/files`、`/api/article`、`/api/version`（热重载探测）。

## 注意

- 不要直接双击 `preview.html`（`file://`）当动态渲染用：file 页无法访问后端接口，会顶部红条告警请走 `http://127.0.0.1:8004/`。
- 端口固定 **8004**（架构约定，避免与原始 wechat-article-format 的 8001 冲突）。
- 预览服务一律在用户本机（Windows）直接前台运行 `python serve.py`（base venv），**不使用隔离 / 沙箱环境**；后台进程由用户自行管理生命周期。

---

## 目录设计（输出约定）

> 遵循《Skill 统一输出目录规范》`skill-output-convention.md`。本 skill 是**本地预览服务壳**，**不产出文件**——仅在浏览器中渲染 `wechat-article-format_{ts}` 会话目录下的 `*clone*.html`（或经子进程调用 `article-format-clone` 动态渲染）。
> 旧文档中提到的 `outputs/*clone*.html` / `outputs/styles/` 已废止（§6）；实际渲染产物来自 clone / draft 落盘的**统一会话目录** `~/WorkBuddy/wechat-article-format_{ts}/`。

### 输出件登记表

| 阶段功能名称 | 格式 | 类型 | 说明 | 是否多文件 |
|---|---|---|---|---|
| （无） | — | — | 纯预览 / 中转，无文件产物 | — |

- 渲染逻辑在 `article-format-clone/scripts/clone_cli.py`，产物落统一会话目录（见 clone 的「目录设计」章节）。
- 跨 skill：经 `common/cli_bridge` 子进程调用 clone，禁止 import 内部函数（进程级解耦）。
