#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公众号文章排版转换器 CLI（article-format-draft 子 skill，五步排版法版）。

读取按 references/input_format.md 规范写好的轻量标记草稿，结合主题配置，输出 HTML。

两种输出模式（--emit）：
  - inline   （默认）：全部内联 style，微信编辑器零依赖、可直接粘公众号。
  - standard ：输出带 :root 设计令牌 + 语义 class 的标准 HTML（本地预览/自托管用，class 才生效）。

主题均为「设计令牌」单一真源（references/themes/<账号>.json 的 tokens），blocks 内用 @token 引用，
改一个令牌即可全局换色。语义块（intro/section/item/action/ps/footer）对应五步排版法的分层词汇。

主题切换（多账号共用本 skill 时）:
    python draft_cli.py input.md -o out.html                  # 默认主题（内联）
    python draft_cli.py input.md --emit standard -o out.html  # 标准模式
    python draft_cli.py input.md -t proluo -o out.html        # 指定「普罗的小生活」主题
    python draft_cli.py --list-themes                          # 列出全部可用主题

主题配置：references/theme.json 仅作分发器（指明 default_theme），各账号完整配置在 references/themes/<账号名>.json。
"""
import json
import os
import re
import sys
import argparse
import time


# 统一产物根（遵循 Skill 统一输出目录规范 §1.1 / §6：取代旧 outputs/ 模式）
_WORKBUDDY_ROOT = os.path.expanduser("~/WorkBuddy")


def _session_dir(skill: str = "wechat-article-format") -> str:
    """本次会话目录：{skill}_{YYYYMMDD-HHMM}，冲突时追加 -2/-3。"""
    ts = time.strftime("%Y%m%d-%H%M")
    base = os.path.join(_WORKBUDDY_ROOT, "%s_%s" % (skill, ts))
    i = 2
    while os.path.isdir(base):
        base = os.path.join(_WORKBUDDY_ROOT, "%s_%s-%d" % (skill, ts, i))
        i += 1
    return base


def _safe_topic(s: str) -> str:
    """主题做文件系统安全处理（去非法字符/空白、限长）。"""
    return re.sub(r'[\\/:*?"<>|\s]', "_", (s or "草稿"))[:20]


def _force_utf8():
    """强制标准流编码，消除 Windows GBK 下 'gbk codec can't encode character' 崩溃。

    - 管道 / 子进程场景（serve 经 cli_bridge 调用，非 tty）：统一 UTF-8 无损。
    - 交互终端场景（用户直接 python draft_cli.py）：保持系统编码，仅把 errors 改 replace。
    """
    import io
    for name in ("stdin", "stdout", "stderr"):
        s = getattr(sys, name, None)
        if s is None:
            continue
        try:
            if getattr(s, "isatty", None) and s.isatty():
                s.reconfigure(encoding=s.encoding or "utf-8", errors="replace")
            else:
                s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            try:
                buf = getattr(s, "buffer", None)
                if buf is not None:
                    setattr(sys, name, io.TextIOWrapper(buf, encoding="utf-8", errors="replace"))
            except Exception:
                pass


# article_formate/article-format-draft/scripts/draft_cli.py -> parents[3] = article_formate/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REF_DIR = os.path.join(PROJECT_ROOT, "references")
THEME_PATH = os.path.join(REF_DIR, "theme.json")
THEMES_DIR = os.path.join(REF_DIR, "themes")
TEMPLATE_CSS_PATH = os.path.join(REF_DIR, "five_step_template.css")

THEME = {}
TOKENS = {}
BLOCKS = {}
EMIT = "inline"          # inline | standard
DEFAULT_THEME = "xiangxiang"

# 公众号兼容开关：是否给 `##` 小标题自动加圆形数字徽章（按主题开启，默认关）。
# 徽章为 <span> inline-block + border-radius:50%，套 primary 色，符合《排版指南》推荐写法。
HEADING_BADGE = False
_H2_SEQ = 0
# 数字徽章基础样式（颜色在渲染时按 tokens.primary 注入，span 上的圆角公众号支持）。
BADGE_BASE = "display:inline-block;width:30px;height:30px;color:#ffffff;font-size:14px;font-weight:700;text-align:center;line-height:30px;margin-right:10px;border-radius:50%"


# ---------------- 令牌解析 ----------------
def resolve_refs(obj, tokens):
    """把 blocks 里的 @token 替换为 tokens 对应值（递归，支持整串或内嵌，如 "4px solid @accent"）。"""
    if isinstance(obj, str):
        def _repl(m):
            k = m.group(1)
            return tokens.get(k, m.group(0))
        return re.sub(r"@([a-zA-Z_][a-zA-Z0-9_]*)", _repl, obj)
    if isinstance(obj, dict):
        return {k: resolve_refs(v, tokens) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_refs(v, tokens) for v in obj]
    return obj


def build_root(tokens):
    """根据 tokens 生成标准模式用的 :root 变量块。"""
    var_map = {
        "primary": "--primary",
        "accent": "--accent",
        "highlight_bg": "--highlight-bg",
        "text": "--text-color",
        "gray": "--gray",
        "max_width": "--max-width",
        "base_font": "--base-font",
        "line_height": "--line-height",
        "font_family": "--font-family",
    }
    lines = [":root {"]
    for k, v in var_map.items():
        val = tokens.get(k)
        if val:
            lines.append(f"  {v}: {val};")
    lines.append("}")
    return "\n".join(lines)


# 标准模式 CSS 读取失败时的兜底（保证标准模式始终可用，避免与 references 文件强耦合）
FALLBACK_CSS = """
.article-wrap{max-width:677px;margin:0 auto;background:#fff;padding:24px 20px;color:#3e3e3e;box-sizing:border-box;line-height:2em;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif}
.article-wrap p{font-size:16px;line-height:2em;margin:0 0 1em;text-align:justify;color:#3e3e3e}
.article-title{font-size:22px;font-weight:700;color:var(--primary);text-align:center;border-bottom:1px solid #e7e7eb;padding-bottom:10px;margin:0 0 1em}
.sub-title{font-size:18px;font-weight:700;color:var(--primary);margin:1.1em 0 .5em}
.h-badge{display:inline-block;width:30px;height:30px;background:var(--primary);color:#fff;font-size:14px;font-weight:700;text-align:center;line-height:30px;margin-right:10px;border-radius:50%}
.sub-sub{font-size:16px;font-weight:700;color:#3e3e3e;margin:1em 0 .4em}
.intro-block{text-align:center;font-size:15px;color:var(--gray);letter-spacing:2px;line-height:2em;margin:0 0 1.2em}
.section-title{font-weight:700;background:var(--highlight-bg);color:#3e3e3e;display:inline-block;padding:0 6px;margin:1.5em 0 .6em;font-size:18px}
.item-title{font-weight:700;color:var(--primary);margin:1.2em 0 .4em;font-size:16px}
.action-tip{color:var(--primary);margin:1.2em 0;line-height:1.8;font-size:16px}.action-tip .check{margin-right:6px}
.highlight{background:var(--highlight-bg);font-weight:700;padding:0 4px;color:#3e3e3e}
.tip-box{background:#f7f8fa;border-left:4px solid var(--primary);padding:14px 18px;margin:1.5em 0;font-size:15px;line-height:1.7;color:#3e3e3e}
.quote-block{background:rgba(81,151,248,.13);border-left:4px solid var(--accent);padding:14px 16px;border-radius:8px;margin:1.5em 0;color:#3e3e3e}
.callout{padding:12px 16px;border-radius:6px;margin:1.2em 0;font-size:15px;line-height:1.7}.callout-tip{background:rgba(81,151,248,.13);color:var(--accent)}.callout-warning{background:rgba(217,33,66,.1);color:var(--primary)}.callout-info{background:#f5f6f8;color:#5a5a5a}
.article-img{width:100%;border-radius:6px;display:block;margin:1em auto}.img-caption{color:var(--gray);font-size:14px;text-align:center;margin:.4em 0 1.2em}
.divider{border:none;border-top:1px solid #e3e3e3;margin:2em 0}
.article-footer{margin-top:28px;padding-top:18px;border-top:1px solid #eee;text-align:center;font-size:14px;color:var(--gray)}
.article-wrap ul,.article-wrap ol{padding-left:1.4em;margin:1em 0;color:#3e3e3e}.article-wrap li{margin:0 0 .5em;line-height:2em}
.article-wrap strong{color:var(--primary);font-weight:700}.article-wrap em{font-style:italic}.article-wrap code{background:#f2f2f2;padding:2px 6px;border-radius:4px;font-size:90%;color:#c7254e}
@media (max-width:640px){.article-wrap{padding:16px 14px}.article-title{font-size:20px}}
"""


# ---------------- 主题加载 ----------------
def _load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_dispatch():
    d = _load_json(THEME_PATH)
    if isinstance(d, dict) and ("default_theme" in d or "available" in d):
        return d
    return None


def theme_names():
    names = []
    disp = load_dispatch()
    if disp:
        names = list(disp.get("available", []))
        if not names and disp.get("default_theme"):
            names = [disp["default_theme"]]
    if os.path.isdir(THEMES_DIR):
        for fn in sorted(os.listdir(THEMES_DIR)):
            if fn.endswith(".json"):
                nm = fn[:-5]
                if nm not in names:
                    names.append(nm)
    if not names:
        d = _load_json(THEME_PATH)
        if isinstance(d, dict) and "body" in d:
            names = ["default"]
    return names


def resolve_theme_path(name):
    p = os.path.join(THEMES_DIR, f"{name}.json")
    if os.path.isfile(p):
        return p
    if name in ("default", "theme.json"):
        d = _load_json(THEME_PATH)
        if isinstance(d, dict) and "body" in d:
            return THEME_PATH
    return None


def load_theme(name=None):
    if name is None:
        disp = load_dispatch()
        name = disp.get("default_theme", DEFAULT_THEME) if disp else DEFAULT_THEME
    path = resolve_theme_path(name)
    if path:
        return _load_json(path) or {}
    return {}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def css(**kw):
    parts = []
    for k, v in kw.items():
        if v is None or v == "":
            continue
        parts.append(f"{k.replace('_', '-')}:{v}")
    return ";".join(parts)


def card_style(block, **overrides):
    """生成 blockquote 卡片内联样式。

    公众号对 `<section>` 完全过滤、对 `<div>` 卡片会丢背景/边距，故卡片统一用 `<blockquote>`；
    同时《排版指南》禁止卡片（div/卡片容器）上的 border-radius，这里直接丢弃该键，其余原样。
    """
    d = dict(block or {})
    d.pop("border_radius", None)
    d.pop("box_shadow", None)
    d.update(overrides)
    return css(**{k: v for k, v in d.items() if v not in (None, "")})


def inline(text):
    """处理行内强调：代码 -> 高亮 -> 加粗 -> 斜体。按 EMIT 决定输出内联 style 还是语义 class。"""
    t = esc(text)
    mark = BLOCKS.get("mark") or {}
    mark_bg = mark.get("bg")
    mark_color = mark.get("color")
    strong_color = BLOCKS.get("strong")
    if EMIT == "standard":
        t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
        if mark_bg:
            t = re.sub(r"==([^=]+)==", r'<span class="highlight">\1</span>', t)
        t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", t)
        return t
    # inline 模式：每个强调挂 style
    t = re.sub(
        r"`([^`]+)`",
        lambda m: f'<code style="{css(background="#f2f2f2", padding="2px 6px", border_radius="4px", font_size="90%", color="#c7254e")}">{m.group(1)}</code>',
        t,
    )
    if mark_bg:
        t = re.sub(
            r"==([^=]+)==",
            lambda m: f'<span style="{css(background=mark_bg, color=mark_color, font_weight="bold", padding="2px 4px", border_radius="3px")}">{m.group(1)}</span>',
            t,
        )
    if strong_color:
        t = re.sub(
            r"\*\*([^*]+)\*\*",
            lambda m: f'<strong style="{css(color=strong_color, font_weight="bold")}">{m.group(1)}</strong>',
            t,
        )
    else:
        t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", t)
    return t


def wrap_h(tag, content, h, cls):
    inner = inline(content)
    if EMIT == "standard":
        return f'<{tag} class="{cls}">{inner}</{tag}>'
    style = css(
        font_size=h.get("font_size"),
        color=h.get("color"),
        font_weight=h.get("font_weight", "bold"),
        text_align=h.get("text_align"),
        margin=h.get("margin"),
        padding=h.get("padding"),
        padding_left=h.get("padding_left"),
        padding_bottom=h.get("padding_bottom"),
        border_left=h.get("border_left"),
        border_top=h.get("border_top"),
        border_bottom=h.get("border_bottom"),
        background=h.get("background"),
        border_radius=h.get("border_radius"),
        display=h.get("display"),
        box_sizing=h.get("box_sizing"),
        line_height=h.get("line_height"),
    )
    return f'<{tag} style="{style}">{inner}</{tag}>'


def render_h2_badge(content, h):
    """带圆形数字徽章的 h2（仅 inline 模式用；徽章为 span，公众号支持）。"""
    global _H2_SEQ
    badge = f'<span style="{BADGE_BASE};background:{TOKENS.get("primary", "#8d6e63")}">{_H2_SEQ}</span>'
    hstyle = css(
        font_size=h.get("font_size"),
        color=h.get("color"),
        font_weight=h.get("font_weight", "bold"),
        text_align=h.get("text_align"),
        margin=h.get("margin"),
        padding=h.get("padding"),
        padding_left=h.get("padding_left"),
        border_left=h.get("border_left"),
        border_top=h.get("border_top"),
        border_bottom=h.get("border_bottom"),
        background=h.get("background"),
        display=h.get("display"),
        box_sizing=h.get("box_sizing"),
        line_height=h.get("line_height"),
    )
    return f'<h2 style="{hstyle}">{badge}{inline(content)}</h2>'


def render_paragraph(text):
    b = BLOCKS.get("body", {})
    inner = inline(text).replace("\n", "<br>")
    if EMIT == "standard":
        return f"<p>{inner}</p>"
    style = css(
        font_size=b.get("font_size"),
        color=b.get("color"),
        line_height=b.get("line_height"),
        letter_spacing=b.get("letter_spacing"),
        text_align=b.get("text_align", "justify"),
        margin=f'0 0 {b.get("paragraph_spacing", "1.2em")}',
    )
    return f'<p style="{style}">{inner}</p>'


def render_quote(text):
    q = BLOCKS.get("quote", {})
    inner = inline(text).replace("\n", "<br>")
    if EMIT == "standard":
        return f'<blockquote class="quote-block">{inner}</blockquote>'
    # 公众号兼容：卡片统一用 <blockquote>（section 会被过滤，div 会丢背景/边距）
    style = card_style(q, margin=q.get("margin", "1.5em 0"), font_size=q.get("font_size"))
    return f'<blockquote style="{style}">{inner}</blockquote>'


def render_list(items, ordered):
    l = BLOCKS.get("list", {})
    tag = "ol" if ordered else "ul"
    if EMIT == "standard":
        lis = "".join(f"<li>{inline(it)}</li>" for it in items)
        return f'<{tag}>{lis}</{tag}>'
    style = css(padding_left="1.4em", margin="1em 0", color=l.get("color"))
    li_style = css(
        margin=f'0 0 {l.get("item_spacing", "0.4em")}',
        line_height=BLOCKS.get("body", {}).get("line_height"),
    )
    lis = "".join(f'<li style="{li_style}">{inline(it)}</li>' for it in items)
    return f'<{tag} style="{style}">{lis}</{tag}>'


def render_image(caption, url):
    ic = BLOCKS.get("image", {})
    if EMIT == "standard":
        img = f'<img class="article-img" src="{url}" alt="{esc(caption)}">'
        cap = f'<p class="img-caption">{esc(caption)}</p>' if caption else ""
        return img + cap
    img_style = css(
        width="100%",
        border_radius=ic.get("radius"),
        display="block",
        margin="0.5em 0",
    )
    img = f'<img src="{url}" style="{img_style}" alt="{esc(caption)}">'
    cap = ""
    if caption:
        cap_style = css(
            color=ic.get("caption_color"),
            font_size=ic.get("caption_size"),
            text_align=ic.get("caption_align", "center"),
            letter_spacing=ic.get("caption_letter_spacing"),
            margin="0.4em 0 1.2em",
        )
        cap = f'<p style="{cap_style}">{esc(caption)}</p>'
    return img + cap


def render_callout(kind, text):
    c = BLOCKS.get("callout_" + kind, {})
    label = {"tip": "💡 提示", "warning": "⚠️ 注意", "info": "ℹ️ 说明"}.get(kind, "")
    inner = (f"<strong>{label}</strong><br>" if label else "") + inline(text).replace("\n", "<br>")
    if EMIT == "standard":
        return f'<div class="callout callout-{kind}">{inner}</div>'
    # 公众号兼容：卡片用 <blockquote>，左侧色条取自提示色，去掉圆角
    col = c.get("color")
    style = css(
        background=c.get("bg"),
        color=col,
        border_left=f"4px solid {col}" if col else None,
        padding="14px 18px",
        margin="1.2em 0",
        font_size="15px",
        line_height="1.7",
    )
    return f'<blockquote style="{style}">{inner}</blockquote>'


def render_intro(text):
    b = BLOCKS.get("intro", {})
    inner = inline(text).replace("\n", "<br>")
    if EMIT == "standard":
        return f'<div class="intro-block">{inner}</div>'
    # 公众号兼容：钩子/引言区用 <blockquote>，背景与边距得以保留
    style = card_style(b)
    return f'<blockquote style="{style}">{inner}</blockquote>'


def render_section_title(text):
    b = BLOCKS.get("section_title", {})
    inner = inline(text)
    if EMIT == "standard":
        return f'<h2 class="section-title">{inner}</h2>'
    # 公众号兼容：大板块标题用原生 <h2>（完全支持，背景/边距不丢）
    style = css(
        background=b.get("background"),
        color=b.get("color"),
        font_weight=b.get("font_weight", "bold"),
        display=b.get("display"),
        padding=b.get("padding"),
        margin=b.get("margin"),
        font_size=b.get("font_size"),
        line_height=b.get("line_height"),
    )
    return f'<h2 style="{style}">{inner}</h2>'


def render_item_title(text):
    b = BLOCKS.get("item_title", {})
    inner = inline(text)
    if EMIT == "standard":
        return f'<h3 class="item-title">{inner}</h3>'
    # 公众号兼容：分论点标题用原生 <h3>
    style = css(
        color=b.get("color"),
        font_weight=b.get("font_weight", "bold"),
        font_size=b.get("font_size"),
        margin=b.get("margin"),
    )
    return f'<h3 style="{style}">{inner}</h3>'


def render_action_tip(text):
    b = BLOCKS.get("action_tip", {})
    inner = inline(text).replace("\n", "<br>")
    if EMIT == "standard":
        return f'<p class="action-tip"><span class="check">✅</span>{inner}</p>'
    # 公众号兼容：建议卡片用 <blockquote>，保留背景/左边框
    style = card_style(b, padding=b.get("padding", "12px 16px"))
    return f'<blockquote style="{style}"><span style="margin-right:6px">✅</span>{inner}</blockquote>'


def render_tip_box(text):
    b = BLOCKS.get("tip_box", {})
    inner = inline(text).replace("\n", "<br>")
    if EMIT == "standard":
        return f'<div class="tip-box"><strong>ps：</strong>{inner}</div>'
    # 公众号兼容：备注卡片用 <blockquote>（div 会丢背景/左边框）
    style = card_style(b)
    return f'<blockquote style="{style}"><strong>ps：</strong>{inner}</blockquote>'


def render_footer(text):
    b = BLOCKS.get("footer", {})
    inner = inline(text).replace("\n", "<br>")
    if EMIT == "standard":
        return f'<div class="article-footer">{inner}</div>'
    # 公众号兼容：签名区用 <blockquote>，上边框与居中保留
    style = card_style(b)
    return f'<blockquote style="{style}">{inner}</blockquote>'


def is_block_start(line):
    s = line.strip()
    if s.startswith("## ") or s.startswith("# ") or s.startswith("### "):
        return True
    if s == "---":
        return True
    if s.startswith("> "):
        return True
    if re.match(r"^[-*]\s+", s):
        return True
    if re.match(r"^\d+\.\s+", s):
        return True
    if re.match(r"^!\[", s):
        return True
    if re.match(r"^:::", s):
        return True
    return False


def render(text):
    global _H2_SEQ
    _H2_SEQ = 0
    lines = text.split("\n")
    out = []
    i = 0
    n = len(lines)
    while i < n:
        raw = lines[i].rstrip()
        if raw.strip() == "":
            i += 1
            continue
        # 分割线
        if raw.strip() == "---":
            d = BLOCKS.get("divider", {})
            if EMIT == "standard":
                out.append('<hr class="divider">')
            else:
                out.append(
                    f'<hr style="{css(border="none", border_top=d.get("border_top", "1px solid #eaeaea"), margin=d.get("margin", "2em 0"))}">'
                )
            i += 1
            continue
        # 标题
        if raw.startswith("### "):
            out.append(wrap_h("h3", raw[4:], BLOCKS.get("h3", {}), "sub-sub"))
            i += 1
            continue
        if raw.startswith("## "):
            content = raw[3:]
            if HEADING_BADGE:
                _H2_SEQ += 1
                if EMIT == "standard":
                    out.append(f'<h2 class="sub-title"><span class="h-badge">{_H2_SEQ}</span>{inline(content)}</h2>')
                else:
                    out.append(render_h2_badge(content, BLOCKS.get("h2", {})))
            else:
                out.append(wrap_h("h2", content, BLOCKS.get("h2", {}), "sub-title"))
            i += 1
            continue
        if raw.startswith("# "):
            out.append(wrap_h("h1", raw[2:], BLOCKS.get("h1", {}), "article-title"))
            i += 1
            continue
        # 图片
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", raw)
        if m:
            out.append(render_image(m.group(1), m.group(2)))
            i += 1
            continue
        # 语义块 / 提示框（::: family）
        cm = re.match(r"^:::\s*(tip|warning|info|intro|section|item|action|ps|footer)\s*$", raw.strip())
        if cm:
            kind = cm.group(1)
            buf = []
            i += 1
            while i < n and lines[i].strip() not in ("::: end", ":::"):
                buf.append(lines[i])
                i += 1
            i += 1  # 跳过结束标记
            content = "\n".join(buf)
            if kind in ("tip", "warning", "info"):
                out.append(render_callout(kind, content))
            elif kind == "intro":
                out.append(render_intro(content))
            elif kind == "section":
                out.append(render_section_title(content))
            elif kind == "item":
                out.append(render_item_title(content))
            elif kind == "action":
                out.append(render_action_tip(content))
            elif kind == "ps":
                out.append(render_tip_box(content))
            elif kind == "footer":
                out.append(render_footer(content))
            continue
        # 引用
        if raw.startswith("> "):
            buf = []
            while i < n and lines[i].startswith("> "):
                buf.append(lines[i][2:])
                i += 1
            out.append(render_quote("\n".join(buf)))
            continue
        # 无序列表
        if re.match(r"^[-*]\s+", raw):
            buf = []
            while i < n and re.match(r"^[-*]\s+", lines[i]):
                buf.append(re.sub(r"^[-*]\s+", "", lines[i]))
                i += 1
            out.append(render_list(buf, ordered=False))
            continue
        # 有序列表
        if re.match(r"^\d+\.\s+", raw):
            buf = []
            while i < n and re.match(r"^\d+\.\s+", lines[i]):
                buf.append(re.sub(r"^\d+\.\s+", "", lines[i]))
                i += 1
            out.append(render_list(buf, ordered=True))
            continue
        # 段落：收集到空行或块起点
        buf = [raw]
        i += 1
        while i < n and lines[i].strip() != "" and not is_block_start(lines[i]):
            buf.append(lines[i])
            i += 1
        out.append(render_paragraph("\n".join(buf)))
    return "\n".join(out)


def build_standard_doc(content, tokens):
    root = build_root(tokens)
    try:
        with open(TEMPLATE_CSS_PATH, encoding="utf-8") as f:
            tpl = f.read()
    except Exception:
        tpl = FALLBACK_CSS
    style = root + "\n" + tpl
    return (
        '<!DOCTYPE html><html lang="zh-CN"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<style>{style}</style></head>'
        f'<body><div class="article-wrap">{content}</div></body></html>'
    )


def _fmt_err(e):
    if isinstance(e, ValueError):
        return "主题或参数解析失败：" + str(e)
    if isinstance(e, KeyError):
        return "主题数据不完整（可能主题 JSON 字段缺失）：" + str(e)
    if isinstance(e, OSError):
        return "文件读写失败：" + str(e)
    return type(e).__name__ + ": " + str(e)


def main():
    global THEME, TOKENS, BLOCKS, EMIT
    _force_utf8()
    p = argparse.ArgumentParser(description="公众号文章排版转换器（article-format-draft，五步排版法版）")
    p.add_argument("input", nargs="?", help="输入草稿文件（.md 风格）")
    p.add_argument("-o", "--output", help="输出 HTML 文件路径；默认 = 统一会话根 ~/WorkBuddy\\wechat-article-format_{YYYYMMDD-HHMM}\\0_draft_<主题>.html")
    p.add_argument("-t", "--theme", help="选择主题：xiangxiang / proluo（省略时用默认主题）")
    p.add_argument("--emit", choices=["inline", "standard"], default="inline",
                   help="输出模式：inline=微信内联样式（默认）；standard=设计令牌+语义 class 标准 HTML（本地预览/自托管）")
    p.add_argument("--list-themes", action="store_true", help="列出可用主题后退出")
    args = p.parse_args()

    EMIT = args.emit

    if args.list_themes:
        names = theme_names()
        default = load_dispatch().get("default_theme", DEFAULT_THEME) if load_dispatch() else DEFAULT_THEME
        print("可用主题：")
        for nm in names:
            tag = "  (默认)" if nm == default else ""
            print(f"  - {nm}{tag}")
        return

    if args.theme and args.theme not in theme_names():
        print(f"错误：未知主题 '{args.theme}'。可用主题：{', '.join(theme_names())}", file=sys.stderr)
        sys.exit(1)

    try:
        THEME = load_theme(args.theme)
        TOKENS = THEME.get("tokens", {})
        BLOCKS = resolve_refs(THEME.get("blocks", {}), TOKENS)
        global HEADING_BADGE
        HEADING_BADGE = bool(THEME.get("heading_badge", False))

        if args.input:
            with open(args.input, encoding="utf-8") as f:
                text = f.read()
        else:
            text = sys.stdin.read()

        html = render(text)
        if EMIT == "standard":
            full = build_standard_doc(html, TOKENS)
        else:
            page = THEME.get("page", {})
            body = BLOCKS.get("body", {})
            # 公众号兼容：外层容器用 <div>（section 会被过滤）；补齐 padding/居中/行高，对齐《排版指南》模板
            wrapper = css(
                font_family=page.get("font_family"),
                background=page.get("background", "#ffffff"),
                color=body.get("color"),
                max_width=page.get("max_width", "640px"),
                margin=page.get("margin", "0 auto"),
                padding=page.get("padding", "24px 18px"),
                line_height=page.get("line_height", body.get("line_height")),
                letter_spacing=page.get("letter_spacing", "0.03em"),
                font_size=page.get("font_size", body.get("font_size")),
            )
            full = f'<div style="{wrapper}">\n{html}\n</div>'

        if args.output:
            out_path = args.output
        else:
            # 默认落到统一会话目录（规范 §1.1），命名 0_draft_<主题>.html（§2.4）
            topic = _safe_topic(os.path.splitext(os.path.basename(args.input or "草稿"))[0])
            out_path = os.path.join(_session_dir("wechat-article-format"), "0_draft_%s.html" % topic)
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(full)
        print(f"已生成：{out_path}")
    except SystemExit:
        raise
    except Exception as e:
        print("ERROR: " + _fmt_err(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
