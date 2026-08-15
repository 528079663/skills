# -*- coding: utf-8 -*-
"""公众号 HTML 克隆排版 CLI（article-format-clone 子 skill）。

从参考文章链接提取真实样式，再按该样式重排「我的文章」，输出内联样式 HTML，可直接粘公众号。
本文件由 wechat-article-format 的 scripts/clone_style.py 整改移植而来，逻辑保持不变，仅做以下适配：
  1. 工程位置：article_formate/article-format-clone/scripts/clone_cli.py；
  2. --style 支持三种形式：URL / data/styles 下文件名 / 原始 JSON 字符串（供 preview 子进程调用）；
  3. --dump-style 把提取到的样式 JSON 输出到 stdout（供 /api/extract-style 捕获后落盘）；
  4. OCR 调用按 G4⑨：超时 10s、失败重试 2 次（共 3 次尝试）、仍失败则跳过该图文 OCR 并写审计日志（A010003 / A010004），经 common/audit 落盘；
  5. 基础能力已委托元 skill：网页抓取 / 图片下载 / 图片本地化 -> meta-web-fetch；样式提取（含引导图 OCR 判定）-> meta-style-extract。
     本文件仅保留渲染引擎、内容解析、引导图素材库与 --save-theme 归一化闭环等独有逻辑，不再自行实现上述基础件。

依赖：beautifulsoup4 + lxml（标准库之外唯一依赖）。
用法：
  python clone_cli.py --style <风格参考URL> --content <我的文章URL|文件|- > -o out.html
  python clone_cli.py --style <URL> --content article.md -o out.html
  cat draft.md | python clone_cli.py --style <URL> -o out.html
  python clone_cli.py --style <URL> --dump-style        # 仅打印提取到的样式 JSON（调试 / 供 preview 调用）
"""
import sys, os, re, json, argparse, urllib.request, html, time, hashlib, random, shutil
from io import BytesIO
from bs4 import BeautifulSoup

# ---- 项目根与 common 路径（article_formate/）----
# article_formate/article-format-clone/scripts/clone_cli.py -> parents[3] = article_formate/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COMMON_DIR = os.path.join(PROJECT_ROOT, "common")
if COMMON_DIR not in sys.path:
    sys.path.insert(0, COMMON_DIR)
try:
    import audit
except Exception:
    audit = None

# —— 委托元 skill 实现（article_formate 不再自行实现这些基础能力）——
# 网页抓取 / 图片下载 / 图片本地化 -> meta-web-fetch
# 样式提取（含引导图 OCR 判定）-> meta-style-extract
SKILLS_DIR = os.path.dirname(PROJECT_ROOT)  # -> .../.workbuddy/skills
_META_WEB_FETCH = os.path.join(SKILLS_DIR, "meta-web-fetch", "scripts")
if _META_WEB_FETCH not in sys.path:
    sys.path.insert(0, _META_WEB_FETCH)
from core import (fetch, load, fetch_image, _localize_images,
                  _ext_from_data, _WX_REFERER, _IMG_SRC_RE)
_META_STYLE = os.path.join(SKILLS_DIR, "meta-style-extract", "scripts")
if _META_STYLE not in sys.path:
    sys.path.insert(0, _META_STYLE)
from extract_api import extract_style


# ═══════════════════ 统一会话目录（Skill 输出目录规范）══════════════════
# 产物统一根：~/WorkBuddy；会话目录 {skill}_{YYYYMMDD-HHMM}。
# 本子 skill 的对外入口为 wechat-article-format，故默认会话目录前缀用 wechat-article-format。
WORKBUDDY_ROOT = os.path.expanduser("~/WorkBuddy")


def _session_dir(skill="wechat-article-format"):
    """本次会话目录：{skill}_{YYYYMMDD-HHMM}，冲突时追加 -2/-3。"""
    ts = time.strftime("%Y%m%d-%H%M")
    base = os.path.join(WORKBUDDY_ROOT, "%s_%s" % (skill, ts))
    i = 2
    while os.path.isdir(base):
        base = os.path.join(WORKBUDDY_ROOT, "%s_%s-%d" % (skill, ts, i))
        i += 1
    return base


def _safe_slug(s):
    """主题做文件系统安全处理（去非法字符/空白、限长）。"""
    return re.sub(r'[\\/:*?"<>|\s]', "_", s or "我的文章")[:20]


def _derive_topic(args):
    """从 --content / --style 推导简短主题（用于产物命名）。"""
    c = args.content or ""
    if c and not c.startswith(("http://", "https://", "-")):
        return os.path.splitext(os.path.basename(c))[0]
    if args.style and args.style.startswith(("http://", "https://")):
        return hashlib.md5(args.style.encode("utf-8")).hexdigest()[:12]
    return "我的文章"


# 引导类图片关键词：只有 OCR 命中这些词，才判定为"可采用的引导图"
GUIDE_LIGHTUP_KW = ["在看", "点赞", "点亮", "分享", "星标", "收藏", "转发", "喜欢", "看一看", "在看"]
GUIDE_FOLLOW_KW = ["关注", "公众号", "订阅", "设为星标", "星标", "蓝字"]
GUIDE_QR_KW = ["二维码", "扫码", "长按识别", "名片", "识别二维码"]



