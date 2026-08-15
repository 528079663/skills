# 五步排版法（本 skill 的方法论与决策清单）

本文把「内容解构 → 设计令牌 → CSS 框架 → 内容填充 → 间距校准」标准化，并说明它如何映射到 `article-format-draft` 子 skill。

> ⚠️ 关键约束：微信编辑器会剥掉 `<style>` 与 `class`，只保留标签上的内联 `style`。
> 因此本 skill 的**默认输出是内联样式（inline）**，设计令牌与语义 class 在「标准模式（standard）」里才以 `<style>`/class 形式出现，用于本地预览/自托管。贴公众号请用 inline。

---

## 第一步：内容解构（语义分层）

拿到原始文本，先按语义标签解剖（通读全文，给每段归类）：

| 内容类型 | 语义标签 | 本 skill 写法 | 示例 |
|---|---|---|---|
| 文章主标题 | `H1` | `# 标题` | 「别让这些地方偷走宝宝的专注力」 |
| 作者/引言区 | `.intro` | `::: intro … ::: end` | 「Hi！我是XX妈妈…」（居中、灰色、多行） |
| 一级大板块 | `.section-title` | `::: section … ::: end` | 「一、宝宝10个小动作…」（黄底） |
| 二级分论点 | `.item-title` | `::: item … ::: end` | 「1. 很早就认妈妈」（红色加粗） |
| 普通正文 | `P` | 普通文字（空行分段） | 段落描述（16px、2em 行高） |
| 特殊功能句 | `.action-tip` | `::: action … ::: end` | 「✅ 我的做法是…」 |
| 总结金句 | `.highlight` | `==重点句==` | 黄底高亮 |
| 补充说明 | `.tip-box`（ps） | `::: ps … ::: end` | 「ps：偶尔去一趟…」（左边框块） |
| 引用 | `blockquote` | `> 引用` | 跨多行引用 |
| 引导/装饰图片 | `IMG` | `![图注](url)` | 文首动图、文末 GIF |

> 出现新类型就新增一个标签（如 `.quote` 引用块已内置为 `>`）。

## 第二步：建立设计令牌（Design Tokens）

把颜色/字号/间距/行高提取成固定变量，存于 `references/themes/<账号名>.json` 的 `tokens`。改一个令牌即可全局换肤：

| 令牌 | 取值（示例） | 用途 |
|---|---|---|
| `primary` | `#D92142` | 小标题、对勾、强调文字、边框 |
| `accent` | `#2E81DA` | 引用左边框等强调色 |
| `highlight_bg` | `#FFFB00` | 大标题背景、金句背景 |
| `text` | `#3e3e3e` | 普通正文 |
| `gray` | `#888888` | 作者签名、时间、次要信息 |
| `max_width` | `677px` | 容器最大宽（手机阅读） |
| `base_font` | `16px` | 正文基础字号 |
| `line_height` | `2em` | 全文统一行高 |

`blocks` 内用 `@primary` 引用令牌，渲染时自动替换。

## 第三步：CSS 框架（模块化）

标准模式（standard）的 CSS 在 `references/five_step_template.css`，按功能分模块（容器 / 主标题 / 引言 / 板块 / 分论点 / 对勾建议 / 高亮 / 提示块 / 引用 / 图片 / 分割线 / 签名 / 媒体查询）。所有模块引用 `:root` 令牌，不写死色值。

内联模式（inline，贴微信用）则由 `draft_cli.py` 按 `blocks` 把同等样式展开成每个标签的 `style="..."`——视觉一致，但写法不同。

## 第四步：内容填充（类名映射）

| 语义内容 | 写法 | 标准模式 class |
|---|---|---|
| 主标题 | `# 标题` | `h1.article-title` |
| 引言 | `::: intro` | `div.intro-block` |
| 一级板块 | `::: section` | `div.section-title` |
| 二级分论点 | `::: item` | `div.item-title` |
| 普通段落 | 纯文字 | `p` |
| 带对勾建议 | `::: action` | `p.action-tip`（含 ✅） |
| 金句 | `==文字==` | `span.highlight` |
| 备注块 | `::: ps` | `div.tip-box`（含「ps：」） |
| 图片 | `![图注](url)` | `img.article-img` + `p.img-caption` |

## 第五步：间距校准（呼吸感）

