# -*- coding: utf-8 -*-
"""Convert conversation-style domain guides (.txt) into clean skill handbooks (.md).

Keeps all structured models (公式/范例/雷区/区别/完整范例), trims chatty tail
lines, adds a domain header + IP-mapping note. Originals are relocated to
references/_raw/ as source archive (non-destructive).
"""
import os, re, shutil

BASE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))  # 本 skill 根目录（基于 __file__ 自适应）
REF = os.path.join(BASE, "references")
RAW = os.path.join(REF, "_raw")
os.makedirs(RAW, exist_ok=True)

# src txt -> (handbook md, domain label, ip note)
JOBS = [
    ("娱乐.txt", "entertainment.md", "娱乐",
     "本域不强制固定 IP。署名/落款/自称沿用文章自身人设或来源写作人设"
     "（可参考 renshe-writer / meta-persona）；若文章未带明确人设且用户未指定，"
     "默认保留原文署名，**不套用福宝妈妈**。娱乐文落款可省略或用作者本名/网名。"),
    ("情感.txt", "emotion.md", "情感",
     "本域不强制固定 IP。署名/落款/自称沿用文章自身人设或来源写作人设；"
     "未指定则保留原文署名，**不套用福宝妈妈**。情感文重“深夜朋友”口吻，落款宜轻或省略。"),
    ("人生哲学励志.txt", "philosophy.md", "人生哲学励志",
     "本域不强制固定 IP。署名/落款/自称沿用文章自身人设或来源写作人设；"
     "未指定则保留原文署名，**不套用福宝妈妈**。"),
    ("女性觉醒.txt", "female_awakening.md", "女性觉醒",
     "本域不强制固定 IP。署名/落款/自称沿用文章自身人设或来源写作人设；"
     "未指定则保留原文署名，**不套用福宝妈妈**。女性觉醒文常带“宣言感”落款，"
     "可用作者本名/笔名，风格需从“弱”到“强”、从“睡着”到“醒来”。"),
    ("财经.txt", "finance.md", "财经",
     "本域不强制固定 IP，但需保持“人设一致性”：个人理财成长史保持“普通人逆袭”亲切感，"
     "商业与公司故事保持“洞察者”专业感，生活化财经解读保持“身边观察者”口语感。"
     "署名/落款沿用文章自身人设；未指定则保留原文署名，**不套用福宝妈妈**。"),
]

# Lines that are pure separators.
SEP_RE = re.compile(r'^[=\-\s]{10,}$')
# Chatty tail lines (only appear at Q&A tails, safe to drop).
TAIL_RE = re.compile(
    r'(你平时写的是|你写的是|告诉我你|告诉我具体|可以告诉我|我帮你(再)?(深挖|定制|看看|拆解|具体拆解)|'
    r'咱们评论区|你是想写|你想写|你现在的财务|你希望我|比如，你上一轮|这四种模型里|'
    r'这个点你(卡|想写)|把我写好的结尾|如果有(了)?一篇|你平时写的是影视|你平时写的是爱情|'
    r'你写的是婚恋|你写的是爱情类|告诉我具体方向|你现在的财务状况属于|'
    r'你想写的是哪家公司|你是要写|你是想写“|你写的是哪个方向)'
)
# Lines carrying only "social" emojis used in tail sign-offs.
TAIL_EMOJI_RE = re.compile(r'[😉😎💖🌙💪💔➡️]')

def clean_body(text):
    out = []
    for line in text.splitlines():
        s = line.rstrip()
        if not s.strip():
            out.append("")
            continue
        if SEP_RE.match(s):
            continue
        # Never drop blockquote example lines (they start with ">") — they may
        # legitimately contain tail-chat keywords like "咱们评论区".
        if s.lstrip().startswith(">"):
            out.append(s)
            continue
        if TAIL_RE.search(s):
            continue
        # drop lines that are basically just a tail sign-off emoji combo
        if TAIL_EMOJI_RE.search(s) and len(re.sub(r'\s', '', s)) <= 6:
            continue
        out.append(s)
    # collapse 3+ consecutive blank lines
    merged = []
    blank = 0
    for s in out:
        if s == "":
            blank += 1
            if blank <= 1:
                merged.append(s)
        else:
            blank = 0
            merged.append(s)
    return "\n".join(merged).strip() + "\n"

HEADER = (
    "# {domain} 文章开头结尾优化 · 打法手册\n\n"
    "本手册是 `begin-end` 技能中「{domain}」领域的详细参考。SKILL.md 只做流程编排与领域路由，"
    "所有可直接套用的「开头模型 / 结尾模型 / 公式 / 范例 / 雷区 / 自检」都在这里。\n\n"
    "> 用法：先由 SKILL.md 判定本文属于「{domain}」领域（必要时追问子类），再读本手册选模型。\n"
    "> 本手册由用户提供的对话式领域指南转换而来，原始素材见 `references/_raw/{src}`。\n\n"
    "---\n\n"
)

def main():
    # Re-run mode: read from _raw archive, overwrite handbooks, skip move.
    for src, dst, domain, ipnote in JOBS:
        sp = os.path.join(RAW, src)
        with open(sp, encoding="utf-8") as f:
            text = f.read()
        body = clean_body(text)
        header = HEADER.format(domain=domain, src=src)
        footer = (
            "\n---\n\n## IP 身份映射（{domain}）\n\n{ip}\n".format(domain=domain, ip=ipnote)
        )
        content = header + body + footer
        dp = os.path.join(REF, dst)
        with open(dp, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[ok] {src} -> references/{dst}  ({len(content)} chars)")

if __name__ == "__main__":
    main()