# ---------------- 引导图素材库（按参考账号分档，供无图时随机复用） ----------------
# 只有 OCR 识别通过的通用引导图（follow 关注图 / end 点亮图）才入库；二维码名片、原号 CTA 一律不入。
# 目录结构：data/guide_library/<账号键>/{follow,end}/<md5>.<ext>
# （持久素材库属 skill 长期数据，迁出 outputs/ 到 data/，遵循 Skill 统一输出目录规范 §1.1）
GUIDE_LIB_DIR = os.path.join(PROJECT_ROOT, "data", "guide_library")
_ACCT_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_GUIDE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")


def _account_key(st, style_url=""):
    """素材库分档键：优先参考账号昵称，其次 style URL 摘要，最后 default。"""
    try:
        nick = (st.get("follow") or {}).get("nickname", "") or ""
    except Exception:
        nick = ""
    nick = _ACCT_ILLEGAL.sub("_", nick).strip().strip(".")
    if nick:
        return nick[:60]
    if style_url:
        return "url_" + hashlib.md5(style_url.encode("utf-8")).hexdigest()[:12]
    return "default"


def save_guide_to_library(account_key, kind, url):
    """把 OCR 识别通过的通用引导图（kind: follow/end）下载存入按账号分档的素材库。
    已存在则跳过；下载/落盘失败不抛异常（返回 None，不影响主流程）。返回落盘路径或 None。"""
    if not url or url.startswith("data:") or not url.startswith("http"):
        return None
    d = os.path.join(GUIDE_LIB_DIR, account_key, kind)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None
    try:
        data = fetch_image(url, referer=_WX_REFERER)
    except Exception as e:
        print(f"[warn] 引导图入库下载失败，跳过：{url[:50]} ({e})", file=sys.stderr)
        return None
    ext = _ext_from_data(data, url)
    fn = hashlib.md5(url.encode("utf-8")).hexdigest()[:16] + ext
    fp = os.path.join(d, fn)
    if os.path.exists(fp):
        return fp
    try:
        with open(fp, "wb") as f:
            f.write(data)
    except OSError:
        return None
    print(f"[info] 引导图已入库：{account_key}/{kind}/{fn}", file=sys.stderr)
    return fp


def pick_random_guide(account_key, kind):
    """从按账号分档的素材库随机取一张引导图本地路径；档不存在或为空返回 None。"""
    d = os.path.join(GUIDE_LIB_DIR, account_key, kind)
    if not os.path.isdir(d):
        return None
    cands = [os.path.join(d, fn) for fn in os.listdir(d)
             if fn.lower().endswith(_GUIDE_EXTS)]
    return random.choice(cands) if cands else None


def _copy_into_images(src_path, images_dir, prefix):
    """把库里的图复制进产物 images 目录，返回相对 prefix 路径（保持产物自包含）。
    复制失败则退回源绝对路径（至少本地可看）。"""
    try:
        os.makedirs(images_dir, exist_ok=True)
    except OSError:
        return src_path
    fn = os.path.basename(src_path)
    dst = os.path.join(images_dir, fn)
    if not os.path.exists(dst):
        try:
            shutil.copyfile(src_path, dst)
        except OSError:
            return src_path
    return prefix + "/" + fn






def style_to_dict(s):
    d = {}
    if not s:
        return d
    for part in s.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def dict_to_style(d):
    return "; ".join(f"{k}: {v}" for k, v in d.items() if v)



# 标题分组签名：只用"能区分版式"的维度子集（排除 font-family/letter-spacing/margin），
# 避免字体微差、引用块 margin 等把同一套标题拆成多套（之前"精确签名"误拆的根因）。
SIG_KEYS = ["font-size", "color", "font-weight", "background-color", "border-top",
            "border-left", "border", "display", "text-align", "padding", "border-radius"]


def norm_sig(d):
    """标题版式分组签名（去重，非聚类）：只取 SIG_KEYS 子集，规范化后拼接。"""
    return "|".join(f"{k}={d.get(k, '')}" for k in SIG_KEYS)


def css(**kw):
    return "; ".join(f"{k.replace('_', '-')}: {v}" for k, v in kw.items() if v)


def _px(v):
    m = re.search(r"(\d+(?:\.\d+)?)px", v or "")
    return float(m.group(1)) if m else 0.0