间距规则已固化进 `tokens` 与模板 CSS（均用 `em` 相对单位，随系统字号等比缩放）：

- 段落间距：`body.paragraph_spacing`（默认 1.5em）
- 小标题上方：`section_title.margin` 顶部留白（默认 1.5em）
- 分割线上下：`divider.margin`（默认 2em 0）
- 图片上下：`image_margin`（默认 1em auto）
- 容器左右内边距：PC 24px 20px / 手机 16px 14px（媒体查询）

---

## 通用排版决策清单（速查）

- [ ] **Step 1**：通读全文，切成块（标题/引言/板块/分论点/列表/提示/图片）。
- [ ] **Step 2**：选 1 个主色（`primary`）、1 个强调色（`accent`）、1 个辅助灰（`gray`）——账号主题已配好，可直接用。
- [ ] **Step 3**：内联模式自动应用账号 CSS；若要标准模式预览，加 `--emit standard`。
- [ ] **Step 4**：按映射表给内容挂语义标签（`#`/`::: intro`/`::: section`/`::: item`/`::: action`/`::: ps`/`== ==`/`![ ]`）。
- [ ] **Step 5**：本地/手机预览一次，微调 `tokens` 的间距与字号（移动端由媒体查询自适应）。
- [ ] **贴公众号**：务必用默认 inline 模式输出（class 版贴微信会失效）。

## 命令行速查

```bash
# 默认内联（贴公众号）
python scripts/draft_cli.py 草稿.md -o out.html
python scripts/draft_cli.py 草稿.md -t proluo -o out.html

# 标准模式（本地预览/自托管，令牌+class）
python scripts/draft_cli.py 草稿.md --emit standard -o out.html

# 列出主题
python scripts/draft_cli.py --list-themes
```

---

## 跨子 skill：clone 提取样式 → draft 复用（样式可移植闭环）

五步法的「设计令牌单一真源」不仅服务 draft，**也是 clone 与 draft 的共享词汇表**。因此可以把任意参考文章的排版风格「提取一次、复用到我的草稿」，无需手动抄色值。

> 为什么能互通：clone 提取出的 `st`（扁平字段：`theme_color`/`strong_color`/`body`/`headings`/`quote`/`divider`…）经 `clone_cli.py` 的令牌翻译层归一化为与本 skill **完全同构**的 `tokens`（primary/accent/highlight_bg/text/gray/max_width/base_font/line_height + 间距令牌）+ `blocks`（以 `@token` 引用）。draft 的渲染器直接消费这套 schema，故克隆出的风格可被 draft 一键复用。clone 自身渲染仍走原 `st`，**零保真损失**。

### 一步闭环

```bash
# 1) 从参考文章链接提取风格，存为 draft 主题（自动登记进 theme.json）
python article-format-clone/scripts/clone_cli.py \
    --style "https://mp.weixin.qq.com/s/XXXX" \
    --save-theme myclone --account "竞品A育儿号"

# 2) 立刻用该风格排版我的草稿（内联，贴公众号）
python article-format-draft/scripts/draft_cli.py 我的草稿.md -t myclone -o out.html

# 3) 或本地预览/自托管（标准模式，令牌+class）
python article-format-draft/scripts/draft_cli.py 我的草稿.md -t myclone --emit standard -o out.html
```

- `--save-theme <名>`：必带 `--style`（URL / 本地样式 JSON / 原始 JSON 均可）。会把主题写到 `references/themes/<名>.json`，并在 `references/theme.json` 的 `available`/`themes` 中登记，预览页主题下拉立即可见。
- `--account <标签>`：登记到 theme.json 的账号名（缺省用 `<名>`）。
- 想微调：直接改 `references/themes/<名>.json` 的 `tokens` 数值（如把 `primary` 换成你的品牌色），所有引用处自动换色——这正是「改一个令牌全局生效」。

### 注意事项

- 这是「风格复用」，不是「内容搬运」：克隆出的只是排版令牌（颜色/字号/间距/标题版式），**不含参考账号的文字、引导图、二维码**。
- 若 `--save-theme` 时 `references/themes/` 不可写，会回退写到 `outputs/themes/`，此时需手动把 JSON 挪到 draft 主题目录并登记 theme.json（stderr 会提示）。
- 提取质量取决于 clone 的样式识别（见 clone SKILL.md 的已知限制：个别特殊版式可能需人工在 `tokens` 里校正）。