def _to_rgb(c):
    if not c:
        return None
    c = c.replace(" ", "")
    if c.startswith("#"):
        h = c[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        try:
            return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return None
    m = re.findall(r"\d+", c)
    if len(m) >= 3:
        return (int(m[0]), int(m[1]), int(m[2]))
    return None


# ---------------- 样式提取（schema 驱动：规划定维度 → 统一遍历抽全 → 字段派生） ----------------
    return out


    return False










# ---------------- 内容解析 ----------------
def parse_inline(el, st):
    out = []
    for child in el.children:
        if getattr(child, "name", None) is None:
            out.append(str(child))
            continue
        name = child.name
        if name in ("strong", "b"):
            out.append(f'<strong style="{css(color=st["strong_color"], font_weight="bold")}">{parse_inline(child, st)}</strong>')
        elif name in ("em", "i"):
            out.append(f'<em>{parse_inline(child, st)}</em>')
        elif name == "span":
            sd = style_to_dict(child.get("style", ""))
            if sd.get("background-color") or sd.get("background"):
                mb = st.get("mark_bg")
                if mb:
                    out.append(f'<span style="{css(background=mb, color=st.get("mark_color"))}">{parse_inline(child, st)}</span>')
                else:
                    out.append(f'<span style="{dict_to_style(sd)}">{parse_inline(child, st)}</span>')
            else:
                out.append(f'<span>{parse_inline(child, st)}</span>')
        elif name == "a":
            href = child.get("href", "#")
            out.append(f'<a href="{href}" style="{css(color=st.get("theme_color", st.get("strong_color")))}">{parse_inline(child, st)}</a>')
        elif name == "br":
            out.append("<br>")
        elif name == "img":
            src = child.get("data-src") or child.get("src") or ""
            out.append(f'<img src="{src}" style="max-width:100%;display:block;margin:1em auto">')
        else:
            out.append(parse_inline(child, st))
    return "".join(out)


def match_heading_variant(el, st, state):
    """内容标题按"在内容里出现的先后"映射到参考文章的多套版式。"""
    sd = style_to_dict(el.get("style", ""))
    sig = norm_sig(sd)
    order = state["order"]
    if sig not in order:
        order[sig] = len(order)
    rank = order[sig]
    if not st["headings"]:
        return None
    return min(rank, len(st["headings"]) - 1)


def _content_heading_type(el, body_size):
    p = el
    while p is not None:
        if p.name == "p":
            return None
        p = p.parent
    sd = style_to_dict(el.get("style", ""))
    bg = sd.get("background-color") or sd.get("background") or ""
    bgc = bg.replace(" ", "")
    transparent = "rgba(0,0,0,0)" in bgc or "transparent" in bgc
    strong = bool((bg and not transparent) or sd.get("border-top")
                  or sd.get("border-left") or sd.get("display") == "inline-block")
    col = sd.get("color")
    col_rgb = _to_rgb(col) if col else None
    bold = sd.get("font-weight") in ("bold", "600", "700", "bolder")
    big = _px(sd.get("font-size")) > _px(body_size) + 1
    if strong:
        return "tag"
    if (col_rgb and col_rgb != (0, 0, 0) and (bold or len(el.get_text(strip=True)) <= 16)) or (bold and big):
        return "colored"
    return None


def _walk_content(node, st, blocks, state):
    for child in list(node.children):
        name = getattr(child, "name", None)
        if name is None:
            continue
        if name == "img":
            src = child.get("data-src") or child.get("src") or ""
            if src:
                blocks.append(("image", src, child.get("alt", "")))
            continue
        if name in ("hr",):
            blocks.append(("divider",))
            continue
        if name in ("ul", "ol"):
            items = [li.get_text(" ", strip=True) for li in child.find_all("li", recursive=False)]
            blocks.append(("list", name == "ol", items))
            continue
        if name == "blockquote":
            blocks.append(("quote", parse_inline(child, st)))
            continue
        txt = child.get_text(strip=True)
        htype = _content_heading_type(child, st["body"]["font-size"])
        has_block = any(getattr(c, "name", None) in ("section", "p", "div", "blockquote", "ul", "ol", "img", "hr")
                        for c in child.children)
        if htype and 2 <= len(txt) <= 30 and not re.search(r"[。！？；：]", txt) and not has_block:
            vi = match_heading_variant(child, st, state)
            blocks.append(("heading", vi, txt))
            continue
        if has_block:
            _walk_content(child, st, blocks, state)
            continue
        if txt:
            blocks.append(("para", parse_inline(child, st)))
            continue


def parse_url_content(soup, st):
    """递归解析另一篇已发布文章，输出块序列（换皮不换字）。"""
    jc = soup.find(id="js_content")
    blocks = []
    if jc:
        _walk_content(jc, st, blocks, {"order": {}})
    return blocks


def parse_md_inline(text, st):
    """把 Markdown 段落里的 ==高亮== 、 **加粗** 、 [文字](链接) 转成带样式的 HTML（并做 HTML 转义）。"""
    def esc(s):
        return html.escape(s, quote=False)
    parts = re.split(r"(\*\*[^*]+\*\*|==[^=]+==|\[[^\]]+\]\([^)]+\))", text)
    out = []
    for p in parts:
        if not p:
            continue
        if p.startswith("**") and p.endswith("**"):
            inner = p[2:-2]
            out.append(f'<strong style="{css(color=st.get("strong_color"), font_weight="bold")}">{esc(inner)}</strong>')
        elif p.startswith("==") and p.endswith("=="):
            inner = p[2:-2]
            mb = st.get("mark_bg")
            if mb:
                out.append(f'<mark style="{css(background=mb, color=st.get("mark_color") or "#1a1a1a")}">{esc(inner)}</mark>')
            else:
                out.append(esc(inner))
        elif p.startswith("[") and p.endswith(")") and "](" in p:
            label, url = p[1:].split("](", 1)
            url = url[:-1]
            safe = url if re.match(r"https?://|/|#", url) else "#"
            out.append(f'<a href="{esc(safe)}" style="{css(color=st.get("theme_color", st.get("strong_color")))}">{esc(label)}</a>')
        else:
            out.append(esc(p))
    return "".join(out)


def parse_md_content(text, st):
    blocks = []
    lines = text.split("\n")
    i, n = 0, len(lines)
    buf = []
    while i < n:
        raw = lines[i].rstrip()
        s = raw.strip()
        if not s:
            if buf:
                blocks.append(("para", "".join(buf)))
                buf = []
            i += 1
            continue
        if s == "---":
            if buf:
                blocks.append(("para", "".join(buf)))
                buf = []
            blocks.append(("divider",))
            i += 1
            continue
        if s.startswith("# "):
            if buf:
                blocks.append(("para", "".join(buf)))
                buf = []
            blocks.append(("heading", {"level": 1}, s[2:].strip()))
            i += 1
            continue
        if s.startswith("## "):
            if buf:
                blocks.append(("para", "".join(buf)))
                buf = []
            blocks.append(("heading", {"level": 2}, s[3:].strip()))
            i += 1
            continue
        if s.startswith("### "):
            if buf:
                blocks.append(("para", "".join(buf)))
                buf = []
            blocks.append(("heading", {"level": 3}, s[4:].strip()))
            i += 1
            continue
        if s.startswith("!["):
            m = re.match(r"!\[(.*?)\]\((.*?)\)", s)
            if m and buf:
                blocks.append(("para", "".join(buf)))
                buf = []
            if m:
                blocks.append(("image", m.group(2), m.group(1)))
            i += 1
            continue
        if s.startswith(">"):
            if buf:
                blocks.append(("para", "".join(buf)))
                buf = []
            blocks.append(("quote", s.lstrip("> ").strip()))
            i += 1
            continue
        if re.match(r"^(\d+\.|-)\s+", s):
            if buf:
                blocks.append(("para", "".join(buf)))
                buf = []
            ordered = s[0].isdigit()
            items = []
            while i < n and re.match(r"^(\d+\.|-)\s+", lines[i].strip()):
                items.append(re.sub(r"^(\d+\.|-)\s+", "", lines[i].strip()))
                i += 1
            blocks.append(("list", ordered, items))
            continue
        buf.append(s + " ")
        i += 1
    if buf:
        blocks.append(("para", "".join(buf)))
    return blocks


# ---------------- 渲染 ----------------
HEADING_KEEP = {
    "font-size", "color", "font-weight", "font-family", "text-align",
    "background-color", "background", "display", "padding", "padding-left",
    "padding-top", "padding-right", "padding-bottom", "border-radius", "line-height",
}


def sanitize_heading_style(sd):
    out = {}
    for k, v in sd.items():
        if not v:
            continue
        if k in HEADING_KEEP or k.startswith("border"):
            out[k] = v
    if out.get("display") != "inline-block":
        out.pop("display", None)
    out.setdefault("margin", "0.8em 0 0.6em")
    return out


def pick_tag_variant(st):
    hs = st.get("headings", [])
    idx = next((k for k, h in enumerate(hs) if h.get("type") == "tag"), None)
    if idx is None and hs:
        idx = 0
    return idx


def qr_placeholder_html():
    """原文二维码名片账号专属，绝不沿用：渲染占位框提示用户替换。"""
    box = css(margin="1.5em 0", padding="24px 16px", border="2px dashed #c8c8c8",
              border_radius="8px", background="#fafafa", text_align="center")
    return (
        f'<section style="{box}">'
        f'<div style="font-size:15px;color:#666;font-weight:bold;margin-bottom:8px">'
        f'【请在此处放置你的公众号二维码名片】</div>'
        f'<div style="font-size:13px;color:#999;line-height:1.6">'
        f'原文二维码属于参考账号，已自动移除，请替换为你的二维码图片</div>'
        f'</section>'
    )


def follow_card_html(st, keep_account):
    """引导关注卡。克隆时默认不照搬参考账号身份（用占位），--keep-account 才沿用提取到的。"""
    f = st.get("follow", {})
    if keep_account and f.get("nickname"):
        hi, name, sig = f["headimg"], f["nickname"], f.get("signature", "")
    else:
        hi, name, sig = "", "你的公众号名称", "你的公众号简介"
    card_style = css(margin="0 0 1.2em", padding="12px 14px", border="1px solid #eee",
                     border_radius="10px", display="flex", align_items="center")
    if hi:
        avatar = f'<img src="{hi}" style="width:46px;height:46px;border-radius:50%;margin-right:12px">'
    else:
        avatar = f'<div style="width:46px;height:46px;border-radius:50%;background:#e6e6e6;margin-right:12px;flex:0 0 auto"></div>'
    btn_style = css(background=st.get("theme_color", "#2e81da"), color="#fff",
                    padding="4px 12px", border_radius="14px", font_size="13px")
    return (
        f'<section style="{card_style}">'
        f'{avatar}'
        f'<div style="flex:1"><strong style="font-size:15px">{name}</strong>'
        f'<br><span style="font-size:12px;color:#888">{sig}</span></div>'
        f'<span style="{btn_style}">关注</span>'
        f'</section>'
    )


def title_style(st):
    b = st["body"]
    return {
        "font-size": "20px", "font-weight": "bold",
        "color": b.get("color") or "#1a1a1a",
        "text-align": b.get("text-align") or "left",
        "margin": "0 0 1em", "line-height": "1.4",
    }


def render(blocks, st, follow=True, end_img=True, keep_account=False):
    b = st["body"]
    body_style = css(font_size=b.get("font-size"), color=b.get("color"),
                     line_height=b.get("line-height"), text_align=b.get("text-align"),
                     letter_spacing=b.get("letter-spacing"), font_family=b.get("font-family"))
    out = []
    if follow:
        out.append(follow_card_html(st, keep_account))
        if st.get("follow_banner"):
            out.append(f'<section style="text-align:center;margin:0 0 1.2em">'
                       f'<img src="{st["follow_banner"]}" style="max-width:100%;border-radius:6px"></section>')

    for blk in blocks:
        kind = blk[0]
        if kind == "heading":
            meta, txt = blk[1], blk[2]
            hd = None
            centered = False
            if isinstance(meta, dict):          # Markdown 草稿：按层级决定样式
                level = meta.get("level", 2)
                if level == 1:                  # 文章大标题用合成样式（平台标题不可提取）
                    hd = title_style(st)
                else:
                    vi = pick_tag_variant(st)
                    if vi is not None:
                        hd = sanitize_heading_style(st["headings"][vi]["style"])
                        centered = st["headings"][vi].get("centered", False)
            else:                               # URL 内容：已匹配到具体版式变体
                vi = meta
                if isinstance(vi, int) and 0 <= vi < len(st["headings"]):
                    hd = sanitize_heading_style(st["headings"][vi]["style"])
                    centered = st["headings"][vi].get("centered", False)
            if not hd:
                hd = {"font-weight": "bold", "font-size": "18px", "margin": "0.8em 0 0.6em"}
            if centered:
                out.append(
                    f'<section style="text-align:center;justify-content:center;display:flex;margin:10px 0">'
                    f'<section style="{dict_to_style(hd)}">{txt}</section></section>'
                )
            else:
                out.append(f'<section style="{dict_to_style(hd)}">{txt}</section>')
        elif kind == "para":
            out.append(f'<section style="{body_style}">{parse_md_inline(blk[1], st)}</section>')
        elif kind == "quote":
            q = st["quote"] or {"background-color": "#f2f7ff", "border-left": "4px solid #2e81da",
                                "padding": "12px 14px", "border-radius": "6px", "margin": "1.2em 0"}
            out.append(f'<section style="{dict_to_style(q)}">{parse_md_inline(blk[1], st)}</section>')
        elif kind == "image":
            out.append(f'<section style="text-align:center;margin:1.2em 0">'
                       f'<img src="{blk[1]}" alt="{blk[2]}" style="max-width:100%;border-radius:6px"></section>')
        elif kind == "divider":
            d = st["divider"]
            out.append(f'<hr style="{dict_to_style(d)}">')
        elif kind == "list":
            ordered, items = blk[1], blk[2]
            tag = "ol" if ordered else "ul"
            li_style = css(margin="0.4em 0", color=b.get("color"))
            list_style = css(padding_left="1.4em", line_height=b.get("line-height"),
                             color=b.get("color"), font_size=b.get("font-size"))
            lis = "".join(f"<li style='{li_style}'>{it}</li>" for it in items)
            out.append(f'<{tag} style="{list_style}">{lis}</{tag}>')

    if end_img and st["end_img"]:
        out.append(f'<section style="text-align:center;margin:1.5em 0">'
                   f'<img src="{st["end_img"]}" style="max-width:100%;border-radius:6px"></section>')

    if follow and st.get("qr_placeholder"):
        out.append(qr_placeholder_html())
    return "\n".join(out)


# ---------------- 样式可移植：clone 提取的 st → draft 五步法令牌主题 ----------------
# 让「提取任意参考文章风格 → 存成 draft 可用主题」成为闭环。draft 渲染器消费的 blocks 键：
#   body / strong / mark / quote / list / image / h1 / h2 / h3 /
#   section_title / item_title / intro / footer / action_tip / tip_box / callout_*
# tokens 需含：primary / accent / highlight_bg / text / gray / max_width /
#   base_font / line_height / font_family 及间距令牌（paragraph_spacing / section_top /
#   divider_margin / image_margin）。blocks 内以 @token 引用，与 draft 主题同源。
def _st_to_draft_tokens(st):
    """把 clone 的 st 归一化为 draft 的 tokens 设计令牌（单一真源）。"""
    body = st.get("body", {})
    return {
        "primary": st.get("theme_color") or "#2e81da",
        "accent": st.get("strong_color") or st.get("theme_color") or "#2e81da",
        "highlight_bg": st.get("mark_bg") or "#fffb00",
        "text": body.get("color") or "#3e3e3e",
        "gray": "#888888",
        "max_width": "677px",
        "base_font": body.get("font-size") or "16px",
        "line_height": body.get("line-height") or "1.75",
        "paragraph_spacing": "1.5em",
        "section_top": "1.5em",
        "divider_margin": (st.get("divider") or {}).get("margin") or "2em 0",
        "image_margin": "1em auto",
        "font_family": body.get("font-family")
        or "-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif",
    }


def _heading_block(h, fallback_size="18px"):
    """把 st['headings'][*]（{style,type}）转成 draft 的 h2 类块样式。"""
    if not isinstance(h, dict):
        return {"font_size": fallback_size, "color": "@primary", "font_weight": "bold",
                "text_align": "left", "margin": "1.1em 0 0.5em"}
    sd = h.get("style", {}) or {}
    if h.get("type") == "tag":
        return {
            "font_size": sd.get("font-size", fallback_size),
            "color": sd.get("color", "@primary"),
            "font_weight": sd.get("font-weight", "bold"),
            "background": sd.get("background-color") or sd.get("background"),
            "display": "inline-block",
            "padding": sd.get("padding", "0 6px"),
            "border_radius": sd.get("border-radius"),
            "margin": sd.get("margin", "1.5em 0 0.6em"),
            "line_height": sd.get("line-height", "@line_height"),
            "text_align": sd.get("text-align", "left"),
        }
    return {
        "font_size": sd.get("font-size", fallback_size),
        "color": sd.get("color", "@primary"),
        "font_weight": sd.get("font-weight", "bold"),
        "text_align": sd.get("text-align", "left"),
        "margin": sd.get("margin", "1.1em 0 0.5em"),
    }


def st_to_draft_theme(st, name, style_url="", account=""):
    """clone 提取的 st → draft 可加载的五步法令牌主题 JSON（含 @token 引用）。

    渲染仍走 clone 原 st（零保真损失）；此函数只在 --save-theme 时把 st 归一化为
    draft 同源 schema，使其能被 draft_cli 直接加载、在预览页主题下拉中出现。
    """
    tokens = _st_to_draft_tokens(st)
    hs = st.get("headings", [])
    h2 = _heading_block(hs[0]) if hs else {"font_size": "18px", "color": "@primary",
                                           "font_weight": "bold", "text_align": "left",
                                           "margin": "1.1em 0 0.5em"}
    h1 = dict(h2); h1.update({"font_size": "20px", "margin": "1.2em 0 0.6em"})
    h3 = dict(h2); h3.update({"font_size": "16px", "color": "@text", "margin": "1em 0 0.4em"})
    q = st.get("quote") or {}
    quote = {
        "background": q.get("background-color") or "rgba(81,151,248,0.13)",
        "border_left": q.get("border-left") or "4px solid @accent",
        "color": q.get("color") or "@text",
        "padding": q.get("padding") or "14px 16px",
        "border_radius": q.get("border-radius") or "8px",
        "margin": q.get("margin") or "1.5em 0",
        "font_size": q.get("font-size") or "@base_font",
    }
    d = st.get("divider") or {}
    divider = {
        "border_top": d.get("border-top") or "1px solid #e3e3e3",
        "margin": d.get("margin") or "@divider_margin",
    }
    body = st.get("body", {})
    blocks = {
        "body": {
            "font_size": "@base_font",
            "color": "@text",
            "line_height": "@line_height",
            "letter_spacing": body.get("letter-spacing", "0.5px"),
            "paragraph_spacing": "@paragraph_spacing",
            "text_align": body.get("text-align", "left"),
        },
        "h1": h1, "h2": h2, "h3": h3,
        "strong": "@primary",
        "mark": {"bg": tokens["highlight_bg"], "color": st.get("mark_color") or "#1a1a1a"},
        "quote": quote,
        "divider": divider,
        "list": {"item_spacing": "0.5em", "color": "@text", "marker": "@primary"},
        "image": {"caption_color": "@gray", "caption_size": "14px",
                  "caption_align": "center", "radius": "6px"},
        "callout_tip": {"bg": "rgba(81,151,248,0.13)", "color": "@accent"},
        "callout_warning": {"bg": "rgba(217,33,66,0.10)", "color": "@primary"},
        "callout_info": {"bg": "#f5f6f8", "color": "#5a5a5a"},
        "section_title": {"background": "@highlight_bg", "color": "@text",
                          "font_size": "18px", "font_weight": "bold",
                          "display": "inline-block", "padding": "0 6px",
                          "margin": "1.5em 0 0.6em", "line_height": "@line_height"},
        "item_title": {"color": "@primary", "font_size": "16px", "font_weight": "bold",
                       "margin": "1.2em 0 0.4em"},
        "intro": {"color": "@gray", "font_size": "15px", "letter_spacing": "2px",
                  "text_align": "center", "line_height": "@line_height", "margin": "0 0 1.2em"},
        "footer": {"color": "@gray", "font_size": "14px", "text_align": "center",
                   "margin": "28px 0 0", "border_top": "1px solid #eee", "padding_top": "18px"},
        "action_tip": {"color": "@primary", "font_size": "16px", "margin": "1.2em 0",
                       "line_height": "1.8"},
        "tip_box": {"background": "#f7f8fa", "border_left": "4px solid @primary",
                    "padding": "14px 18px", "margin": "1.5em 0", "color": "@text",
                    "font_size": "15px", "line_height": "1.7"},
    }
    return {
        "meta": {
            "name": account or name,
            "extracted_from": [style_url] if style_url else [],
            "note": "由 article-format-clone --save-theme 从参考文章自动提取并归一化为五步法令牌版主题。",
        },
        "page": {"background": "#ffffff", "font_family": tokens["font_family"]},
        "tokens": tokens,
        "blocks": blocks,
    }


# ---------------- style 解析（支持 URL / 本地 .json 文件名 / 原始 JSON 字符串）----------------
def _styles_dir():
    # 持久样式库属 skill 长期数据，迁出 outputs/ 到 data/（规范 §1.1）
    return os.path.join(PROJECT_ROOT, "data", "styles")


def _draft_themes_dir():
    """draft 主题目录（位于 skill 根级共享 references/themes，与 draft 读取路径一致）。"""
    return os.path.join(PROJECT_ROOT, "references", "themes")


def _draft_theme_json():
    """draft 主题分发器（skill 根级共享 references/theme.json）。"""
    return os.path.join(PROJECT_ROOT, "references", "theme.json")


def _save_draft_theme(theme, name):
    """把归一化主题写入 draft 主题目录；不可写时回退到 data/themes/。返回实际路径。"""
    tdir = _draft_themes_dir()
    try:
        os.makedirs(tdir, exist_ok=True)
    except Exception:
        # 持久主题回退目录也迁出 outputs/ 到 data/（规范 §1.1）
        tdir = os.path.join(PROJECT_ROOT, "data", "themes")
        os.makedirs(tdir, exist_ok=True)
    path = os.path.join(tdir, name + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(theme, f, ensure_ascii=False, indent=2)
    return path


def _register_draft_theme(name, account, style_url):
    """把新主题登记进 draft 的 theme.json（available + themes），使其在预览下拉中出现。"""
    p = _draft_theme_json()
    disp = {}
    if os.path.isfile(p):
        try:
            with open(p, encoding="utf-8") as f:
                disp = json.load(f)
        except Exception:
            disp = {}
    if not isinstance(disp, dict):
        disp = {}
    avail = disp.setdefault("available", [])
    themes = disp.setdefault("themes", {})
    if name not in avail:
        avail.append(name)
    themes[name] = {
        "account": account or name,
        "style": "由 clone --save-theme 从参考文章提取归一化",
        "file": "themes/%s.json" % name,
        "extracted_from": style_url or "",
    }
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(disp, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def resolve_style(style_arg, ocr=True):
    """解析 style 参数：URL → 抓取并提取；本地文件（data/styles/name.json 或 name）→ 读 JSON；
    原始 JSON 字符串 → json.loads；均失败则抛错。"""
    if style_arg.startswith(("http://", "https://")):
        soup = BeautifulSoup(load(style_arg), "lxml")
        return extract_style(soup, style_url=style_arg, ocr=ocr)
    # 本地文件：直接路径，或 data/styles/<name>.json
    base = style_arg
    if not base.endswith(".json"):
        base = base + ".json"
    candidates = [base, os.path.join(_styles_dir(), base)]
    for c in candidates:
        if os.path.isfile(c):
            with open(c, encoding="utf-8") as f:
                return json.load(f)
    # 原始 JSON 字符串
    try:
        return json.loads(style_arg)
    except Exception:
        pass
    raise ValueError("无法解析 style 参数（需 URL / styles 文件名 / 原始 JSON）")


# ---------------- CLI ----------------
def _force_utf8():
    """强制标准流编码，消除 Windows GBK 下 'gbk codec can't encode character' 崩溃。

    - 管道 / 子进程场景（serve 经 cli_bridge 调用，非 tty）：统一 UTF-8 无损，
      与 cli_bridge 的 encoding="utf-8" 对齐，渲染结果（含私有区 emoji 等特殊字符）不丢。
    - 交互终端场景（用户直接 python clone_cli.py）：保持系统编码，仅把 errors 改 replace，
      保证中文正常显示，且遇到 GBK 表示不了的字符时用 '?' 兜底而非炸进程。
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
            # 极老 Python：reconfigure 不可用 → 退回二进制 buffer 直写 UTF-8
            try:
                buf = getattr(s, "buffer", None)
                if buf is not None:
                    setattr(sys, name, io.TextIOWrapper(buf, encoding="utf-8", errors="replace"))
            except Exception:
                pass


def _fmt_err(e):
    """把常见异常转成面向用户的简洁中文错误（避免向调用方抛原始 traceback）。"""
    import urllib.error as _ue
    if isinstance(e, (_ue.URLError, _ue.HTTPError)) or "urlopen" in str(e) or "Connection" in type(e).__name__:
        return ("无法访问 URL（链接无效 / 网络不可达 / 公众号反爬限制）。"
                "建议先点『提取』把样式存为本地 JSON，再用该样式渲染：" + str(e))
    if isinstance(e, ValueError):
        return "参数或样式解析失败：" + str(e)
    if isinstance(e, KeyError):
        return "样式数据不完整（可能提取失败或字段缺失）：" + str(e)
    if isinstance(e, OSError):
        return "文件读写失败：" + str(e)
    return type(e).__name__ + ": " + str(e)


def main():
    _force_utf8()
    p = argparse.ArgumentParser(description="公众号 HTML 克隆排版（article-format-clone）")
    p.add_argument("--style", required=True, help="风格参考：URL / data/styles 下文件名 / 原始 JSON")
    p.add_argument("--content", help="我的文章：URL / .md / .txt / -（标准输入）")
    p.add_argument("-o", "--output", help="输出 HTML 路径")
    p.add_argument("--dump-style", action="store_true", help="仅打印提取到的样式 JSON 到 stdout（供 preview 调用）")
    p.add_argument("--no-follow", action="store_true", help="不包含引导关注卡/关注引导图")
    p.add_argument("--no-end", action="store_true", help="不包含结尾点亮图")
    p.add_argument("--no-ocr", action="store_true", help="不做 OCR 确认：用结构启发式采用文末横幅图（仍告警请人工确认）")
    p.add_argument("--no-random-guide", action="store_true", help="关闭素材库随机复用：本次未识别到引导图时不从素材库随机取（默认开启随机复用）")
    p.add_argument("--keep-account", action="store_true", help="引导关注卡沿用参考账号身份（默认用占位，避免照搬他人账号）")
    p.add_argument("--save-theme", metavar="NAME", help="把提取到的样式归一化为 draft 五步法令牌主题，存到 draft 主题目录（含 @token 引用），可直接被 draft 复用")
    p.add_argument("--account", metavar="LABEL", help="--save-theme 时登记到 theme.json 的账号标签（缺省用 NAME）")
    args = p.parse_args()

    try:
        st = resolve_style(args.style, ocr=not args.no_ocr)

        if args.save_theme:
            theme = st_to_draft_theme(st, args.save_theme,
                                      style_url=args.style if args.style.startswith(("http://", "https://")) else "",
                                      account=args.account)
            path = _save_draft_theme(theme, args.save_theme)
            registered = _register_draft_theme(args.save_theme, args.account, args.style)
            print("已生成 draft 主题：%s" % path)
            if registered:
                print("已登记到 theme.json，可直接用 draft -t %s 复用" % args.save_theme)
            else:
                print("[warn] theme.json 登记失败（不影响主题文件本身），可手动在 article-format-draft/references/theme.json 的 available 中加入 %s" % args.save_theme, file=sys.stderr)
            return

        if args.dump_style:
            print(json.dumps(st, ensure_ascii=False, indent=2, default=str))
            return

        if not args.content:
            print("ERROR: 需提供 --content（URL / 文件 / -）", file=sys.stderr)
            sys.exit(1)

        if args.content == "-":
            text = sys.stdin.read()
            blocks = parse_md_content(text, st)
        elif args.content.startswith("http://") or args.content.startswith("https://"):
            csoup = BeautifulSoup(fetch(args.content), "lxml")
            blocks = parse_url_content(csoup, st)
        else:
            with open(args.content, encoding="utf-8") as fh:
                text = fh.read()
            if args.content.endswith((".md", ".txt")):
                blocks = parse_md_content(text, st)
            else:
                blocks = parse_url_content(BeautifulSoup(text, "lxml"), st)

        # —— 引导图素材库：识别通过则入库；本次无图则按账号档随机复用 ——
        # 本地图目录/前缀提前算好（随机复用需把库图复制进产物，保持自包含）
        # 统一会话目录（Skill 输出目录规范）：渲染产物落到
        #   ~/WorkBuddy\wechat-article-format_{ts}\
        # 不再写入 article_formate/outputs/（该路径已废止，见规范 §6）。
        topic = _safe_slug(_derive_topic(args))
        if args.output:
            out_dir = os.path.dirname(os.path.abspath(args.output))
            html_path = args.output
        else:
            session_dir = _session_dir("wechat-article-format")
            out_dir = session_dir
            html_path = os.path.join(session_dir, "0_clone_%s.html" % topic)
        os.makedirs(out_dir, exist_ok=True)
        # 图片本地化目录：会话目录内 0_images/ 子目录（文件夹型产物带序号前缀，合规）
        images_dir = os.path.join(out_dir, "0_images")
        os.makedirs(images_dir, exist_ok=True)
        prefix = "0_images"

        acct = _account_key(st, args.style)
        # ① 本次 OCR 识别通过的通用引导图 → 入库（远程 URL 才入）
        if st.get("follow_banner", "").startswith("http"):
            save_guide_to_library(acct, "follow", st["follow_banner"])
        if st.get("end_img", "").startswith("http"):
            save_guide_to_library(acct, "end", st["end_img"])
        # ② 本次未识别到 → 从该账号素材档随机复用（--no-random-guide 关闭；库空则回退排除+提示自备）
        if not args.no_random_guide:
            if not st.get("follow_banner") and not args.no_follow:
                pk = pick_random_guide(acct, "follow")
                if pk:
                    st["follow_banner"] = _copy_into_images(pk, images_dir, prefix)
                    print(f"[warn] 本次未识别到文首关注图，已从素材库[{acct}]随机复用一张历史引导图，请确认合适",
                          file=sys.stderr)
            if not st.get("end_img") and not args.no_end:
                pk = pick_random_guide(acct, "end")
                if pk:
                    st["end_img"] = _copy_into_images(pk, images_dir, prefix)
                    print(f"[warn] 本次未识别到文末点亮图，已从素材库[{acct}]随机复用一张历史引导图，请确认合适",
                          file=sys.stderr)

        html = render(blocks, st, follow=not args.no_follow, end_img=not args.no_end,
                      keep_account=args.keep_account)
        # 全部图片本地化：下载 http 图到 0_images/，src 改本地相对路径（产物自包含）；
        # 随机复用的库图已是本地相对路径，_localize_images 只处理 http，不受影响。
        html = _localize_images(html, images_dir, referer=_WX_REFERER, prefix=prefix)
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"已生成：{html_path}")
    except SystemExit:
        raise
    except Exception as e:
        print("ERROR: " + _fmt_err(e), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
