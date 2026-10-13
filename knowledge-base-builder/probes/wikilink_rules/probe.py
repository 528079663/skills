#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""十二套探针 P1–P12：一次性驱动器（只写临时目录 _work/，绝不碰 skill 仓库与真库）。

  P1 render + verify 骨架（Step 1–5，--allow-empty-index；含模板占位回归）
  P2 verify 满库（C9/C10/C12/C13）＋负控（[[不存在]] 必报失效）
  P3 audit A1 explicit（有链库 / 无链库对照，exit 恒 0）
  P4 check_hooks（q_hooks 只读校验）
  P5 recall（有链库 / 无链库命中集合与排序一致 → 检索不依赖 explicit 边）
  P6 路由 JSON 契约（原因码 / 软硬错退出码 / 落盘 / flow×stage 交叉校验）
  P7 verify C14 源目录只读（基线、增删改、mtime 不参与、写范围）
  P8 validate / verify 的输入与退出码守卫（G1/G1b/T6/G3/G4/T4/T3 工单）
  P9 check_verbatim_lite（多/缺两向 + units-on 让位 + 前缀白名单）+ HOOK_GRAM_RATIO 双向 + C10 目标解析范围
  P10 progress.py 进度派生（三档 + no_hv / next_todo / coverage 声称字段已作废 / 两类不一致 / JSON 逐字节确定 / 只读 / 输入守卫）
  P11 progress.py --gate（默认关 / 两类不一致判红 / stdout 逐字节不变 / 与 --emit-todo 叠加 / 判本视图 / 守卫优先 / 只读）
  P12 结构适配（enc＝A8 编码保护｜dir＝A2+A3 目录/KB 根参数化｜src＝A4 源类型与 C14 清单口径｜lang＝A1 多语言分词｜fb＝同源兜底不得产出可用值｜sb＝拆篇候选边界三条规约：资产表按内容判、围栏整体不可切、超限先粘连不硬切）

全绿 exit 0；有 FAIL exit 1。逐套盯什么、为什么这么断言，见 probes/README.md。
"""
import json
import os
import re
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # 与 scripts/*.py 同形（A8，Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))          # probes/wikilink_rules → skill 根
SCRIPTS = os.path.join(REPO, "scripts")
TAXO = os.path.join(REPO, "assets", "taxonomy", "taxonomy.json")
TEMPLATES = os.path.join(REPO, "assets", "templates")
# 临时库落在探针目录下的 _work/（git 忽略即可）；设 PROBE_WORK 可换到别处
WORK = os.environ.get("PROBE_WORK", os.path.join(HERE, "_work"))

FLOW, STAGE = "视频制作", "1_找素材"
B_STEM = "选品四象限判需求与竞争"
A_STEM = "爆款拆解三步法"
C_STEM = "封面标题的数字承诺"

ROWS = []


def run(args, want_rc=0, label=""):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([sys.executable] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    out = (p.stdout or "") + (p.stderr or "")
    name = label or os.path.basename(args[0])
    if want_rc is None:
        ROWS.append((name, "RAN", p.returncode, out))
    else:
        ROWS.append((name, "RC" if p.returncode == want_rc else "RC-MISMATCH",
                     p.returncode, out))
    return p.returncode, out


def w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def check(name, ok, detail=""):
    ROWS.append((name, "OK" if ok else "FAIL", "", detail))
    return ok


SRC_DOCS = {
    "选品方法.md": "# 选品方法\n\n## 四象限\n\n选品看两个轴：需求强度、竞争密度。"
                   "四象限里只有高需求低竞争值得进场，其余三格分别对应红海、伪需求、长尾。"
                   "判断需求强度用搜索量同比，判断竞争密度用在售链接数除以搜索量。\n",
    "爆款拆解.md": "# 爆款拆解\n\n## 三步法\n\n第一步锁定对标账号，第二步按完播率倒序排片，"
                   "第三步拆前 3 秒的钩子类型。拆钩子时必须对照选品的四象限结论："
                   "钩子再好，落在低需求象限的选题也不做。\n",
    "封面标题.md": "# 封面标题\n\n## 数字承诺\n\n标题里的数字必须是可验证的承诺。"
                   "封面人脸朝向与文字方向一致时点击率更高。\n",
}


def note(stem, title, topics, hooks, src, loc, one_liner, quote, points, extra, island_note=""):
    body = f"""---
title: {title}
flow: {FLOW}
stage: {STAGE}
substage: 子技巧
domains: [内容创作]
forms: [方法论]
tools: []
types: [方法]
projects: [AI自媒体]
topics: [{', '.join(topics)}]
q_hooks:
{chr(10).join('  - ' + h for h in hooks)}
sources:
  - {src}
source_locator:            # block 列表，首项=主块（与真库同格式；调用点仍传单个 loc 字符串）
  - {loc}
confidence: high
status: confirmed
created: 2026-10-02
---

# {title}

> {one_liner}

## 资料原话（evidence.quote）

> {quote}

## 归纳结论

{points}
{extra}
## 可执行清单

1. 按结论执行第一步；
2. 复盘一次再决定是否复用。

## AI 推断（inference）

> {island_note or '本笔记的推断与原文分离标注，不影响上述结论。'}
"""
    return body


NOTE_B = note(
    B_STEM, "选品四象限：判需求与竞争", ["选品", "爆款"],
    ["选品四象限怎么用", "怎么判断选题的需求强度", "竞争密度太高还能进场吗",
     "高需求低竞争是怎么算的"],
    "选品方法.md", "§四象限#char=0-120",
    "只有高需求低竞争象限值得进场。",
    "四象限里只有高需求低竞争值得进场",
    "- 两轴：需求强度（搜索量同比）、竞争密度（在售链接数 ÷ 搜索量）；\n"
    "- 其余三格 = 红海 / 伪需求 / 长尾，不进。\n", "")

NOTE_A = note(
    A_STEM, "爆款拆解三步法", ["选品", "爆款"],
    ["爆款拆解具体怎么拆", "拆前 3 秒钩子从哪开始", "对标账号怎么选才不跑偏",
     "完播率倒序排片有用吗"],
    "爆款拆解.md", "§三步法#char=0-110",
    "锁对标 → 按完播率倒序 → 拆前 3 秒钩子。",
    "第一步锁定对标账号，第二步按完播率倒序排片，第三步拆前 3 秒的钩子类型",
    f"- 三步顺序不可换，钩子类型是最后一步的产出；\n"
    f"- 第三步的准入判断依赖[[{B_STEM}]]给出的四象限结论：钩子再好，"
    "选题落在低需求象限也不做；\n",
    f"- 拆解结果回流候选池，准入仍按[[{B_STEM}]]的象限结论执行。\n", "")

NOTE_C = note(
    C_STEM, "封面标题的数字承诺", ["选品", "爆款", "封面"],
    ["封面标题里的数字有什么坑", "人脸朝向影响点击率吗", "数字承诺做不到会怎样"],
    "封面标题.md", "§数字承诺#char=0-60",
    "标题数字必须是可验证承诺。",
    "标题里的数字必须是可验证的承诺",
    "- 数字 = 承诺，写了就得兑现；\n- 封面人脸朝向与文字方向一致时点击率更高。\n", "",
    "本笔记与 A/B 同 topic 但正文没有引用它们，故不加双链——孤岛合法（08 第 3.6 节）。")

ANSWERS = {
    "q1_flows": [FLOW], "q2_stages": {FLOW: [STAGE, "2_写脚本"]},
    "q3_first_task": "把选品与爆款拆解沉淀成可检索笔记",
    "q4_painpoints": ["a", "b"], "q5_doc_types": ["c"], "q5_scale": "b",
    "q6_granularity": "b", "q7_ingest_scope": {"md": True, "minutes": True},
    "q8_unsorted_not_applicable": True, "q9_existing_kb": "a", "q10_collab": "b",
    "q11_note_depth": "b", "q11_depth_exceptions": ["a", "b"], "q12_batch_size": "a",
    "q13_output_targets": ["a"], "q13_class": "a", "q13_priv": ["b"],
    "q15_projects": [], "q15_exclude": ["a"], "q16_retrieval": "fts", "q16_units": "off",
}


def build_base(name):
    root = os.path.join(WORK, name)
    if os.path.isdir(root):
        shutil.rmtree(root)
    src, work, kb = (os.path.join(root, x) for x in ("source", "work", "kb"))
    for fn, text in SRC_DOCS.items():
        w(os.path.join(src, fn), text)
    w(os.path.join(work, "answers.json"), json.dumps(ANSWERS, ensure_ascii=False, indent=2))
    run([os.path.join(SCRIPTS, "scan_sources.py"), "--source", src,
         "--out", os.path.join(work, "sources_manifest.json")], 0, f"{name}: scan_sources")
    run([os.path.join(SCRIPTS, "build_profile.py"), "--answers",
         os.path.join(work, "answers.json"), "--out", os.path.join(work, "profile.json")],
        0, f"{name}: build_profile")
    run([os.path.join(SCRIPTS, "render_config.py"), "--profile", os.path.join(work, "profile.json"),
         "--manifest", os.path.join(work, "sources_manifest.json"), "--taxonomy", TAXO,
         "--out", os.path.join(work, "config.json")], 0, f"{name}: render_config")
    run([os.path.join(SCRIPTS, "render_templates.py"), "--config", os.path.join(work, "config.json"),
         "--templates", TEMPLATES, "--target", kb, "--kb-name", "探针库"], 0,
        f"{name}: render_templates")
    return kb, os.path.join(work, "config.json")


def add_notes(kb):
    d = os.path.join(kb, "工作流", FLOW, STAGE)
    w(os.path.join(d, B_STEM + ".md"), NOTE_B)
    w(os.path.join(d, A_STEM + ".md"), NOTE_A)
    w(os.path.join(d, C_STEM + ".md"), NOTE_C)


def aggregates(kb):
    run([os.path.join(SCRIPTS, "build_flows.py"), "--kb", kb], 0, f"build_flows {os.path.basename(kb)}")
    run([os.path.join(SCRIPTS, "build_topics.py"), "--kb", kb, "--notes", "工作流"],
        0, f"build_topics {os.path.basename(kb)}")
    run([os.path.join(SCRIPTS, "search_index.py"), "build", "--kb", kb,
         "--notes", "工作流", "--rebuild"], 0, f"index build {os.path.basename(kb)}")


def c_line(out, cid):
    for l in out.splitlines():
        if cid in l and l.strip().startswith("["):
            return l.strip()
    return ""


def recall_json(kb, route=None, query=None, want_rc=0, label=""):
    """跑一次 recall，返回 (rc, stdout, 解析后的 json|None)。"""
    args = [os.path.join(SCRIPTS, "search_index.py"), "recall", "--kb", kb]
    if query:
        args += ["--query", query]
    if route is not None:
        args += ["--route-json", json.dumps(route, ensure_ascii=False)]
    if want_rc == 0:
        args += ["--json"]
    rc, out = run(args, want_rc, label)
    data = None
    if rc == 0:
        try:
            data = json.loads(out)
        except ValueError:
            pass
    return rc, out, data


def warn_log_path(kb):
    return os.path.join(kb, "_meta", "logs", "route_warnings.jsonl")


def log_lines(kb):
    p = warn_log_path(kb)
    if not os.path.isfile(p):
        return 0
    with open(p, encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def codes_of(data):
    return [w.get("code") for w in (data or {}).get("warnings", [])]


def p6_route():
    """P6：路由契约。需要一个含两个工作流的库，才能造出"stage 存在但不属于该 flow"。"""
    flow2, stage2 = "直播运营", "1_开场"
    kb6, cfg6 = build_base("p6_route")
    add_notes(kb6)
    note_d = (NOTE_C.replace("flow: 视频制作", "flow: " + flow2)
                     .replace("stage: 1_找素材", "stage: " + stage2)
                     .replace("封面标题的数字承诺", "开场三分钟结构"))
    w(os.path.join(kb6, "工作流", flow2, stage2, "开场三分钟结构.md"), note_d)
    aggregates(kb6)

    # 前置：_meta/logs 目录不存在时，软错必须能把目录和文件一起建出来
    logdir = os.path.join(kb6, "_meta", "logs")
    shutil.rmtree(logdir, ignore_errors=True)
    _, _, d = recall_json(kb6, {"topics": ["根本不存在的主题"]}, "爆款", 0,
                          "P6 软错（logs 目录原先不存在）")
    check("P6 提醒：_meta/logs 缺失时软错能建目录并落盘",
          os.path.isfile(warn_log_path(kb6)), logdir)

    # 验收1：flow×stage 组合不存在 → warning + 丢 stage 留 flow + 命中 > 0（不静默 0）
    #   keywords 用「爆款」（视频制作库里命中的词），确保丢 stage 之后 flow 过滤仍出结果；
    #   若用只命中另一工作流的词，0 命中是关键词的功劳，测不出这条断言。
    _, _, d = recall_json(kb6, {"keywords": ["爆款"], "flow": FLOW, "stage": stage2},
                          None, 0, "P6 验收1 flow×stage 不匹配")
    r = (d or {}).get("route", {})
    check("验收1 flow×stage 组合不存在 → code=stage_flow_mismatch",
          "stage_flow_mismatch" in codes_of(d), str(codes_of(d)))
    check("验收1 丢 stage、保留 flow", r.get("stage") is None and r.get("flow") == FLOW,
          json.dumps({"flow": r.get("flow"), "stage": r.get("stage")}, ensure_ascii=False))
    check("验收1 不静默 0 命中（命中 > 0）", len((d or {}).get("hits", [])) > 0,
          "命中 %d 条" % len((d or {}).get("hits", [])))

    # 对照：组合真实存在时不该报 mismatch
    _, _, d = recall_json(kb6, {"keywords": ["开场"], "flow": flow2, "stage": stage2},
                          None, 0, "P6 对照 flow×stage 匹配")
    check("对照：合法组合不误报 stage_flow_mismatch",
          "stage_flow_mismatch" not in codes_of(d), str(codes_of(d)))

    # 验收2：非法 topic → code + 落盘一行（字段齐全、带时区 ts）
    n0 = log_lines(kb6)
    _, _, d = recall_json(kb6, {"topics": ["又一个不存在的主题"]}, "爆款", 0,
                          "P6 验收2 非法 topic")
    check("验收2 非法 topic → code=topic_not_found",
          "topic_not_found" in codes_of(d), str(codes_of(d)))
    check("验收2 每次软错落一行", log_lines(kb6) == n0 + 1,
          "before=%d after=%d" % (n0, log_lines(kb6)))
    raw_last = open(warn_log_path(kb6), encoding="utf-8").read().strip().split("\n")[-1]
    last = json.loads(raw_last)
    check("验收2 日志行字段齐全（ts/query/code/detail/severity）",
          sorted(last) == ["code", "detail", "query", "severity", "ts"], str(sorted(last)))
    check("验收2 ts 带时区（不是本地无时区）",
          bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$", last["ts"])),
          last.get("ts", ""))
    check("验收2 落盘是 sort_keys（code 排在 detail 前）",
          raw_last.index('"code"') < raw_last.index('"detail"'), raw_last[:120])

    # 验收3：三类硬错 → exit 2 且**不落任何一行**（文件不存在时也不新建）
    os.remove(warn_log_path(kb6))
    base = log_lines(kb6)
    hard = [("非 JSON 串", "爆款拆解"),
            ("顶层数组", ["爆款"]),
            ("keywords 混数字", {"keywords": ["爆款", 5]}),
            ("top_k 越界", {"keywords": ["爆款"], "top_k": 101}),
            ("三者全空", {"keywords": [], "topics": []})]
    for name, payload in hard:
        if isinstance(payload, str):
            rc, out = run([os.path.join(SCRIPTS, "search_index.py"), "recall",
                           "--kb", kb6, "--route-json", payload], 2, "P6 硬错 " + name)
        else:
            rc, out = run([os.path.join(SCRIPTS, "search_index.py"), "recall",
                           "--kb", kb6, "--route-json",
                           json.dumps(payload, ensure_ascii=False)], 2, "P6 硬错 " + name)
        check("验收3 硬错 exit 2 且不落盘：%s" % name,
              rc == 2 and log_lines(kb6) == base and not os.path.isfile(warn_log_path(kb6)),
              "rc=%s lines=%s" % (rc, log_lines(kb6)))

    # 验收4：三错叠加 → warnings 每项都有 code，rc 仍为 0
    #   必须带 keywords，否则 topics 被丢、stage 被丢之后就撞上 route_empty 硬错
    #   （那种情形是"硬错优先、整条不执行、一行不落"——已由上面那轮误打误撞验过）
    _, _, d = recall_json(kb6, {"keywords": ["爆款"], "topics": ["瞎写的主题"],
                                "flow": FLOW, "stage": stage2, "bad_field": 1},
                          None, 0, "P6 验收4 多字段软错叠加")
    ws = (d or {}).get("warnings", [])
    check("验收4 三错叠加 warnings 每项含 code 且 rc=0",
          len(ws) >= 3 and all(isinstance(w, dict) and w.get("code") and w.get("detail")
                               and w.get("severity") for w in ws),
          json.dumps(ws, ensure_ascii=False))
    check("验收4 三种 code 齐现",
          {"topic_not_found", "stage_flow_mismatch", "unknown_field"} <= set(codes_of(d)),
          str(codes_of(d)))

    # 混合：软错 + 硬错并存 → 硬错赢、exit 2、**一行都不落**（已收集的 warning 不落地）
    before = log_lines(kb6)
    rc, out = run([os.path.join(SCRIPTS, "search_index.py"), "recall", "--kb", kb6,
                   "--route-json", json.dumps({"topics": ["又一无"], "bad": 1},
                                              ensure_ascii=False)], 2, "P6 软错+硬错并存")
    check("软错与硬错并存时硬错优先、不落任何日志",
          rc == 2 and log_lines(kb6) == before,
          "rc=%s lines %d→%d" % (rc, before, log_lines(kb6)))

    # 退化路由（只给 --query，无路由）→ 不校验、不落盘
    before = log_lines(kb6)
    rc, out = run([os.path.join(SCRIPTS, "search_index.py"), "recall", "--kb", kb6,
                   "--query", "开场三分钟"], 0, "P6 退化路由")
    check("退化路由（无 route JSON）不落 warning 行", log_lines(kb6) == before,
          "before=%s after=%s" % (before, log_lines(kb6)))

    # 文本模式仍给人读：前缀带 code
    rc, out = run([os.path.join(SCRIPTS, "search_index.py"), "recall", "--kb", kb6,
                   "--query", "爆款", "--route-json",
                   json.dumps({"topics": ["不存在"], "stage": stage2}, ensure_ascii=False)],
                  0, "P6 文本模式 warning 带 code")
    check("文本模式 warning 行前缀含 (code)",
          re.search(r"\[recall\]\[校验\] \([a-z_]+\)", out or "") is not None,
          "\n".join(l for l in (out or "").splitlines() if "校验" in l))


def p7_snapshot():
    """P7：C14 源目录只读校验（基线、增删改、mtime 不参与、warn/fail 分档、verify 的写范围）。"""
    kb7, cfg7 = build_base("p7_snapshot")
    add_notes(kb7)
    aggregates(kb7)
    src = os.path.join(WORK, "p7_snapshot", "source")
    pristine = os.path.join(WORK, "p7_source_pristine")
    shutil.copytree(src, pristine)
    snap_path = os.path.join(kb7, "_meta", "source_snapshot.json")
    V = os.path.join(SCRIPTS, "verify.py")

    def v(args, want_rc, label):
        return run([V, "--kb", kb7] + args, want_rc, label)

    def c14(out):
        return c_line(out, "C14")

    def restore():
        shutil.rmtree(src, ignore_errors=True)
        shutil.copytree(pristine, src)

    # 验收 7/8：没有基线 → warn，不影响退出码（此时也没有快照文件）
    rc, out = v(["--config", cfg7], 0, "P7 无基线 verify")
    l = c14(out)
    check("验收7 无基线 → C14 warn、exit 不变",
          l.startswith("[WARN]") and "--snapshot-source" in l and rc == 0, l)
    check("P7 无基线时不该有快照文件", not os.path.isfile(snap_path), snap_path)
    rc, out = run([V, "--kb", kb7], 0, "P7 无 config 无 --source-root")
    check("验收8 无源目录可解析（无 config.source_root、无 --source-root）→ C14 warn",
          c14(out).startswith("[WARN]") and "无源目录" in c14(out) and rc == 0, c14(out))

    # 验收 1：建基线 → 常规 verify C14 PASS
    rc, out = v(["--source-root", src, "--snapshot-source"], 0, "P7 建基线")
    l = c14(out)
    check("验收1 --snapshot-source 建基线 → C14 PASS", l.startswith("[PASS]") and rc == 0, l)
    check("验收1 基线落在 _meta/source_snapshot.json", os.path.isfile(snap_path), snap_path)
    snap = json.load(open(snap_path, encoding="utf-8")) if os.path.isfile(snap_path) else {}
    check("P7 基线格式：created_at 带时区 + source_root 绝对 + files{size,sha256} + media_counts",
          bool(re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$",
                        snap.get("created_at", "")))
          and os.path.isabs(snap.get("source_root", ""))
          and all(sorted(v0) == ["sha256", "size"] for v0 in snap.get("files", {}).values())
          and "media_counts" in snap,
          json.dumps({k: (v0 if k != "files" else list(v0)) for k, v0 in snap.items()},
                     ensure_ascii=False)[:300])
    rc, out = v(["--config", cfg7], 0, "P7 常规 verify（有基线，未变动）")
    check("验收1 常规 verify 用 config.source_root 也能对上基线 → PASS",
          c14(out).startswith("[PASS]") and rc == 0, c14(out))

    # 验收 9：基线在、但源目录路径不在了（换盘/挪目录）→ warn，不是 fail
    rc, out = v(["--config", cfg7, "--source-root", "Z:/根本不存在的/源目录"], 0,
                "P7 基线指向不存在的路径")
    l = c14(out)
    check("验收9 有基线但路径不存在 → C14 warn 不 fail、exit 不变",
          l.startswith("[WARN]") and "不存在" in l and rc == 0, l)

    # 验收 6：只改 mtime、内容不变 → PASS（证明不比 mtime）
    touched = os.path.join(src, "选品方法.md")
    st = os.stat(touched)
    os.utime(touched, (st.st_atime - 7200, st.st_mtime - 7200))
    rc, out = v(["--config", cfg7], 0, "P7 只改 mtime")
    check("验收6 只 touch 改 mtime、内容不变 → C14 PASS",
          c14(out).startswith("[PASS]") and rc == 0, c14(out))

    # 验收 2：改内容 → fail + 非 0 退出
    w(touched, "# 选品方法\n\n## 四象限\n\n**被人改了内容**，加了新的一行。\n")
    rc, out = v(["--config", cfg7], 1, "P7 源文件被改")
    l = c14(out)
    check("验收2 源文件内容变 → C14 fail「被修改」+ exit 非 0",
          l.startswith("[FAIL]") and "被修改" in l and "选品方法.md" in l and rc == 1, l)
    restore()

    # 验收 3：删除 → fail
    os.remove(os.path.join(src, "封面标题.md"))
    rc, out = v(["--config", cfg7], 1, "P7 源文件被删")
    l = c14(out)
    check("验收3 源文件被删 → C14 fail「被删除」+ exit 非 0",
          l.startswith("[FAIL]") and "被删除" in l and "封面标题.md" in l and rc == 1, l)
    restore()

    # 验收 4：新增资料文档 → warn（不是 fail），且提示重建基线 + intake
    w(os.path.join(src, "新补的资料.md"), "# 新补的资料\n\n## 段落\n\n这是后来补进源目录的资料正文。\n")
    rc, out = v(["--config", cfg7], 0, "P7 新增资料文档")
    l = c14(out)
    check("验收4 新增 documents → C14 **warn 而非 fail**、exit 0",
          l.startswith("[WARN]") and rc == 0, l)
    check("验收4 warn 文案带「未纳管 / 重建基线 / intake」",
          "未纳管" in l and "重建基线" in l and "intake" in l, l)
    os.remove(os.path.join(src, "新补的资料.md"))

    # 验收 5：新增媒体 → warn，只报计数（不哈希、不逐篇列）
    with open(os.path.join(src, "配图.png"), "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    rc, out = v(["--config", cfg7], 0, "P7 新增媒体")
    l = c14(out)
    check("验收5 新增 media → warn 且只报计数变化",
          l.startswith("[WARN]") and "媒体数量变化" in l and "配图.png" not in l and rc == 0, l)
    os.remove(os.path.join(src, "配图.png"))

    # 重建一次干净基线；顺带用「文件集差分」证明 verify 的写范围
    all_files = lambda: {os.path.relpath(os.path.join(r, p), kb7).replace("\\", "/")
                         for r, _, fs in os.walk(kb7) for p in fs}
    os.remove(snap_path)
    f_before = all_files()
    v(["--source-root", src, "--snapshot-source"], 0, "P7 重建干净基线")
    f_after = all_files()
    created = sorted(f_after - f_before)
    check("verify --snapshot-source 只新建 _meta/source_snapshot.json 这一个文件",
          created == ["_meta/source_snapshot.json"], str(created))
    deleted = sorted(f_before - f_after)
    check("verify 不删任何既有文件", deleted == [], str(deleted))

    before = {os.path.relpath(os.path.join(r, p), kb7): os.path.getmtime(os.path.join(r, p))
              for r, _, fs in os.walk(kb7) for p in fs if p.endswith(".md")}
    rc, out = v(["--config", cfg7], 0, "P7 写范围复检（常规 verify）")
    after = {os.path.relpath(os.path.join(r, p), kb7): os.path.getmtime(os.path.join(r, p))
             for r, _, fs in os.walk(kb7) for p in fs if p.endswith(".md")}
    check("常规 verify 不改任何 .md（笔记与模板都不动）", before == after,
          "%d 个 md，差异=%s" % (len(before), sorted(set(before) ^ set(after))[:3]))

    # 显式建基线却建不出来 → 大声失败，不能 warn 了事
    rc, out = run([V, "--kb", kb7, "--source-root", "Z:/根本没有/这目录",
                   "--snapshot-source"], 1, "P7 建基线失败应报错")
    check("--snapshot-source 指向不存在的目录 → 非 0 退出并说明",
        rc != 0 and "不存在" in (out or ""), (out or "")[:200])
    rc, out = run([V, "--kb", kb7, "--snapshot-source"], 1, "P7 建基线但没源目录")
    check("--snapshot-source 无源目录可解析 → 非 0 退出（不是静默 warn）",
        rc != 0 and "需要源目录" in (out or ""), (out or "")[:200])


def p8_validation_gates():
    """P8：validate 的输入/退出码守卫（G1/G1b）、合并留痕可检形态（T6）、
    verify 的 C5/C9/C15/C14 工单（G3/G4/T4/T3）。"""
    kb8, cfg8 = build_base("p8_gates")
    add_notes(kb8)
    aggregates(kb8)
    src = os.path.join(WORK, "p8_gates", "source")
    units_p = os.path.join(kb8, "_meta", "units.jsonl")
    VAL = os.path.join(SCRIPTS, "validate_extraction.py")
    V = os.path.join(SCRIPTS, "verify.py")

    # ---- 造 units 夹具：locator 用真实偏移，免得 quote 校验自己先把测试搞红 ----
    with open(os.path.join(src, "选品方法.md"), encoding="utf-8") as fh:
        text = fh.read()
    q1 = "选品看两个轴"
    q2 = "判断需求强度用搜索量同比"
    i1, i2 = text.index(q1), text.index(q2)
    L1 = "§一#char=%d-%d" % (i1, i1 + len(q1))
    L2 = "§一#char=%d-%d" % (i2, i2 + len(q2))
    good = {"id": "g1", "doc_id": "选品方法", "type": "claim", "confidence": "high",
            "text": "两轴定义", "evidence": {"file": "选品方法.md", "locator": L1, "quote": q1}}
    trimmed = {"id": "t1", "doc_id": "选品方法", "type": "procedure", "confidence": "high",
               "steps": [{"order": 1, "action": "定需求轴", "locator": L1},
                         {"order": 2, "action": "定竞争轴", "locator": L2}],
               "evidence": [{"file": "选品方法.md", "locator": L1, "quote": q1}]}
    thin = {"id": "t2", "doc_id": "选品方法", "type": "concept", "confidence": "medium",
            "evidence": [{"file": "选品方法.md", "locator": L1, "quote": q1},
                         {"file": "选品方法.md", "quote": "这一项没有 locator"}]}
    dup = {"id": "t3", "doc_id": "选品方法", "type": "concept", "confidence": "medium",
           "evidence": [{"file": "选品方法.md", "locator": L1, "quote": q1},
                        {"file": "选品方法.md", "locator": L1, "quote": q1}]}

    def write_units(rows):
        os.makedirs(os.path.dirname(units_p), exist_ok=True)
        with open(units_p, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    def validate(label, want_rc):
        return run([VAL, "--kb", kb8, "--source-root", src], want_rc, label)

    # G1：units.jsonl 不存在 → 不许说"通过"
    if os.path.isfile(units_p):
        os.remove(units_p)
    rc, out = validate("P8 G1 units 缺失", 1)
    check("G1 units.jsonl 不存在 → exit 1、不打「通过 ✓」",
          rc == 1 and "输入缺失" in out and "通过 ✓" not in out, (out or "")[-260:])

    # G1：存在但 0 条 → 同样不许通过
    write_units([])
    rc, out = validate("P8 G1 units 0 条", 1)
    check("G1 units.jsonl 0 条 → exit 1", rc == 1 and "输入缺失" in out, (out or "")[-200:])

    # G1b：合法单元 → exit 0；且单来源库明写「无合并记录可校验」
    write_units([good])
    rc, out = validate("P8 G1b 合法单元", 0)
    check("G1b 合法 units → exit 0 通过", rc == 0 and "通过 ✓" in out, (out or "")[-200:])
    check("T6 单来源库明写「无合并记录可校验」（不假装全检）",
          "无合并记录可校验" in out, [l for l in (out or "").splitlines() if "合并" in l])

    # T6：三种可检削痕形态
    write_units([good, trimmed, thin, dup])
    rc, out = validate("P8 T6 三种削痕", 1)
    rep = json.load(open(os.path.join(kb8, "_meta", "validate_report.json"), encoding="utf-8"))
    check("T6 三要素不齐 → evidence_thin 命中",
          any(x["id"] == "t2" for x in rep["evidence_thin"]), str(rep["evidence_thin"]))
    check("T6 合并指向同一 locator → evidence_dup_locator 命中",
          any(x["id"] == "t3" for x in rep["evidence_dup_locator"]), str(rep["evidence_dup_locator"]))
    check("T6 步骤跨段只留 1 条 → evidence_trimmed 命中",
          any(x["id"] == "t1" for x in rep["evidence_trimmed"]), str(rep["evidence_trimmed"]))
    check("T6 削痕计入不放行（exit 1、pass=false）", rc == 1 and rep["pass"] is False,
          "rc=%s pass=%s" % (rc, rep["pass"]))
    check("T6 合并条数不可反查要明写在 report 里",
          rep["merge_count_checkable"] is False and "不可反查" in rep["merge_note"],
          rep.get("merge_note", ""))

    # ---- verify 侧：C5 / C9 / C15 / C14 工单 ----
    if os.path.isfile(units_p):
        os.remove(units_p)          # 后面 verify 不跑 validate，清掉夹具免得留垃圾
    d8 = os.path.join(kb8, "工作流", FLOW, STAGE)

    def verify(want_rc, label, extra=None):
        args = [V, "--kb", kb8, "--config", cfg8] + (extra or [])
        return run(args, want_rc, label)

    def line_of(out, cid):
        return c_line(out, cid)

    # G3：sources 为空 → C5 FAIL（以前只查 5 篇样板，逐篇根本没验）
    w(os.path.join(d8, "无来源样本.md"), NOTE_C.replace("封面标题的数字承诺", "无来源样本", 1)
      .replace("sources:\n  - 封面标题.md", "sources: []"))
    aggregates(kb8)
    rc, out = verify(1, "P8 G3 sources 为空")
    l = line_of(out, "C5")
    check("G3 逐篇 sources 为空 → C5 FAIL（不再只抽样板）",
          l.startswith("[FAIL]") and "sources 为空" in l and rc == 1, l)
    os.remove(os.path.join(d8, "无来源样本.md"))

    # G3：sources 指向磁盘上不存在的文件 → C5 FAIL
    w(os.path.join(d8, "假来源样本.md"), NOTE_C.replace("封面标题的数字承诺", "假来源样本", 1)
      .replace("  - 封面标题.md", "  - 根本没有这个资料.md"))
    aggregates(kb8)
    rc, out = verify(1, "P8 G3 来源不可达")
    l = line_of(out, "C5")
    check("G3 来源路径不可达 → C5 FAIL", l.startswith("[FAIL]") and "不可达" in l and rc == 1, l)
    os.remove(os.path.join(d8, "假来源样本.md"))

    # G3：不带 config（拿不到 source_root）时只 warn，不硬 fail
    aggregates(kb8)
    rc, out = run([V, "--kb", kb8], 0, "P8 G3 无 config")
    l = line_of(out, "C5")
    check("G3 无 config 时可达性未验 → C5 **warn 不 fail**",
          l.startswith("[WARN]") and "可达性未验" in l and rc == 0, l)

    # G4：缺三段分标 → C9 必须 FAIL（负控：防止以后又被改回 warn）
    #   注意：样本正文里**不能出现那三个标记词**——C9 判的是字面存在，
    #   写"没有资料原话/归纳结论/AI 推断三段"反而把三个词都带上了，样本自证清白。
    w(os.path.join(d8, "缺分标样本.md"), """---
title: 缺分标样本
flow: %s
stage: %s
substage: 案例
sources:
  - 选品方法.md
confidence: high
---

# 缺分标样本

只有一句结论，没有分标小节。
""" % (FLOW, STAGE))
    aggregates(kb8)
    rc, out = verify(1, "P8 G4 缺三段分标（负控）")
    l = line_of(out, "C9")
    check("G4 负控：缺三段分标 → C9 **必须 FAIL**、exit 非 0",
          l.startswith("[FAIL]") and rc == 1, l)
    os.remove(os.path.join(d8, "缺分标样本.md"))

    # T4：confidence: low → C15 warn、exit 不变（只提醒，不拦路）
    low = os.path.join(d8, C_STEM + ".md")
    with open(low, encoding="utf-8") as fh:
        keep = fh.read()
    w(low, keep.replace("confidence: high", "confidence: low", 1))
    aggregates(kb8)
    rc, out = verify(0, "P8 T4 confidence low")
    l = line_of(out, "C15")
    check("T4 low 笔记 → C15 WARN、**不影响 exit**",
          l.startswith("[WARN]") and "99_收件箱" in l and rc == 0, l)
    w(low, keep)

    # T4：confidence 缺失 / 值域非法 → 也在 C15 里
    w(low, keep.replace("confidence: high\n", "", 1))
    aggregates(kb8)
    rc, out = verify(0, "P8 T4 confidence 缺失")
    check("T4 缺 confidence → C15 WARN 列出篇目",
          "缺 confidence" in line_of(out, "C15") and rc == 0, line_of(out, "C15"))
    w(low, keep)
    aggregates(kb8)

    # T3：C14 发现源文件被改 → 工单列出依赖它的笔记，且**只列不写**
    run([V, "--kb", kb8, "--config", cfg8, "--source-root", src, "--snapshot-source"],
        0, "P8 T3 建基线")
    note_before = {p: os.path.getmtime(os.path.join(r, p))
                   for r, _, fs in os.walk(os.path.join(kb8, "工作流")) for p in fs}
    with open(os.path.join(src, "选品方法.md"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n被人添了一句。\n")
    rc, out = verify(1, "P8 T3 源文件被改 → 工单")
    l = line_of(out, "C14")
    check("T3 源文件被改 → C14 FAIL", l.startswith("[FAIL]") and rc == 1, l)
    check("T3 工单标题与内容都在（列出依赖该源文件的笔记）",
          "[C14 工单] 以下笔记依赖已变更源资料" in out and B_STEM in out,
          "\n".join(x for x in (out or "").splitlines() if "工单" in x or "  - " in x)[:400])
    check("T3 工单声明只列不改", "本工单只列不改" in out or "verify 不写任何笔记" in out)
    note_after = {p: os.path.getmtime(os.path.join(r, p))
                  for r, _, fs in os.walk(os.path.join(kb8, "工作流")) for p in fs}
    check("T3 出工单时没有写任何笔记文件", note_before == note_after,
          "差异=%s" % sorted(set(note_before) ^ set(note_after))[:3])
    with open(os.path.join(src, "选品方法.md"), encoding="utf-8") as fh:
        fixed = fh.read().replace("\n被人添了一句。\n", "")
    with open(os.path.join(src, "选品方法.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(fixed)
    rc, out = verify(0, "P8 T3 还原后")
    check("T3 源文件还原后 C14 回到 PASS", line_of(out, "C14").startswith("[PASS]"),
          line_of(out, "C14"))


# ---------------------------------------------------------------- P9
# 六组断言：check_verbatim_lite 的两个方向 / units-on 让位 / 前缀白名单本身
#          / HOOK_GRAM_RATIO 双向 / C10 目标解析范围。
# 夹具为什么用 15 不用 20：源夹具里「5到20人」确有 20，写 20 会假过——
# 这正是"「多」的参照必须是本篇引用的块，不能是整篇文件"的实证（真库撞出来的）。
LITE_SRC_NAME = "逐字夹具.md"
LITE_L1 = "团队规模在5到20人之间，期间也做了100多人的企业内部BOT，基本上5-10分钟就能梳理一个可介入的场景。"
LITE_L2 = "基本上5-10分钟就能梳理一个可介入的场景"
LITE_L3 = "报告生成时间从60分钟降到5分钟以内"
# 发现 39 的回归面专用块：**标题带章节号**（3.1.2），正文另带两个数（2026／8 分钟）。
LITE_HEAD4 = "3.1.2 定位符剥噪块"
LITE_L4 = "这套流程 2026 年上线，单条成片时长 8 分钟。"
LITE_SRC_TEXT = ("# 逐字夹具\n\n## 块一\n\n" + LITE_L1 +
                 "\n\n![缩图](assets/x/001.png)\n\n## 块二\n\n"
                 "1. " + LITE_L3 + "；\n2. 前端日处理量翻倍。\n\n"
                 "这一步收百来块的基本费用，建立信任和验证价值。\n"
                 "\n\n## " + LITE_HEAD4 + "\n\n" + LITE_L4 + "\n")
SRC_NOTE_STEM = "来源·逐字夹具"
LONG_QUERY = ("我一个人不会写代码，能帮中小企业做AI落地吗，客户从哪来，"
              "怎么收费才不至于第一单就亏钱")
IRRELEVANT_QUERIES = ["封面标题里的数字承诺怎么验证", "怎么用Stable Diffusion出电商主图",
                      "公众号起号前30篇怎么排"]


def lite_loc(quote):
    """按 quote 在夹具源文本里的真实位置算 locator；找不到或不唯一直接抛，绝不用编的偏移。"""
    i = LITE_SRC_TEXT.find(quote)
    assert i >= 0, "夹具 quote 不在源文本里：%s" % quote[:24]
    assert LITE_SRC_TEXT.count(quote) == 1, "夹具 quote 不唯一：%s" % quote[:24]
    return "§块一#char=%d-%d" % (i, i + len(quote))


def lite_note(kb, stem, title, hooks, locs, quote, points, todos, infers):
    """结构合法的原子笔记（C4/C9/C11 都过），正文数字由每条断言各自控制。"""
    fm = ["---", "title: %s" % title, "flow: %s" % FLOW, "stage: %s" % STAGE,
          "substage: 子技巧", "domains: [AI]", "forms: [方法论]", "tools: []",
          "types: [方法]", "projects: []", "topics: [逐字校验]", "q_hooks:"]
    fm += ["  - %s" % h for h in hooks]
    fm += ["sources:", "  - %s" % LITE_SRC_NAME, "source_locator:                 # 首项 = 主块"]
    fm += ["  - %s" % l for l in locs]
    fm += ["confidence: high", "status: confirmed", "created: 2026-10-04", "---", ""]
    body = ["# %s" % title, "", "> %s" % title, "", "## 资料原话（evidence.quote）", "",
            "> %s" % quote, "> —— `%s`" % locs[0], "", "## 归纳结论", ""]
    body += ["- %s" % p for p in points]
    body += ["", "## 可执行清单", ""]
    body += ["%d. %s" % (i + 1, t) for i, t in enumerate(todos)]
    body += ["", "## AI 推断（inference）", ""]
    body += ["- %s" % x for x in infers]
    body += ["", "## 关联", "", "- 来源：[[%s]]" % SRC_NOTE_STEM, ""]
    w(os.path.join(kb, "工作流", FLOW, STAGE, stem + ".md"), "\n".join(fm + body))


def p9_verbatim_and_gates():
    """P9：units-off 逐字替身 + units-on 让位 + 前缀白名单 + hook 阈值双向 + C10 目标范围。"""
    LITE = os.path.join(SCRIPTS, "check_verbatim_lite.py")
    kb9, cfg9 = build_base("p9_lite")
    src_dir = os.path.join(WORK, "p9_lite", "source")
    w(os.path.join(src_dir, LITE_SRC_NAME), LITE_SRC_TEXT)

    loc_full = lite_loc(LITE_L1)
    loc_short = lite_loc(LITE_L2)
    i3 = LITE_SRC_TEXT.find(LITE_L3)
    loc_b2 = "§块二#char=%d-%d" % (i3, i3 + len(LITE_L3))

    lite_note(kb9, "定稿逐字篇", "引用块里有的数都写全了",
              ["逐字校验会不会误报", "定稿笔记的数从哪来", "引用块怎么定"],
              [loc_full], LITE_L1,
              ["5到20人是团队规模，100多人是 BOT 规模，5-10分钟是梳理时长"],
              ["按 5-10 分钟的时长安排现场演示"],
              ["作者未提、我的推论：这套规模描述适合中小客户场景"])
    lite_note(kb9, "自创数字篇", "把时长写成本块里没有的数",
              ["梳理一个场景要多久", "时长被改写怎么发现", "本块里没有的数"],
              [loc_short], LITE_L2,
              ["梳理一个场景很快"],
              ["配合「15分钟出一个可介入场景」这类时间量来谈交付"],
              ["作者未提、我的推论：现场演示控制在半小时内"])
    lite_note(kb9, "缺数拆篇篇", "只引一句，本块其余数字没进正文",
              ["一块里还有几个数", "怎么知道有东西没抽完", "拆篇候选从哪来"],
              [loc_short], LITE_L2,
              ["这块只挑了一句话成篇"],
              ["其余结论另立笔记"],
              ["作者未提、我的推论：本块还有规模类数字没进本篇"])
    # 跨块篇：引用块一 + 块二 → 「多」的参照是两个块的并，块二里的 5分钟以内 不该被报成自创
    lite_note(kb9, "跨块引用篇", "承诺与回证分属两个块",
              ["承诺的动作怎么补验证", "跑通之后数据有没有变", "两块合起来才答得完吗"],
              [loc_full, loc_b2], LITE_L1,
              ["承诺的自动化动作，回证是处理量数据；",
               "同块其他结论：报告生成时间从60分钟降到5分钟以内，翻倍的是日处理量"],
              ["跨块时主块进 source_locator 首项，其余块按引用顺序往下列"],
              ["作者未提、我的推论：承诺与回证分属两块，只校首项会漏，所以按块之并比对"])
    lite_note(kb9, "前缀豁免篇", "声明过的自创数字应被豁免",
              ["不会写代码做企业服务会不会露怯", "自创阈值能不能写进笔记", "怎么声明这是我的推断"],
              [loc_full], LITE_L1,
              ["三条判据同时成立才值得进场"],
              ["先做认知差诊断再谈报价"],
              ["作者未提、我的推论：可把进场阈值定在 300 条以下先试运行一季"])
    lite_note(kb9, "前缀违规篇", "不带前缀的自创数字不该被豁免",
              ["无前缀的推断行会怎样", "免责前缀有什么用", "混在推断里的数"],
              [loc_full], LITE_L1,
              ["无前缀的推断行仍按正文校验"],
              ["先补前缀再入库"],
              ["建议把阈值定在 400 条以下试运行一季"])
    # 定位符剥噪篇：**同一篇里两种定位符写法都用上**（evidence 用 §…#char=、清单用 [char=a-b]），
    # 数值全部照抄原文 → 「多」必须是空的；主块标题带章节号而正文不重复它 → 「缺」里不得有 3.1.2。
    i4 = LITE_SRC_TEXT.find(LITE_L4)
    loc4 = "§%s#char=%d-%d" % (LITE_HEAD4, i4, i4 + len(LITE_L4))
    lite_note(kb9, "定位符剥噪篇", "定位符自身的数字不该被当自创",
              ["定位符里的数字算不算正文数值", "章节号会不会被当成缺数", "剥噪退化了谁会报"],
              [loc4], LITE_L4,
              ["2026 年上线，单条成片 8 分钟"],
              ["上线年份与时长照抄：2026 年、8 分钟 —— [char=%d-%d]" % (i4, i4 + len(LITE_L4))],
              ["作者未提、我的推论：这块只验定位符文本的剥噪，不引入新数值"])
    w(os.path.join(kb9, "素材库", "_来源地图", "%s.md" % SRC_NOTE_STEM),
      "---\ntitle: %s\nsource_doc: %s\nderived_notes:\n  - [[定稿逐字篇]]\n"
      "created: 2026-10-04\n---\n\n# %s\n\n"
      "- 块数、图片引用数这类语料元数据记在这里，不写进原子笔记正文\n"
      "- 顺手留一条**死链** [[早被删掉的一篇旧笔记]]：来源笔记自己的出链不在被检范围"
      "（发现 25 残留②=未定：这条断言钉的是「现在确实不检」这个事实，不是「应该这样」）\n"
      % (SRC_NOTE_STEM, LITE_SRC_NAME, SRC_NOTE_STEM))

    def lite(label="P9 check_verbatim_lite"):
        return run([LITE, "--notes-dir", os.path.join(kb9, "工作流"),
                    "--source-root", src_dir, "--format", "json"], 0, label)

    rc, out = lite()
    try:
        data = json.loads(out)
        by = {os.path.basename(r["note"])[:-3]: r for r in data.get("rows", [])}
    except Exception:
        check("P9 check_verbatim_lite 输出可解析 JSON", False, (out or "")[:300])
        return

    def extra_of(n):
        return (by.get(n) or {}).get("extra")

    def missing_of(n):
        return (by.get(n) or {}).get("missing")

    # ---- 组 1：「多」主判据抓到自创数字，且只抓到它（剥噪没退化）----
    check("P9-1 自创的 15 被「多」抓到，且 extra 里没有图片编号/列表标记噪声",
          extra_of("自创数字篇") == ["15"], "extra=%s" % extra_of("自创数字篇"))

    # ---- 组 2：零假警 + 「缺」当拆篇候选 ----
    check("P9-2a 定稿逐字篇「多」=0（假警防线）", extra_of("定稿逐字篇") == [],
          "extra=%s" % extra_of("定稿逐字篇"))
    check("P9-2b 「缺」列出本块有、本篇没写的数（100 在列）＝1:N 拆篇候选",
          "100" in (missing_of("缺数拆篇篇") or []), "missing=%s" % missing_of("缺数拆篇篇"))
    r_cross = by.get("跨块引用篇") or {}
    mb = r_cross.get("main_block") or [0, 0]
    fa = int(loc_full.split("#char=")[1].split("-")[0])
    fb = int(loc_full.split("#char=")[1].split("-")[1])
    check("P9-2e 跨块篇被认出跨块；主块**包住**首项区间且比它宽（主块=块，不是贴紧的 quote 区间）",
          r_cross.get("cross_block") is True and r_cross.get("extra") == []
          and mb[0] <= fa and mb[1] >= fb and (mb[1] - mb[0]) > (fb - fa),
          "cross=%s extra=%s main=%s quote=[%d,%d]"
          % (r_cross.get("cross_block"), r_cross.get("extra"), mb, fa, fb))
    check("P9-2c 图片编号 001 / 画板 token 串不被当数值",
          not ({"001", "001.", "1"} & set(missing_of("定稿逐字篇") or [])),
          "missing=%s" % missing_of("定稿逐字篇"))
    check("P9-2d warn only：rc=0、blocking=false、not_checked 明写",
          rc == 0 and data.get("blocking") is False and len(data.get("not_checked") or []) >= 4,
          "rc=%s blocking=%s not_checked=%s" % (rc, data.get("blocking"),
                                                len(data.get("not_checked") or [])))

    # ---- 组 3：units-on 让位 validate ----
    units = os.path.join(kb9, "_meta", "units.jsonl")
    w(units, json.dumps({"id": "doc-x-claim-1", "type": "claim", "text": "占位",
                         "file": LITE_SRC_NAME, "locator": "§块一#char=0-10",
                         "quote": LITE_L2[:10], "confidence": "high", "evidence": []},
                        ensure_ascii=False) + "\n")
    rc3, out3 = run([LITE, "--notes-dir", os.path.join(kb9, "工作流"),
                     "--source-root", src_dir], 0, "P9 units-on 让位")
    check("P9-3 units 开着 → 让位 validate、明写「未做任何校验」、rc=0（不是错误也不假装跑过）",
          "units 已开" in out3 and "未做任何校验" in out3 and rc3 == 0, (out3 or "")[:200])
    os.remove(units)

    # ---- 组 4：前缀白名单本身（有人改匹配逻辑，这条必须红）----
    check("P9-4a 带「作者未提、我的推论：」的 300 被豁免（不出现在「多」）",
          "300" not in (extra_of("前缀豁免篇") or []), "extra=%s" % extra_of("前缀豁免篇"))
    check("P9-4b 不带前缀的 400 仍被「多」抓到（白名单外照查，前缀不是逃生门）",
          extra_of("前缀违规篇") == ["400"], "extra=%s" % extra_of("前缀违规篇"))

    # ---- 组 5：HOOK_GRAM_RATIO 双向 ----
    aggregates(kb9)

    def hook_hits(query=None, route=None, label="P9 recall"):
        cmd = [os.path.join(SCRIPTS, "search_index.py"), "recall",
               "--kb", kb9, "--json"]
        if route:
            cmd += ["--route-json", json.dumps(route, ensure_ascii=False)]
        if query:
            cmd += ["--query", query]
        rcx, outx = run(cmd, 0, label)
        try:
            d = json.loads(outx)
        except Exception:
            return None
        return [h for h in d.get("hits", []) if "hook" in h.get("channels", [])]

    hl = hook_hits(query=LONG_QUERY, label="P9 长问句 hook")
    check("P9-5a 长问句 hook 命中 >0（只用分母=query 会恒 0，这条钉住判据 ③）",
          hl is not None and len(hl) > 0,
          "命中=%s" % (None if hl is None else [h["path"][-24:] for h in hl]))
    bad = {q: [h["path"] for h in (hook_hits(query=q, label="P9 无关查询") or [])]
           for q in IRRELEVANT_QUERIES if hook_hits(query=q, label="P9 无关查询")}
    check("P9-5b 无关查询 hook 命中必须全 0（放宽阈值不能把通道变成全匹配）",
          not bad, json.dumps(bad, ensure_ascii=False)[:220])
    hs = hook_hits(route={"keywords": ["不会写代码", "AI落地"], "top_k": 5},
                   label="P9 短 keywords")
    check("P9-5c 路由短 keywords 的 hook 命中没被 ③ 打回 0（短语路径不回归）",
          hs is not None and len(hs) > 0, "命中=%s" % (None if hs is None else len(hs)))

    # ---- 组 6：C10 目标解析范围（发现 28 的防线）----
    V = os.path.join(SCRIPTS, "verify.py")
    rcv, outv = run([V, "--kb", kb9, "--config", cfg9], None, "P9 C10 目标在 素材库/_来源地图")
    l6 = c_line(outv, "C10")
    print("   C10 →", l6[:150])
    check("P9-6a 指向来源笔记的 [[ ]] 判 PASS（扩的是目标解析范围，不是判据）",
          l6.startswith("[PASS]"), l6[:200])
    check("P9-6b 来源笔记**自己正文的出链**仍不被校验（发现 25 残留②=未定的现状，不是应然）",
          "早被删掉的一篇旧笔记" not in l6, l6[:220])
    tgt = os.path.join(kb9, "素材库", "_来源地图", "%s.md" % SRC_NOTE_STEM)
    os.rename(tgt, tgt + ".bak")
    rcv2, outv2 = run([V, "--kb", kb9, "--config", cfg9], None, "P9 C10 目标消失")
    l7 = c_line(outv2, "C10")
    check("P9-6c 目标真消失时 C10 仍报失效（warn）——判据没被改软",
          l7.startswith("[WARN]") and SRC_NOTE_STEM in l7, l7[:200])
    os.rename(tgt + ".bak", tgt)
    rcv3, outv3 = run([V, "--kb", kb9, "--config", cfg9], None, "P9 C10 还原")
    check("P9-6d 还原后 C10 回到 PASS", c_line(outv3, "C10").startswith("[PASS]"),
          c_line(outv3, "C10")[:150])

    # ---- 组 7：发现 39 的剥噪不许退化（定位符文本是元数据，不是正文数值）----
    def lite_neg(banned):
        """把某个剥噪正则换成"永不匹配"的常量再跑同一份夹具（banned ∈ {bracket, headnum}）。"""
        drv = os.path.join(WORK, "p9_lite", "neg_%s.py" % banned)
        pat = {"bracket": "LOCATOR_BRACKET_RE", "headnum": "HEADING_NUM_RE"}[banned]
        w(drv, "import sys, io, runpy\n"
               "sys.path.insert(0, %r)\n"
               "import check_verbatim_lite as cvl\n"
               "import re\n"
               "cvl.%s = re.compile(r'ZZZ_NEVER_MATCH_ZZZ')\n"
               "sys.argv = %r\n"
               "cvl.main()\n"
               % (SCRIPTS, pat,
                  ["check_verbatim_lite.py", "--notes-dir", os.path.join(kb9, "工作流"),
                   "--source-root", src_dir, "--format", "json"]))
        p = subprocess.run([sys.executable, drv], capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        try:
            rows = json.loads(p.stdout).get("rows", [])
        except Exception:
            return None
        return {os.path.basename(r["note"])[:-3]: r for r in rows}

    e_pos = extra_of("定位符剥噪篇") or []
    m_pos = missing_of("定位符剥噪篇") or []
    nb = lite_neg("bracket")
    e_neg = ((nb or {}).get("定位符剥噪篇") or {}).get("extra")
    check("P9-7a **发现 39 正判据**：同一篇里 `§…#char=a-b`（evidence 行）与 `[char=a-b]`（清单行）**两种定位符写法**"
          "都不许被当成正文数值——「多」必须为空（那篇的 2026／8 是照抄原文的，剥噪退化时「多」立刻冒出 char 区间）。"
          "**负控**：把 `LOCATOR_BRACKET_RE` 摘成永不匹配再跑同一夹具，「多」必须**由 0 变非 0**（不红就是空断言）",
          e_pos == [] and nb is not None and bool(e_neg),
          "正跑 extra=%s｜摘掉行内定位符剥噪后 extra=%s" % (e_pos, (e_neg or [])[:3]))
    nh = lite_neg("headnum")
    m_neg = ((nh or {}).get("定位符剥噪篇") or {}).get("missing")
    check("P9-7b **对称剥**：主块标题带章节号（`## 3.1.2 定位符剥噪块`）而笔记正文不重复它 →"
          "「缺」里**不得**出现 `3.1.2`（笔记侧剥了、源侧不剥就会虚增一条假「缺」）。"
          "**负控**：把 `HEADING_NUM_RE` 摘掉再跑，`3.1.2` 必须冒出来",
          "3.1.2" not in m_pos and nh is not None and any(x == "3.1.2" for x in (m_neg or [])),
          "正跑 missing 含 3.1.2=%s｜摘掉源侧章节号剥噪后 missing=%s" % (
              "3.1.2" in m_pos, [x for x in (m_neg or []) if x == "3.1.2"] or "(没冒出，判据失效)"))


# ---------------------------------------------------------------- P10
# progress.py 的 ①–⑨ 组、16 条断言：三档计数 / next_todo（含 --path-prefix）/
# coverage 声称字段已作废（③ 负控）/ 两类不一致各造一例 /
# JSON 逐字节确定 / **只读**（mtime + 内容不变）/ 输入守卫。
# 夹具要点：chunk 的 char 区间全部由**真文本算出来**（p10_split），不硬编码偏移——
# 硬编码的夹具会在源文本被改过一次之后静默变成"全绿但没在测东西"。
P10_DOCS = {
    "docA.md": ("# 甲篇\n\n## 段一\n\n第一个结论。\n\n## 段二\n\n第二个结论。\n\n"
                "## 段三\n\n第三个结论。\n"),
    "docB.md": "# 乙篇\n\n## 段一\n\n甲。\n\n## 段二\n\n乙。\n\n## 段三\n\n丙。\n\n## 段四\n\n丁。\n",
    "docC.md": "# 丙篇\n\n## 段一\n\n戊。\n\n## 段二\n\n己。\n",
    "docD.md": "# 丁篇\n\n## 段一\n\n目录性内容。\n\n## 段二\n\n还是目录。\n",
}
# 每篇的第一块是 H1 标题块（低价值），段块从 index 1 开始——与 doc_map 的切块行为一致。
P10_HIGH = {"docA.md": [False, True, True, True],
            "docB.md": [False, True, True, True, True],
            "docC.md": [False, True, True],
            "docD.md": [False, False, False]}
P10_PICK = {"docA.md": [1, 2, 3], "docB.md": [1, 2], "docC.md": [], "docD.md": []}


def p10_split(text):
    """按 #/## 标题切块 → [(heading, start, end)]，与 doc_map 同思路的极简版。"""
    marks = sorted(set([0] + [m.start() for m in re.finditer(r"(?m)^#{1,2} ", text)]))
    out = []
    for i, s in enumerate(marks):
        e = marks[i + 1] if i + 1 < len(marks) else len(text)
        out.append((re.sub(r"^#+\s*", "", text[s:e].split("\n")[0]).strip(), s, e))
    return out


def p10_maps():
    rows = []
    for name in sorted(P10_DOCS):
        text, hs = P10_DOCS[name], P10_HIGH[name]
        chunks = p10_split(text)
        rows.append({
            "doc_id": "doc-" + name[:4], "path": name, "title": name[:-3],
            "chunks": [{"chunk_id": "doc-%s-%d" % (name[:4], i), "heading": h,
                        "char_start": s, "char_end": e, "char_len": e - s,
                        "overlap_start": s, "features": ["numbers"], "density": 0.6,
                        "high_value": bool(hs[i]), "candidate_topics": [],
                        "skip_reason": None if hs[i] else "低密度"}
                       for i, (h, s, e) in enumerate(chunks)],
            "coverage": {"chunks_total": len(chunks), "high_value": sum(hs),
                         "low_value": len(chunks) - sum(hs), "chunks_processed": 0,
                         "chunks_skipped": 0, "high_value_done": False, "status": "mapped"},
        })
    return rows


def p10_build(tag):
    """临时库 + 源目录 + doc_maps.jsonl + 笔记；返回 (kb, maps_path, cfg)。"""
    kb, cfg = build_base(tag)
    src = os.path.join(WORK, tag, "source")
    for name, text in P10_DOCS.items():
        w(os.path.join(src, name), text)
    maps = os.path.join(kb, "_meta", "doc_maps.jsonl")
    w(maps, "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                      for r in p10_maps()) + "\n")
    for name in sorted(P10_PICK):
        for idx in P10_PICK[name]:
            h, s, e = p10_split(P10_DOCS[name])[idx]
            stem = "%s_块%d_笔记" % (name[:-3], idx)
            w(os.path.join(kb, "工作流", FLOW, STAGE, stem + ".md"),
              "---\ntitle: %s\nflow: %s\nstage: %s\nsubstage: 子技巧\n"
              "domains: [内容创作]\nforms: [方法论]\ntools: []\ntypes: [方法]\nprojects: []\n"
              "topics: [进度夹具]\nq_hooks:\n  - 这块讲了什么\n"
              "sources:\n  - %s\nsource_locator:\n  - §%s#char=%d-%d\n"
              "confidence: high\nstatus: confirmed\ncreated: 2026-10-04\n---\n\n"
              "# %s\n\n> 一句话。\n\n## 资料原话（evidence.quote）\n\n> 略\n"
              "> —— `§%s#char=%d-%d`\n\n## 归纳结论\n\n- 略；\n\n## 可执行清单\n\n1. 略；\n\n"
              "## AI 推断（inference）\n\n- 作者未提、我的推论：略。\n"
              % (stem, FLOW, STAGE, name, h, s, e, stem, h, s, e))
    return kb, maps, cfg


def p10_fingerprint(root):
    import hashlib
    """整库 .md 与 .jsonl 的 (mtime_ns, sha256) 指纹——用来证明 progress 真的只读。"""
    out = {}
    for dp, _, fs in os.walk(root):
        for fn in fs:
            if fn.endswith(".md") or fn.endswith(".jsonl"):
                p = os.path.join(dp, fn)
                st = os.stat(p)
                with open(p, "rb") as fh:
                    digest = hashlib.sha256(fh.read()).hexdigest()[:12]
                out[p.replace("\\", "/")] = (st.st_mtime_ns, digest)
    return out


def p10_progress():
    """P10：进度派生器 ①–⑨ 组、16 条断言。"""
    PROG = os.path.join(SCRIPTS, "progress.py")
    kb, maps, cfg = p10_build("p10_progress")
    nd = os.path.join(kb, "工作流")

    def run_p(extra=None, want_rc=0, label="P10 progress"):
        return run([PROG, "--notes-dir", nd] + (extra or []), want_rc, label)

    def parsed(extra=None):
        rc, out = run_p(extra)
        try:
            return rc, json.loads(out)
        except Exception:
            return rc, None

    rc, data = parsed(["--format", "json"])
    if data is None:
        check("P10 progress --format json 可解析", False, "")
        return
    s = data["summary"]
    # ---- ① 三档 + no_hv 计数 ----
    check("P10-① 三档计数正确：done 1 / partial 1 / todo 1 / no_hv 1；"
          "高价值块 9、已抽 5、未抽 4",
          (s["done_docs"], s["partial_docs"], s["todo_docs"], s["no_hv_docs"],
           s["total_high_value_chunks"], s["done_chunks"], s["undone_high_value_chunks"])
          == (1, 1, 1, 1, 9, 5, 4), json.dumps(s, ensure_ascii=False, sort_keys=True))
    check("P10-①b status 分档按文档逐个对（docA done / docB partial / docC todo / docD no_hv）",
          {r["path"]: r["status"] for r in data["docs"]}
          == {"docA.md": "done", "docB.md": "partial", "docC.md": "todo", "docD.md": "no_hv"},
          json.dumps({r["path"]: r["status"] for r in data["docs"]}, ensure_ascii=False))

    # ---- ② next_todo：全局 = docB 第一个未引用块；带前缀 = 该范围内第一个 ----
    check("P10-②a 全局 next_todo = docB 未抽的第一块（docA 已 done，按路径+块序排）",
          data["next_todo"]["doc"] == "docB.md", json.dumps(data["next_todo"], ensure_ascii=False))
    _, d2 = parsed(["--format", "json", "--path-prefix", "docC"])
    check("P10-②b --path-prefix 只换起点，不换判据：范围内 next_todo = docC 第一个高价值块"
          "（块 0 是 H1 标题块、低价值，不该被当欠债）",
          d2 and d2["next_todo"]["doc"] == "docC.md"
          and d2["next_todo"]["chunk_id"] == "doc-docC-1", json.dumps((d2 or {}).get("next_todo"),
                                                                 ensure_ascii=False))
    rc, out = run_p(["--emit-todo"], 0, "P10 emit-todo")
    check("P10-②c --emit-todo 单行 = doc\\tchunk_id\\treason，且与 json 版一致",
          out.startswith("docB.md\tdoc-docB-3\t") and data["next_todo"]["chunk_id"] == "doc-docB-3",
          out[:120])
    check("P10-②d 前缀过滤时**全库与范围内两份计数都给**（不伪装、不装没生效）",
          "scope" in d2 and d2["scope"]["summary"]["total_docs"] == 1
          and d2["summary"]["total_docs"] == 4,
          json.dumps({"scope": (d2 or {}).get("scope", {}).get("summary"),
                      "all": (d2 or {}).get("summary", {}).get("total_docs")}, ensure_ascii=False))

    # ---- ③ coverage 声称字段**已作废**：progress 不读它（B 裁决）----
    # 夹具里同时成立两处"结构性必然矛盾"：docC 声称 processed=2/high_value_done=true 而派生 0 引用、
    # docA/docB 派生 done>0 而声称恒 0。旧的两类 claim_* 不一致就是靠这两处成立的，现在必须都不出现。
    pristine_maps = open(maps, encoding="utf-8").read()
    _, o_before = run_p(["--format", "json"], 0, "P10 作废字段·改前")
    mrows = p10_maps()
    for r in mrows:
        if r["path"] == "docC.md":
            r["coverage"]["chunks_processed"] = 2
            r["coverage"]["high_value_done"] = True
    w(maps, "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in mrows) + "\n")
    _, d5 = parsed(["--format", "json"])
    _, o_after = run_p(["--format", "json"], 0, "P10 作废字段·改后")
    off = [i for i in (d5 or {}).get("inconsistencies", [])
           if i["type"] not in ("ghost_locator", "unmapped_source")]
    check("P10-③ coverage 的 chunks_processed/high_value_done 已作废：改声称值后 --format json"
          "**逐字节不变**、输出里不出现该字段名、不一致只可能是 ghost/unmapped 两类"
          "（docC 声称 2 却 0 引用 + docA 派生 3 却声称 0，两处矛盾都不报）",
          d5 is not None and o_before == o_after
          and "chunks_processed" not in o_after and not off,
          "改前 %dB / 改后 %dB｜越界类型 %s｜字段名出现 %d 次"
          % (len(o_before), len(o_after), sorted(i["type"] for i in off),
             o_after.count("chunks_processed")))
    w(maps, pristine_maps)

    # ---- ④ ghost_locator：把某篇的定位符改到源里不存在的偏移 ----
    victim = os.path.join(kb, "工作流", FLOW, STAGE, "docB_块1_笔记.md")
    before = open(victim, encoding="utf-8").read()
    w(victim, before.replace("char=%d-%d" % tuple(
        (p10_split(P10_DOCS["docB.md"])[1][1], p10_split(P10_DOCS["docB.md"])[1][2])),
        "char=999999-999999"))
    _, d3 = parsed(["--format", "json"])
    ghosts = [i for i in (d3 or {}).get("inconsistencies", []) if i["type"] == "ghost_locator"]
    check("P10-④ 定位符落不进任何块 → ghost_locator 报出（且点名是哪篇）",
          any("docB_块1_笔记" in g["note"] for g in ghosts),
          json.dumps(ghosts, ensure_ascii=False)[:200])
    check("P10-④b 该篇的块因此退回未抽：done_chunks 从 5 掉到 4（引用是真凭证，不是装饰）",
          d3["summary"]["done_chunks"] == 4, json.dumps(d3["summary"], ensure_ascii=False))
    w(victim, before)

    # ---- ⑤ unmapped_source：sources 指向没进地图的文档 ----
    v2 = os.path.join(kb, "工作流", FLOW, STAGE, "docA_块1_笔记.md")
    b2 = open(v2, encoding="utf-8").read()
    w(v2, b2.replace("sources:\n  - docA.md", "sources:\n  - 没进地图的文档.md"))
    _, d4 = parsed(["--format", "json"])
    check("P10-⑤ sources 指的文档不在 doc_maps → unmapped_source 报出（doc_map 过期可查）",
          any(i["type"] == "unmapped_source" and "没进地图的文档.md" in i["doc"]
              for i in (d4 or {}).get("inconsistencies", [])),
          json.dumps([i for i in (d4 or {}).get("inconsistencies", [])
                      if i["type"] == "unmapped_source"], ensure_ascii=False)[:200])
    w(v2, b2)

    # ---- ⑥ 已删（B 裁决）：原 claimed_but_empty 的夹具并入 ③ 当"作废字段"的负控，编号不复用 ----

    # ---- ⑦ 确定性：两次 --format json 逐字节一致 ----
    _, o1 = run_p(["--format", "json"], 0, "P10 确定性第 1 次")
    _, o2 = run_p(["--format", "json"], 0, "P10 确定性第 2 次")
    check("P10-⑦ 同一输入两次 --format json 逐字节一致（sort_keys + 全列表排序）",
          o1 == o2 and len(o1) > 200, "长度 %d/%d" % (len(o1), len(o2)))

    # ---- ⑧ 只读：跑完前后整库 .md 与 doc_maps.jsonl 的 mtime+内容都不变 ----
    fp1 = p10_fingerprint(kb)
    run_p(["--format", "json"], 0, "P10 只读复检跑一次")
    run_p(["--emit-todo"], 0, "P10 只读复检 emit-todo")
    run_p([], 0, "P10 只读复检 markdown")
    fp2 = p10_fingerprint(kb)
    diff = sorted(k for k in set(fp1) | set(fp2) if fp1.get(k) != fp2.get(k))
    check("P10-⑧ progress 只读：跑完三种输出后，整库 .md 与 doc_maps.jsonl 的"
          " mtime+内容**一项都没变**", not diff, "变了 %d 个：%s" % (len(diff), diff[:3]))

    # ---- ⑨ 输入守卫：doc_maps 不在 → rc=1 且不打印通过 ----
    os.rename(maps, maps + ".bak")
    rc, out = run_p(["--format", "json"], 1, "P10 doc_maps 缺失")
    check("P10-⑨a doc_maps 不存在 → rc=1，明写怎么重建，不打印任何进度",
          rc == 1 and "doc_maps 不存在" in out and "doc_map.py" in out, out[:200])
    os.remove(maps + ".bak")
    w(maps, "")
    rc, out = run_p(["--format", "json"], 1, "P10 doc_maps 0 行")
    check("P10-⑨b doc_maps 0 行 → rc=1（拒绝在什么都没读的基础上打印进度）",
          rc == 1 and "0 行" in out, out[:200])
    w(maps, "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                      for r in p10_maps()) + "\n")
    rc, out = run_p(["--notes-dir", os.path.join(WORK, "p10_progress", "nope"),
                     "--format", "json"], 1, "P10 笔记目录不存在")
    check("P10-⑨c 笔记目录不存在 → rc=1", rc == 1 and "笔记目录不存在" in out, out[:160])
    rc2, out2 = run([PROG, "--notes-dir", nd, "--format", "json"], 0, "P10 守卫后恢复正常")
    check("P10-⑨d 三种输入错误都不影响恢复正常后的读数",
          rc2 == 0 and json.loads(out2)["summary"]["done_chunks"] == 5, out2[:120])


# ---------------------------------------------------------------- P11
# progress.py 的 --gate（默认关的显式门禁）：只判**本视图内**的结构不一致非空与否，共 14 条断言。
# 夹具复用 P10 那套（同一份 p10_build / P10_DOCS / p10_maps），但**另起一个临时库 tag**，
# 不与 P10 共享任何状态——两套探针各自改各自的笔记，互不污染。
# 断言分开两路：gate 相关的跑用 gate_run()（要**分开的 stdout / stderr**，run() 是合并的），
# 其余沿用 run_p() 以便在汇总里留下 RC 行。

def p11_gate():
    """P11：--gate 的 14 条断言（默认关 / 判红 / stdout 不变 / 叠加 / 范围内 / 守卫优先 / 只读）。"""
    PROG = os.path.join(SCRIPTS, "progress.py")
    kb, maps, cfg = p10_build("p11_gate")
    nd = os.path.join(kb, "工作流")

    def run_p(extra=None, want_rc=0, label="P11 progress"):
        return run([PROG, "--notes-dir", nd] + (extra or []), want_rc, label)

    def gate_run(extra, label):
        """分开返回 (rc, stdout, stderr)——证明 stdout 一字不变、话全在 stderr。"""
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable, PROG, "--notes-dir", nd] + extra,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env)
        ROWS.append((label, "RAN", p.returncode, ""))
        return p.returncode, (p.stdout or ""), (p.stderr or "")

    # ---- ① 干净夹具：默认关、开了也绿 ----
    rc_a, out_a, err_a = gate_run(["--format", "json"], "P11 干净·不加 gate")
    rc_b, out_b, err_b = gate_run(["--format", "json", "--gate"], "P11 干净·加 gate")
    check("P11-①a 不一致 0 条时，不加 --gate 恒 rc=0（**默认关**，行为一字未变）",
          rc_a == 0 and json.loads(out_a)["summary"]["inconsistencies"] == 0,
          "rc=%d｜%s" % (rc_a, out_a[:120]))
    check("P11-①b --gate 且不一致 0 条 → rc=0，且 stderr 明写 GATE OK（判绿也要出声）",
          rc_b == 0 and "GATE OK" in err_b, "rc=%d｜stderr=%s" % (rc_b, err_b[:160]))

    # ---- ②③ ghost_locator：默认关必须不拦，开了才判红 ----
    victim = os.path.join(kb, "工作流", FLOW, STAGE, "docB_块1_笔记.md")
    before = open(victim, encoding="utf-8").read()
    ghost = before.replace("char=%d-%d" % tuple(p10_split(P10_DOCS["docB.md"])[1][1:3]),
                           "char=999999-999999")
    w(victim, ghost)
    rc_c, out_c, err_c = gate_run(["--format", "json"], "P11 脏·不加 gate")
    rc_d, out_d, err_d = gate_run(["--format", "json", "--gate"], "P11 脏·加 gate")
    kinds_d = sorted(set(i["type"] for i in json.loads(out_d)["inconsistencies"]))
    check("P11-② 有一条 ghost_locator 时**不加 --gate 仍 rc=0**（门禁不显式开就绝不拦）",
          rc_c == 0 and json.loads(out_c)["summary"]["inconsistencies"] == 1,
          "rc=%d｜条数=%s" % (rc_c, json.loads(out_c)["summary"]["inconsistencies"]))
    check("P11-③ 同一条不一致 + --gate → rc=1，stderr 明写条数、类型与「不是百分比」",
          rc_d == 1 and "GATE FAIL" in err_d and "1 条" in err_d
          and "ghost_locator" in err_d and "不是百分比" in err_d,
          "rc=%d｜stderr=%s" % (rc_d, err_d[:200]))

    # ---- ⑥ stdout 逐字节：gate 只作用于退出码 ----
    check("P11-⑥a 脏夹具下 --gate 与不加 --gate 的 **stdout 逐字节相同**（json）",
          out_c == out_d and len(out_c) > 200, "长度 %d/%d" % (len(out_c), len(out_d)))
    _, m_plain, _ = gate_run(["--format", "markdown"], "P11 脏·markdown 不加 gate")
    _, m_gate, _ = gate_run(["--format", "markdown", "--gate"], "P11 脏·markdown 加 gate")
    check("P11-⑥b markdown 同样逐字节相同，且 **stdout 里绝不出现 GATE 字样**"
          "（人读报告不被门禁文案污染）",
          m_plain == m_gate and "GATE" not in m_plain and "GATE" not in out_c,
          "相同=%s｜stdout 含 GATE=%s" % (m_plain == m_gate, "GATE" in m_plain))

    # ---- ⑦ 与 --emit-todo 叠加：一次拿起点 + 判绿 ----
    _, todo_out, _ = gate_run(["--emit-todo"], "P11 脏·emit-todo 单独")
    rc_e, todo_gate_out, _ = gate_run(["--emit-todo", "--gate"], "P11 脏·emit-todo + gate")
    check("P11-⑦ --emit-todo 与 --gate 叠加：stdout 还是**那一行起点**（与单独用时一致），"
          "rc 由 gate 决定（脏 → 1）",
          todo_gate_out == todo_out and todo_out.startswith("docB.md\t")
          and todo_out.count("\n") == 1 and rc_e == 1,
          "rc=%d｜stdout=%r" % (rc_e, todo_out[:90]))

    # ---- ⑧ --path-prefix 的代价：范围外的真实不一致不触发 gate ----
    rc_out_view, _, err_out = gate_run(["--gate", "--path-prefix", "docA"],
                                       "P11 脏·gate 范围外")
    rc_in_view, _, err_in = gate_run(["--gate", "--path-prefix", "docB"],
                                     "P11 脏·gate 范围内")
    check("P11-⑧ gate 判**本视图**：ghost 在 docB，`--path-prefix docA` → rc=0（范围外不触发，"
          "stderr 说 0 条）、`--path-prefix docB` → rc=1（范围内触发）——"
          "这是主动缩小视图的代价，文档已明写",
          rc_out_view == 0 and rc_in_view == 1 and "范围内" in err_out and "docB" in err_in,
          "范围外 rc=%d %s｜范围内 rc=%d %s" % (rc_out_view, err_out[:70],
                                          rc_in_view, err_in[:70]))
    w(victim, before)

    # ---- ④⑤ 第二类也判 + 还原复绿（判"有无"不是阈值）----
    v2 = os.path.join(kb, "工作流", FLOW, STAGE, "docA_块1_笔记.md")
    b2 = open(v2, encoding="utf-8").read()
    w(v2, b2.replace("sources:\n  - docA.md", "sources:\n  - 没进地图的文档.md"))
    rc_f, out_f, err_f = gate_run(["--format", "json", "--gate"], "P11 脏·unmapped + gate")
    check("P11-④ 第二类不一致（unmapped_source）同样判红：rc=1 且 stderr 点名类型",
          rc_f == 1 and "unmapped_source" in err_f
          and "unmapped_source" in [i["type"] for i in json.loads(out_f)["inconsistencies"]],
          "rc=%d｜kinds=%s｜stderr=%s" % (rc_f,
                                    sorted(set(i["type"] for i in
                                               json.loads(out_f)["inconsistencies"])), err_f[:140]))
    w(v2, b2)
    rc_g, out_g, _ = gate_run(["--format", "json", "--gate"], "P11 还原·gate")
    check("P11-⑤ 两处都还原后 gate 回到 rc=0（判的是**有没有**，不是数量阈值，改回来必复绿）",
          rc_g == 0 and json.loads(out_g)["summary"]["inconsistencies"] == 0,
          "rc=%d｜%s" % (rc_g, out_g[:100]))

    # ---- ⑨ 输入守卫优先于 gate：报错文案不许被 GATE 抢话 ----
    os.rename(maps, maps + ".bak")
    rc_h, out_h, err_h = gate_run(["--format", "json", "--gate"], "P11 doc_maps 缺失 + gate")
    check("P11-⑨ doc_maps 缺失 + --gate → 仍是**输入守卫**的 rc=1 与「doc_maps 不存在」，"
          "不打印 GATE 文案（两者语义不混）",
          rc_h == 1 and "doc_maps 不存在" in (out_h + err_h) and "GATE" not in (out_h + err_h),
          "rc=%d｜out=%s" % (rc_h, (out_h + err_h)[:150]))
    os.remove(maps + ".bak")
    w(maps, "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True)
                      for r in p10_maps()) + "\n")

    # ---- ⑩ 只读：跑完十种 gate 组合后整库不变 ----
    rc_i, _, _ = gate_run(["--format", "markdown", "--path-prefix", "docC"],
                          "P11 守卫后恢复正常（markdown）")
    rc_j, out_j, _ = gate_run(["--format", "json"], "P11 守卫后恢复正常（json）")
    check("P11-⑩a 输入错误恢复后 gate 读数正常（rc=0、done_chunks 仍 5）",
          rc_i == 0 and rc_j == 0 and json.loads(out_j)["summary"]["done_chunks"] == 5,
          "rc=%d/%d｜%s" % (rc_i, rc_j, out_j[:100]))
    check("P11-⑩b --gate 的自我约束写进 --help：明写「结构性错误 / 不是百分比」，"
          "所以百分比、warn、audit 指标都不可能进了 gate 还被误读",
          "不是百分比" in run([PROG, "--help"], 0, "P11 --help")[1], "")

    fp1 = p10_fingerprint(kb)
    for extra in (["--gate"], ["--format", "json", "--gate"], ["--emit-todo", "--gate"],
                  ["--gate", "--path-prefix", "docB"]):
        run_p(extra, 0, "P11 只读复检 %s" % "+".join(extra))
    fp2 = p10_fingerprint(kb)
    diff = sorted(k for k in set(fp1) | set(fp2) if fp1.get(k) != fp2.get(k))
    check("P11-⑪ 跑完四种 gate 组合后整库 .md 与 doc_maps.jsonl 的 mtime+内容一项都没变"
          "（**门禁也不许偷偷写**）", not diff, "变了 %d 个：%s" % (len(diff), diff[:3]))


# ---------------------------------------------------------------- P12
# P12 结构适配（可移植性）：六组按批次递增——
#   enc（A8 编码保护）｜dir（A2+A3 目录参数化）｜src（A4 源类型）｜lang（A1 语言）
#   ｜fb（同源 except 兜底不得产出可用常量值）
#   ｜sb（拆篇候选边界：①media_table 按内容判 ②围栏整体不可切（**闭栏反引号数 ≥ 开栏数**，含四反引号嵌套的回归面）③超限先粘连、不硬切）。
# 每组都配一条**负控**：证明断言不是空的（把保护剥掉必须变红）。

CJK_RE = re.compile(r"[一-鿿]")
ENC_BAD = ("Traceback", "UnicodeEncodeError", "lost sys.stderr", "I/O operation on closed file")
RECONF_OUT = re.compile(r'^sys\.stdout\.reconfigure\(encoding="utf-8", errors="replace"\)', re.M)
RECONF_ERR = re.compile(r'^sys\.stderr\.reconfigure\(encoding="utf-8", errors="replace"\)', re.M)


def enc_run(argv, enc, cwd=None):
    """带指定 PYTHONIOENCODING 跑一次脚本，分开返回 (rc, stdout, stderr)。"""
    env = dict(os.environ, PYTHONIOENCODING=enc)
    p = subprocess.run([sys.executable] + argv, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, cwd=cwd)
    tag = " ".join(os.path.basename(a) for a in argv if not a.startswith("-"))[:40] or "help"
    ROWS.append(("P12 enc %s %s" % (enc, tag), "RAN", p.returncode, ""))
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def p12_enc():
    """A8：scripts/*.py + probe.py 的 reconfigure 防漏（**文件数动态取**）+ gbk 下不炸 + 输出不被编码层改动。"""
    scripts = sorted(os.path.join(SCRIPTS, f) for f in os.listdir(SCRIPTS) if f.endswith(".py"))
    here = os.path.join(HERE, "probe.py")
    guarded = [p for p in scripts + [here]
               if RECONF_OUT.search(open(p, encoding="utf-8").read())
               and RECONF_ERR.search(open(p, encoding="utf-8").read())]

    # ---- ① 防漏：stdout 与 stderr 两条 reconfigure 都在，缺一即红 ----
    check("P12-enc① 防漏：scripts/*.py（%d 个）+ probe.py 全部带 stdout **和** stderr 两条 "
          "reconfigure；缺一个就红（新脚本忘加保护会被这条抓到）" % len(scripts),
          len(guarded) == len(scripts) + 1,
          "齐 %d/%d｜缺：%s" % (len(guarded), len(scripts) + 1,
                             [os.path.basename(p) for p in scripts + [here] if p not in guarded]))

    # ---- ② 逐个 --help 在 gbk 下跑：脚本数**动态取**（写死会把「测了几个」变成假话）----
    offenders = []
    for p in scripts:
        rc, out, err = enc_run([p, "--help"], "gbk")
        bad = [b for b in ENC_BAD if b in out + err]
        if rc != 0 or bad or not CJK_RE.search(out):
            offenders.append("%s(rc=%d,坏字样=%s,中文=%s)"
                             % (os.path.basename(p), rc, bad or "无", bool(CJK_RE.search(out))))
    check("P12-enc② %d 个脚本 `--help` 在 PYTHONIOENCODING=gbk 下逐个跑：rc=0、"
          "输出无 Traceback/UnicodeEncodeError/lost sys.stderr，且**中文确实打出来了**"
          "（不是「没输出所以没报错」）" % len(scripts),
          not offenders,
          "; ".join(offenders) or "%d/%d 通过" % (len(scripts) - len(offenders), len(scripts)))

    # ---- ③ gbk 与 utf-8 的 --help 输出逐字节相同（编码层不得改动内容）----
    diffs = []
    for p in scripts:
        _, o_g, _ = enc_run([p, "--help"], "gbk")
        _, o_u, _ = enc_run([p, "--help"], "utf-8")
        if o_g != o_u:
            diffs.append(os.path.basename(p))
    check("P12-enc③ 同一脚本 gbk 与 utf-8 两种控制台下 `--help` 输出**逐字节相同**"
          "（保护只改编码，不改内容；errors=replace 也不许偷偷替换出差异）",
          not diffs, "不同的文件：%s" % (diffs or "无"))

    # ---- ④ evaluate.report 的结论行（✅ / ❌）——原崩溃点 ----
    kb, maps, cfg = p10_build("p12_enc")
    out_json = os.path.join(WORK, "p12_enc", "rep.json")
    snippet = ("import sys; sys.path.insert(0, %r); import evaluate;"
               "evaluate.report('t', {'gate': True, 'gate_rule': 'x'}, %r)")
    rc_t, o_t, e_t = enc_run(["-c", snippet % (SCRIPTS, out_json)], "gbk")
    snippet_f = ("import sys; sys.path.insert(0, %r); import evaluate;"
                 "evaluate.report('t', {'gate': False, 'gate_rule': 'x'}, %r)")
    rc_f, o_f, e_f = enc_run(["-c", snippet_f % (SCRIPTS, out_json)], "gbk")
    check("P12-enc④ `evaluate.report()` 的 `[gate] 通过 ✅ / 未通过 ❌` 两条分支在 gbk 下都打得出来"
          "（rc=0、✅❌ 均在 stdout、无异常）——这一行正是原先 UnicodeEncodeError 的位置",
          rc_t == rc_f == 0 and "✅" in o_t and "❌" in o_f
          and not [b for b in ENC_BAD if b in o_t + e_t + o_f + e_f],
          "gate=True rc=%d 含✅=%s｜gate=False rc=%d 含❌=%s"
          % (rc_t, "✅" in o_t, rc_f, "❌" in o_f))

    # ---- ⑤ 跨 import 链（progress→search_index）不得关掉共享缓冲 ----
    nd = os.path.join(kb, "工作流")
    rc_a, o_a, e_a = enc_run([os.path.join(SCRIPTS, "progress.py"), "--notes-dir", nd,
                              "--format", "json"], "gbk")
    rc_b, o_b, e_b = enc_run([os.path.join(SCRIPTS, "progress.py"), "--notes-dir", nd,
                              "--format", "json"], "utf-8")
    check("P12-enc⑤ 被 import 的模块也带保护（progress→search_index 两层 reconfigure 落在同一对象上）："
          "gbk 下 rc=0、stdout 与 utf-8 逐字节相同、**且不出现 lost sys.stderr / closed file**"
          "（无条件 TextIOWrapper 会在这里把缓冲区关掉，故全仓统一用 reconfigure）",
          rc_a == rc_b == 0 and o_a == o_b and len(o_a) > 200
          and not [b for b in ENC_BAD if b in o_a + e_a],
          "rc=%d/%d｜长度 %d/%d｜相同=%s" % (rc_a, rc_b, len(o_a), len(o_b), o_a == o_b))

    # ---- ⑥ 负控：把 guard 剥掉的副本必须炸----
    noguard = os.path.join(WORK, "p12_enc", "noguard")
    os.makedirs(noguard, exist_ok=True)
    strip = re.compile(r'^sys\.(stdout|stderr)\.reconfigure\(.*\)\n?', re.M)
    for f in os.listdir(SCRIPTS):
        if f.endswith(".py"):
            src = open(os.path.join(SCRIPTS, f), encoding="utf-8").read()
            open(os.path.join(noguard, f), "w", encoding="utf-8", newline="\n").write(
                strip.sub("", src))
    rc_n, o_n, e_n = enc_run(["-c", snippet % (noguard, out_json)], "gbk", cwd=noguard)
    check("P12-enc⑥ **负控**：同一份 evaluate 副本把两条 reconfigure 删掉后，gbk 下必红"
          "（rc≠0 且报 UnicodeEncodeError）——证明 enc①–⑤ 不是空断言",
          rc_n != 0 and "UnicodeEncodeError" in o_n + e_n,
          "rc=%d｜报错=%s" % (rc_n, (o_n + e_n).strip().splitlines()[-1:] or ["无"]))

    # ---- ⑦ 只读：P12 的 enc 组没碰临时库以外的东西 ----
    fp1 = p10_fingerprint(kb)
    enc_run([os.path.join(SCRIPTS, "progress.py"), "--notes-dir", nd], "gbk")
    check("P12-enc⑦ enc 组跑完后临时库的 .md/.jsonl 指纹不变（测试自身不污染库）",
          p10_fingerprint(kb) == fp1, "")


# ---------------------------------------------------------------- P12 · dir 组
# A2+A3：笔记目录名/KB 根的参数化。**自建夹具、自带负控**，不复用 P10/P11 的库
# （教训已记台账：手写夹具会被下一次 rmtree(_work) 清掉，所以建库与测量必须在同一套里）。

DIR_RULES = {"new_note": "L0", "fix_format": "L0", "add_tags": "L0", "move_in_inbox": "L1",
             "edit_source": "L2", "delete": "L2", "batch_20plus": "L2", "rename_topic": "L2",
             "write_rules": "L2"}
DIR_STAGES = {"1_找选题": ["笔记甲", "笔记乙"], "2_写脚本": ["笔记丙"]}


def p12_dir_note(kb, notes_name, stage, stem, a, b):
    w(os.path.join(kb, notes_name, "内容创作", stage, stem + ".md"),
      "---\ntitle: %s\nflow: 内容创作\nstage: %s\nsubstage: 子技巧\n"
      "domains: [内容创作]\nforms: [方法论]\ntools: []\ntypes: [方法]\nprojects: []\n"
      "topics: [换名夹具]\nq_hooks:\n  - 这个问题怎么解\n  - 还有别的说法吗\n  - 适用边界在哪\n"
      "sources:\n  - doc.md\nsource_locator:\n  - §段一#char=%d-%d\n"
      "confidence: high\nstatus: confirmed\ncreated: 2026-10-06\n---\n\n"
      "# %s\n\n> 一句话。\n\n## 资料原话（evidence.quote）\n\n> 第一个结论。\n"
      "> —— `§段一#char=%d-%d`\n\n## 归纳结论\n\n- 略；\n\n## 可执行清单\n\n1. 略；\n\n"
      "## 关联\n\n来源：[[来源·换名夹具]]\n\n## AI 推断（inference）\n\n- 作者未提、我的推论：略。\n"
      % (stem, stage, a, b, stem, a, b))


DIR_DOC = ("# 甲篇\n\n## 段一\n\n第一个结论，含 12、34、56 三个数与一条命令 `pip install kb-demo`，"
           "再补一句把长度撑过 doc_map 的 200 字节正文门槛：这条结论的可执行部分是先切题再切段。\n\n"
           "## 段二\n\n第二个结论，讲可引名单与正文引用的对应关系，同样补齐到足够长以避免被 is_body "
           "当成短文件跳过（真库踩过一次，教训见台账「测试台方法论」）。\n")


def p12_dir_build(tag, notes_name, with_doc_maps=False):
    """造一个笔记目录叫 `notes_name` 的可用库：目录骨架 + 3 篇原子笔记 + 1 篇来源笔记 + config。

    定位符的 char 区间由 `p10_split(DIR_DOC)` 从真文本算出——硬编码偏移会在源文本改动后
    静默落错块，把夹具变成"全绿但没在测东西"。"""
    root = os.path.join(WORK, tag)
    kb = os.path.join(root, "kb")
    src = os.path.join(root, "src")
    os.makedirs(src, exist_ok=True)
    w(os.path.join(src, "doc.md"), DIR_DOC)
    a, b = p10_split(DIR_DOC)[1][1], p10_split(DIR_DOC)[1][2]
    dirs = ["_meta", "00_导航", "99_收件箱", "素材库/_来源地图", "概念索引"]
    dirs += ["%s/内容创作" % notes_name] + ["%s/内容创作/%s" % (notes_name, s) for s in DIR_STAGES]
    for d in dirs:
        os.makedirs(os.path.join(kb, *d.split("/")), exist_ok=True)
    w(os.path.join(kb, "README.md"), "# 换名库\n")
    w(os.path.join(kb, "AGENTS.md"), "# 规则\n\n改动分三档：L0 直接做、L1 先确认、L2 禁止。\n")
    w(os.path.join(kb, "_meta", "问题资产库.md"), "# 问题资产库\n")
    w(os.path.join(kb, "素材库", "_来源地图", "来源·换名夹具.md"),
      "---\ntitle: 来源·换名夹具\nsource_doc: doc.md\nderived_notes:\n  - [[笔记甲]]\n"
      "  - [[笔记乙]]\n  - [[笔记丙]]\ncreated: 2026-10-06\n---\n\n# 来源·换名夹具\n\n"
      "- 块数与字数记在这里，不写进原子笔记正文\n")
    for stage, titles in DIR_STAGES.items():
        for t in titles:
            p12_dir_note(kb, notes_name, stage, t, a, b)
    cfg = {"notes_dir": notes_name, "source_root": src.replace("\\", "/"), "rules": DIR_RULES,
           "sample_notes": [],
           "directories": [{"path": d, "create": True, "reason": "夹具"} for d in dirs]}
    w(os.path.join(root, "config.json"), json.dumps(cfg, ensure_ascii=False))
    if with_doc_maps:
        run([os.path.join(SCRIPTS, "doc_map.py"), "--source-root", src,
             "--out", os.path.join(kb, "_meta", "doc_maps.jsonl")], 0, "P12 dir doc_map")
    return kb, src, os.path.join(root, "config.json")


def p12_dir_pyfile():
    """verify 的「现状副本」：把 A2+A3 四处改动逐一反向着陆，用来证明新断言不是空的。"""
    cur = open(os.path.join(SCRIPTS, "verify.py"), encoding="utf-8").read()
    pairs = [("note_dir_prefixes = scan_dirs", "note_dir_prefixes = SCAN_DIRS"),
             ("startswith(stem_dirs)", "startswith(STEM_SOURCE_DIRS)"),
             ("expect_dirs = list(required_dirs(notes_dir))", "expect_dirs = list(REQUIRED_DIRS)"),
             ("check_index_consistency(kb, notes_dir)", "check_index_consistency(kb)")]
    for a, b in pairs:
        if a not in cur:
            raise SystemExit("[P12 dir] verify.py 的锚点没找到，「现状副本」造不出来——"
                             "说明参数化实现被改了而负控没跟着改：%s" % a)
        cur = cur.replace(a, b)
    d = os.path.join(WORK, "p12_dir", "oldcode")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "verify_old.py")
    w(p, cur)
    return p


def dir_run(argv, want_rc=None, label="P12 dir", cwd=None):
    """带 PYTHONPATH=SCRIPTS 跑（「现状副本」放在 _work 里，不指回 scripts 就 import 不到同目录模块）。"""
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=SCRIPTS)
    p = subprocess.run([sys.executable] + argv, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, cwd=cwd)
    ROWS.append((label, "RAN", p.returncode, ""))
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def c_line(out, cid):
    return next((l.strip() for l in out.splitlines() if "] " + cid + " " in l), "(无该行)")


def p12_dir():
    """P12 dir 组：A2+A3 的九条断言（含两条负控）。"""
    V = os.path.join(SCRIPTS, "verify.py")
    BF = os.path.join(SCRIPTS, "build_flows.py")
    kb, src, cfgp = p12_dir_build("p12_dir", "notes", with_doc_maps=True)
    run([os.path.join(SCRIPTS, "build_topics.py"), "--kb", kb, "--notes", "notes"],
        0, "P12 dir build_topics")
    run([os.path.join(SCRIPTS, "search_index.py"), "build", "--kb", kb,
         "--notes", "notes", "--rebuild"], 0, "P12 dir index build")
    old_v = p12_dir_pyfile()

    # ---- ① config.notes_dir 生效 + 负控（现状副本看不见换名库）----
    rc1, o1, _ = dir_run([V, "--kb", kb, "--config", cfgp], label="P12 dir ① config.notes_dir")
    rco, oo, _ = dir_run([old_v, "--kb", kb, "--config", cfgp], label="P12 dir ① 现状副本")
    check("P12-dir① config.notes_dir=notes 时 verify 检到 **3 篇**（C4）且整库 rc=0；"
          "**负控**：同一库用「现状副本」跑，C4 只检到 0 篇、C12 报「磁盘笔记目录缺失：工作流」"
          "（把参数没接上伪装成忘了 rebuild 的那个 bug，就在这里被抓住）",
          rc1 == 0 and "3 篇合法" in c_line(o1, "C4") and "fail=0" in o1
          and "0 篇" in c_line(oo, "C4") and "缺失" in c_line(oo, "C12"),
          "新 rc=%d C4=%s｜旧 rc=%d C4=%s C12=%s"
          % (rc1, c_line(o1, "C4")[:44], rco, c_line(oo, "C4")[:40], c_line(oo, "C12")[:52]))

    # ---- ② CLI --notes（config 不带该键）----
    cfg_nokey = json.loads(open(cfgp, encoding="utf-8").read())
    cfg_nokey.pop("notes_dir")
    p_nokey = os.path.join(WORK, "p12_dir", "config_nokey.json")
    w(p_nokey, json.dumps(cfg_nokey, ensure_ascii=False))
    rc2, o2, _ = dir_run([V, "--kb", kb, "--config", p_nokey, "--notes", "notes"],
                         label="P12 dir ② CLI --notes")
    check("P12-dir② 只靠 CLI `--notes notes`（config 里删掉 notes_dir）：同样检到 3 篇、rc=0",
          rc2 == 0 and "3 篇合法" in c_line(o2, "C4"),
          "rc=%d｜%s" % (rc2, c_line(o2, "C4")[:60]))

    # ---- ③ 优先级：CLI 覆盖 config ----
    rc3, o3, _ = dir_run([V, "--kb", kb, "--config", cfgp, "--notes", "工作流"],
                         label="P12 dir ③ CLI 覆盖 config")
    check("P12-dir③ 优先级 CLI > config：config 写 notes、CLI 传 工作流 → 检到 0 篇（CLI 赢）",
          "0 篇" in c_line(o3, "C4"), c_line(o3, "C4")[:64])

    # ---- ④ 兜底与默认名：新代码 vs 现状副本，逐字节相同 ----
    kb_std, src_std, cfg_std = p12_dir_build("p12_dir_std", "工作流", with_doc_maps=True)
    run([os.path.join(SCRIPTS, "build_topics.py"), "--kb", kb_std, "--notes", "工作流"],
        0, "P12 dir 标准库 build_topics")
    run([os.path.join(SCRIPTS, "search_index.py"), "build", "--kb", kb_std,
         "--notes", "工作流", "--rebuild"], 0, "P12 dir 标准库 index build")
    old_std = p12_dir_pyfile()
    rc4a, o4a, _ = dir_run([V, "--kb", kb_std, "--config", cfg_std], label="P12 dir ④ 新代码")
    rc4b, o4b, _ = dir_run([old_std, "--kb", kb_std, "--config", cfg_std], label="P12 dir ④ 现状副本")
    check("P12-dir④ 兼容红线：标准布局 + 不带 `--notes` 时，新代码与「现状副本」的 **stdout 逐字节相同**"
          "（参数化只加能力，不改一次输出）", o4a == o4b and rc4a == rc4b == 0 and len(o4a) > 400,
          "长度 %d/%d｜相同=%s" % (len(o4a.encode()), len(o4b.encode()), o4a == o4b))

    # ---- ⑤ --kb 覆盖父目录推导（嵌套布局：notes 目录天生就在 kb/deep/nest/ 下）----
    kb_deep, _, _ = p12_dir_build("p12_dir_deep", "deep/nest/工作流", with_doc_maps=True)
    deep_notes = os.path.join(kb_deep, "deep", "nest", "工作流")
    rc5a, o5a, e5a = dir_run([os.path.join(SCRIPTS, "progress.py"),
                              "--notes-dir", deep_notes, "--format", "json"],
                             label="P12 dir ⑤ 不给 --kb")
    rc5b, o5b, e5b = dir_run([os.path.join(SCRIPTS, "progress.py"),
                              "--notes-dir", deep_notes, "--kb", kb_deep,
                              "--format", "json"], label="P12 dir ⑤ 给 --kb")
    check("P12-dir⑤ `--kb`：嵌套库不给 → rc=1 且文案是「doc_maps 不存在」（默认＝父目录，没被改坏）；"
          "给了 --kb → rc=0 且读到 3 篇",
          rc5a == 1 and "doc_maps 不存在" in e5a and rc5b == 0
          and json.loads(o5b)["summary"]["notes_total"] == 3,
          "不给 rc=%d｜给 rc=%d｜%s" % (rc5a, rc5b, (e5a.strip().splitlines() or [""])[0][:56]))

    # ---- ⑥⑦ build_flows：换名成功 + 目录不存在的输入守卫 ----
    kb_bf, _, _ = p12_dir_build("p12_dir_bf", "notes")
    rc6, o6, _ = dir_run([BF, "--kb", kb_bf, "--notes", "notes"], label="P12 dir ⑥ build_flows 成功")
    made = sorted(os.path.relpath(os.path.join(dp, f), kb_bf).replace("\\", "/")
                  for dp, _, fs in os.walk(kb_bf) for f in fs
                  if f in ("_流程.md", "_总览.md"))
    check("P12-dir⑥ `build_flows --notes notes` 在换名库里生成聚合页且 rc=0（落点全在 notes/ 下）",
          rc6 == 0 and made == ["notes/内容创作/1_找选题/_总览.md", "notes/内容创作/2_写脚本/_总览.md",
                                "notes/内容创作/_流程.md"], "%s｜%s" % (rc6, made))
    # 基线取在 ⑥ 之后：⑥ 合法写入了聚合页，拿 ⑥ 之前当基线会把"正常生成"误判成污染
    fp1 = p10_fingerprint(kb_bf)
    rc7, o7, e7 = dir_run([BF, "--kb", kb_bf, "--notes", "不存在"], label="P12 dir ⑦ build_flows 守卫")
    check("P12-dir⑦ **输入守卫（本批改判）**：`build_flows` 找不到目录时 → **rc=1** + 文案走 stderr"
          "（与 progress 的 doc_maps 缺失同性质：显式动作失败要响），且**一个文件都没写**",
          rc7 == 1 and "未找到 不存在 目录" in e7 and "未找到" not in o7
          and p10_fingerprint(kb_bf) == fp1,
          "rc=%d｜stderr=%s" % (rc7, e7.strip()[:96]))

    # ---- ⑧ 单一真源防漏（⑥ 的落地验证）----
    bad = []
    for f in sorted(os.listdir(SCRIPTS)):
        if not f.endswith(".py"):
            continue
        lines = open(os.path.join(SCRIPTS, f), encoding="utf-8").read().splitlines()
        for n, ln in enumerate(lines):
            if re.match(r'^DEFAULT_NOTES_DIR\s*=\s*"工作流"\s*$', ln):
                prev = lines[n - 1].strip() if n else ""
                if not prev.startswith(("try:", "except")):
                    bad.append("%s:%d" % (f, n + 1))
    check("P12-dir⑧ **单一真源防漏**：无条件写死 `DEFAULT_NOTES_DIR = \"工作流\"` 的只允许 "
          "search_index.py 一处（try/except 兜底分支不算）——check_hooks/backfill_hooks 抄的那两份"
          "已被 import 取代，新脚本再抄一份会在这里红",
          bad == ["search_index.py:%d" % next(i + 1 for i, l in enumerate(
              open(os.path.join(SCRIPTS, "search_index.py"), encoding="utf-8").read().splitlines())
              if l.startswith('DEFAULT_NOTES_DIR = "工作流"'))],
          "命中的无条件字面量：%s" % (bad or "无"))

    # ---- ⑨ ⑨ 定案：STEM_SOURCE_DIRS 第二段不跟 notes_dir 动 ----
    w(os.path.join(kb, "概念索引", "只在三处.md"), "---\ntitle: 只在三处\n---\n\n# 只在三处\n\n正文。\n")
    victim = os.path.join(kb, "notes", "内容创作", "1_找选题", "笔记甲.md")
    txt = open(victim, encoding="utf-8").read()
    w(victim, txt.replace("来源：[[来源·换名夹具]]", "来源：[[来源·换名夹具]]；另指：[[只在三处]]"))
    rc9, o9, _ = dir_run([V, "--kb", kb, "--config", cfgp], label="P12 dir ⑨ C10 范围")
    c10 = c_line(o9, "C10")
    check("P12-dir⑨ **⑨ 的落地验证**：换名库里 `[[来源·换名夹具]]`（住在 `素材库/_来源地图/`）仍判存在，"
          "而指向第三个目录（`概念索引/`）的链**必报失效**——证明 `STEM_SOURCE_DIRS` 的第二段是"
          "写死的约定、不跟 `notes_dir` 动；谁把它也参数化，这条就红",
          rc9 == 0 and "来源·换名夹具" not in c10 and "只在三处" in c10,
          c10[:120])
    w(victim, txt)

    # ---- ⑩ B8 显式白名单：`_` 前缀不再是免检金牌 ----
    kb10, _s10, cfg10 = p12_dir_build("p12_dir_ag", "工作流")
    stage_dir = os.path.join(kb10, "工作流", "内容创作", list(DIR_STAGES)[0])
    stray = os.path.join(stage_dir, "_临时.md")
    aggr = os.path.join(stage_dir, "_总览.md")
    w(stray, "# 手动丢进来的临时页\n\n没有 frontmatter，也不该被当成原子笔记。\n")
    w(aggr, "# 聚合页标题\n\n- [[笔记甲]]\n")
    rc10a, out10a, _e10a = dir_run([os.path.join(SCRIPTS, "verify.py"), "--kb", kb10,
                                       "--config", cfg10], label="P12-dir⑩ 白名单")
    c4a = c_line(out10a, "C4")
    old10 = os.path.join(WORK, "p12_dir_ag", "verify_prefix.py")
    vtxt = open(os.path.join(SCRIPTS, "verify.py"), encoding="utf-8").read()
    back = vtxt.replace("if fn in AGGREGATE_PAGES:      # B8：C4 只豁免白名单里的聚合页",
                        'if fn.startswith("_"):', 1)
    if back == vtxt:
        raise SystemExit("[probe] C4 白名单锚点没找到——B8 的实现被改了而负控没跟着改")
    w(old10, back)
    rc10b, out10b, _e10b = dir_run([old10, "--kb", kb10, "--config", cfg10], label="P12-dir⑩ 负控")
    c4b = c_line(out10b, "C4")
    lits = set()
    for fn in ("verify.py", "search_index.py", "audit.py"):
        bt = open(os.path.join(SCRIPTS, fn), encoding="utf-8").read()
        i = bt.index("AGGREGATE_PAGES = (")
        lits.add(bt[i:bt.index("\n", i)])
    check("P12-dir⑩ **B8 显式白名单**：`_临时.md`（前缀是 `_` 但不在白名单）必须被 C4 点名缺主轴三字段——"
          "前缀不再是免检金牌；同目录 `_总览.md` 仍豁免。两份 `verify` 输出只差这一处判据（负控臂：把 C4 的"
          "`fn in AGGREGATE_PAGES` 改回 `fn.startswith(\"_\")` 的副本**必须不点名**，否则 ⑩ 是空断言）。"
          "顺带钉住 verify/search_index/audit 三份 `AGGREGATE_PAGES` 字面量**逐字相同**（一处改了另一处没跟上就红）",
          rc10a == 1 and "_临时" in c4a and "_总览" not in c4a
          and "_临时" not in c4b and len(lits) == 1,
          "白名单版 C4=%s｜前缀版 C4=%s｜三份常量一致=%s" % (c4a[:78], c4b[:58], len(lits) == 1))
    for pth in (stray, aggr):
        os.remove(pth)


# ---------------------------------------------------------------- P12 · src 组
# A4：源类型扩展。核心语义要钉住的是「**登记 + 只读保护 ≠ 可深抽**」与
# 「清单口径变化只赦免 added，其余判据一律照旧」（发现 32 + 不放松校验）。

SRC_FILES = (("a.md", "# 甲篇\n\n## 段一\n\n{s}\n"),
             ("b.html", "<html><body><p>{s}</p></body></html>\n"),
             ("e.vtt", "WEBVTT\n\n00:00.000 --> 00:04.000\n{s}\n"),
             ("c.docx", "PK\x03\x04" + "fake-docx-bytes-" * 20 + "\n"),
             ("d.pdf", "%PDF-1.4\n{s}\n%%EOF\n"),
             ("m.txt", "{s}\n"))
SRC_FILL = ("这段文字用来把夹具源文件撑过 doc_map.is_body 的 200 字节门槛（测试台方法论第 5 条要求显式检查"
            "长度）；不够长就会被当场断言拦下，而不是静默造出一份空地图骗后面读结果的人。")


def p12_src_old_scan():
    """反向还原 scan_sources 到"A4 之前"，作为负控副本（还原不干净就 SystemExit 响亮停）。"""
    cur = open(os.path.join(SCRIPTS, "scan_sources.py"), encoding="utf-8").read()
    blocks = [
        ('TEXT_READABLE_EXT = {".md", ".txt", ".srt", ".vtt", ".ass", ".html", ".htm", ".rtf"}\n'
         'NEEDS_CONVERT_EXT = {".pdf", ".docx", ".epub", ".odt"}\n'
         'TEXT_BODY_EXT = TEXT_READABLE_EXT | NEEDS_CONVERT_EXT',
         'TEXT_BODY_EXT = {".md", ".pdf", ".txt", ".srt"}'),
        ('            elif ext in TEXT_READABLE_EXT:\n'
         '                # .vtt/.ass/.html/.htm/.rtf：登记并受 C14 保护；doc_map 本批仍只吃 .md，不解析它们\n'
         '                readable_other.append({"path": r, "size": size})\n'
         '            elif ext in NEEDS_CONVERT_EXT:\n'
         '                # .pdf 在上面已走既有 pdf_files / orphan_pdfs 路径，这里只收 docx/epub/odt\n'
         '                needs_convert.append({"path": r, "size": size})\n', ''),
        ('    readable_other, needs_convert = [], []      # 可直读的非 md 正文 / 需转换的二进制正文\n', ''),
        ('            "other_readable": len(readable_other),\n'
         '            "needs_convert_incl_pdf": len(needs_convert) + len(pdf_files),\n', ''),
        ('            # 下面两键是 A4 新增；四个老键一字未动（tag_documents / build_profile 在读它们）\n'
         '            "other_readable": sorted(readable_other, key=lambda x: x["path"]),\n'
         '            "needs_convert": sorted(needs_convert, key=lambda x: x["path"]),\n', ''),
        ('    print(f"[scan] 可直读其他={t[\'other_readable\']} "\n'
         '          f"需转换={t[\'needs_convert_incl_pdf\']}（含 PDF；documents.needs_convert 只列 docx/epub/odt）"\n'
         '          f"｜两档都只登记，深抽仍只吃 .md")\n', ''),
    ]
    for a, b in blocks:
        if a not in cur:
            raise SystemExit("[P12 src] 负控副本还原失败：锚点没命中，说明 scan_sources 被改了"
                             "而负控没跟着改：%s…" % a[:40])
        cur = cur.replace(a, b)
    d = os.path.join(WORK, "p12_src", "oldcode")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "scan_sources_old.py")
    w(p, cur)
    return p


def p12_src():
    """P12 src 组：A4 的六条断言。"""
    SS, V = os.path.join(SCRIPTS, "scan_sources.py"), os.path.join(SCRIPTS, "verify.py")
    root = os.path.join(WORK, "p12_src")
    kb, src = os.path.join(root, "kb"), os.path.join(root, "src")
    for d in ("_meta", "00_导航", "99_收件箱", "工作流/内容创作/1_找选题"):
        os.makedirs(os.path.join(kb, *d.split("/")), exist_ok=True)
    w(os.path.join(kb, "README.md"), "# 换源类型库\n")
    w(os.path.join(kb, "AGENTS.md"), "# 规则\n\nL0 直接做、L1 先确认、L2 禁止。\n")
    w(os.path.join(kb, "_meta", "问题资产库.md"), "# 问题资产库\n")
    os.makedirs(src, exist_ok=True)
    for name, tmpl in SRC_FILES:
        p = os.path.join(src, name)
        w(p, tmpl.format(s=SRC_FILL) if "{" in tmpl else tmpl)
        n = len(open(p, "rb").read())
        assert n >= 200, "夹具源 %s 只有 %dB（测试台方法论第 5 条）" % (name, n)
    cfgp = os.path.join(root, "config.json")
    w(cfgp, json.dumps({"source_root": src.replace("\\", "/"),
                        "rules": {"new_note": "L0", "fix_format": "L0", "add_tags": "L0"},
                        "sample_notes": [],
                        "directories": [{"path": d, "create": True, "reason": "夹具"} for d in
                                        ("_meta", "00_导航", "99_收件箱", "工作流",
                                         "工作流/内容创作", "工作流/内容创作/1_找选题")]}, ensure_ascii=False))
    man, man_old = os.path.join(root, "m_new.json"), os.path.join(root, "m_old.json")
    rc_n, o_n, _ = dir_run([SS, "--source", src, "--out", man], label="P12 src 扫描·新")
    rc_o, o_o, _ = dir_run([p12_src_old_scan(), "--source", src, "--out", man_old], label="P12 src 扫描·负控")
    mn, mo = json.load(open(man, encoding="utf-8")), json.load(open(man_old, encoding="utf-8"))
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    import scan_sources as _ss
    cur_ext = sorted(_ss.TEXT_BODY_EXT)
    def paths(d, k): return sorted(x["path"] for x in d["documents"].get(k, []))
    check("P12-src① 两档登记：documents.other_readable=[b.html,e.vtt]、needs_convert=[c.docx]、"
          "totals 两个计数对；**负控**：还原成 A4 之前的副本里这两档不存在、三篇掉进 media.others",
          rc_n == rc_o == 0 and paths(mn, "other_readable") == ["b.html", "e.vtt"]
          and paths(mn, "needs_convert") == ["c.docx"]
          and mn["totals"]["other_readable"] == 2 and mn["totals"]["needs_convert_incl_pdf"] == 2
          and "other_readable" not in mo["documents"]
          and {"b.html", "e.vtt", "c.docx"} <= {x["path"] for x in mo["media"]["others"]},
          "新=%s/%s｜旧 others=%s" % (paths(mn, "other_readable"), paths(mn, "needs_convert"),
                                   sorted({x["path"] for x in mo["media"]["others"]}))[:150])
    check("P12-src② 契约不破：documents 的 md/pdf/txt/srt 四键与副本**完全相同**、pairing 相同、"
          "media 键集相同（只加键不改老键）；pdf 不进 needs_convert 列表但计入 totals（④ 的口径）",
          all(mn["documents"][k] == mo["documents"][k] for k in ("md", "pdf", "txt", "srt"))
          and mn["pairing"] == mo["pairing"] and sorted(mn["media"]) == sorted(mo["media"])
          and "d.pdf" not in paths(mn, "needs_convert"),
          "四键相同=%s" % all(mn["documents"][k] == mo["documents"][k] for k in ("md", "pdf", "txt", "srt")))
    snap = os.path.join(kb, "_meta", "source_snapshot.json")
    dir_run([V, "--kb", kb, "--config", cfgp, "--source-root", src, "--snapshot-source"],
            label="P12 src 建基线")
    sj = json.load(open(snap, encoding="utf-8"))
    dm = os.path.join(kb, "_meta", "doc_maps.jsonl")
    dir_run([os.path.join(SCRIPTS, "doc_map.py"), "--source-root", src, "--out", dm], label="P12 src doc_map")
    in_dm = sorted(json.loads(l)["path"] for l in open(dm, encoding="utf-8") if l.strip())
    check("P12-src③ 基线跟随清单：snapshot.text_body_ext == sorted(DOC_EXT)（12 类）且 files 覆盖 6 篇；"
          "而 doc_maps.jsonl **只含 .md** —— 把「登记 + 保护 ≠ 可深抽」（发现 32）钉成断言",
          sj["text_body_ext"] == cur_ext and len(sj["files"]) == 6 and in_dm == ["a.md"],
          "类数=%d｜files=%d｜doc_maps=%s" % (len(sj["text_body_ext"]), len(sj["files"]), in_dm))

    def c14():
        _, out, _ = dir_run([V, "--kb", kb, "--config", cfgp, "--source-root", src], label="P12 src verify")
        return next((l.strip() for l in out.splitlines() if "] C14 " in l), "(无 C14 行)")
    OLD4 = sorted({".md", ".pdf", ".txt", ".srt"})
    s2 = dict(sj); s2["text_body_ext"] = OLD4
    s2["files"] = {k: v for k, v in sj["files"].items() if os.path.splitext(k)[1] in OLD4}
    w(snap, json.dumps(s2, ensure_ascii=False, indent=2, sort_keys=True))
    lineA = c14()
    s3 = dict(s2); s3["text_body_ext"] = sorted(sj["text_body_ext"])
    w(snap, json.dumps(s3, ensure_ascii=False, indent=2, sort_keys=True))
    lineB = c14()
    check("P12-src④ 两类文案可区分：旧口径基线 → 文案 A「基线是旧清单口径…重建」且**不出现**"
          "「未纳管」；口径一致但基线缺文件 → 文案 B「源目录新增 N 个文档未纳管」",
          "旧清单口径" in lineA and "未纳管" not in lineA and "不计为新增" in lineA
          and "未纳管" in lineB and "旧清单口径" not in lineB,
          "A=%s｜B=%s" % (lineA[:86], lineB[:86]))
    w(snap, json.dumps(s2, ensure_ascii=False, indent=2, sort_keys=True))
    w(os.path.join(src, "a.md"), open(os.path.join(src, "a.md"), encoding="utf-8").read() + "\n有人改了源文件。\n")
    lineD = c14()
    os.remove(os.path.join(src, "m.txt"))
    lineE = c14()
    check("P12-src⑤ **不放松校验**：旧口径基线下，内容被改 → 仍 FAIL（被修改）；文件被删 → 仍 FAIL"
          "（被删除）。赦免只作用于 added，口径不一致绝不降级 deleted/modified",
          lineD.startswith("[FAIL]") and "被修改" in lineD and "旧清单口径" in lineD
          and lineE.startswith("[FAIL]") and "被删除" in lineE,
          "D=%s｜E=%s" % (lineD[:70], lineE[:70]))
    open(os.path.join(src, "pic.png"), "wb").write(b"\x89PNG\r\n\x1a\n" + b"x" * 400)
    lineF = c14()
    check("P12-src⑥ 旧口径基线下，媒体计数变化**仍按 warn 报出**（与口径 warn 并存，不被吞）",
          "媒体数量变化" in lineF and "images" in lineF and "旧清单口径" in lineF, lineF[:120])


# ---------- P12 lang 组（A1 语言适配：多语言分词 / 停用词 / audit 口径 / schema） ----------
# 夹具自建（测试台方法论第 1 条：建 + 测在同一个函数里，_work 会被整轮 rmtree）；
# 不复用 P10/P11 与其他 P12 组的库，因为 lang 组要的是「同一条查询在五种语言里的 gram 与命中」。
LANG_FILL = ("。把正文顶过 doc_map 的 200 字节门槛，顺便让五种语言共用同一段中文实词，"
             "这样跨语种对照时唯一的变量就只剩脚本段本身。")
# (文件名, 标题, 正文, q_hook, 语种标记, **只出现在正文**的查询)
# 查询一律取正文短语：这样命中只能来自 FTS 通道，不会被 matched_hooks 的
# 「互相包含」规则（①，不看 gram）蒙对，before/after 的差别才是分词口径本身的差别。
LANG_NOTES = [
    ("cn.md", "关键词选品的中文对照笔记",
     "中文选题要把关键词落到具体场景上。" + LANG_FILL, "怎么挑关键词", "cn", "落到具体场景"),
    ("ko.md", "키워드 선정 방법 정리",
     "키워드 선정을 할 때는 검색 의도를 먼저 구분한다. " + LANG_FILL,
     "키워드 선정 방법", "ko", "검색 의도"),
    ("ja.md", "動画企画のキーワード選定",
     "動画企画ではキーワード選定の前に視聴者意图を整理する。" + LANG_FILL,
     "キーワード選定のコツ", "ja", "視聴者"),
    ("fr.md", "Sélection de mots-clés vidéo éditoriale",
     "Pour une vidéo éditoriale, la sélection des mots-clés dépend de l intention. " + LANG_FILL,
     "sélection mots-clés", "fr", "dépend"),
    ("ru.md", "Отбор ключевых слов для видео",
     "Отбор ключевых слов начинается с намерений зрителя. " + LANG_FILL,
     "ключевые слова видео", "ru", "намерений зрителя"),
]

# 「改造前口径」的负控驱动器：把 gram_units / to_index_text 退回 A1 之前，再跑**同一条 CLI**。
# 正则区间用 chr() 拼——把反斜杠+u 写进源码会被编辑链路解码成真字符（本轮实测踩过）。
LANG_OLD_DRIVER = '''# -*- coding: utf-8 -*-
"""P12 lang 负控：A1 之前的分词口径跑真实 CLI 路径（由 probe.py 生成，不是产品代码）。"""
import contextlib
import io
import json
import os
import re
import sys

SCRIPTS = sys.argv[2]
sys.path.insert(0, SCRIPTS)
import search_index as si

kb = sys.argv[1]
queries = json.loads(sys.argv[3])
_HAN = "[" + chr(0x4e00) + "-" + chr(0x9fff) + "]+"
STOP = si.STOP_CHARS


def old_units(text, sizes=(2,), drop_stopwords=False):
    out = []
    for chunk in re.findall(r"[A-Za-z0-9_]+|" + _HAN, text):
        if re.fullmatch(r"[A-Za-z0-9_]+", chunk):
            out.append(chunk.lower())
            continue
        for n in sizes:
            if n == 1:
                out.extend(c for c in chunk if c not in STOP)
            else:
                out.extend(chunk[i:i + n] for i in range(len(chunk) - n + 1))
    return out


si.gram_units = old_units            # 函数按模块全局名查找，补丁对整条 CLI（含 matched_hooks）生效
si.to_index_text = lambda t: " ".join(old_units(t, sizes=(1, 2)))

quiet = io.StringIO()
with contextlib.redirect_stdout(quiet):     # 建索引的提示不污染 stdout，只留最后一行 JSON
    si.cmd_build(kb, si.DEFAULT_NOTES_DIR, True)
out = {}
for tag, q in queries:
    buf = io.StringIO()
    sys.argv = ["search_index.py", "recall", "--kb", kb, "--query", q, "--json", "--k", "5"]
    try:
        with contextlib.redirect_stdout(buf):
            si.main()
    except SystemExit:
        pass
    j = json.loads(buf.getvalue())
    out[tag] = {"grams": old_units(q, drop_stopwords=True),
                "fts_kept": j["fts_stats"]["kept"],
                "hits": [h["path"] for h in j["hits"]]}
print(json.dumps(out, ensure_ascii=False))
'''


def p12_lang_build():
    """造 lang 夹具库：五种语言各一篇原子笔记（正文 ≥200B 断言）+ config。返回 (kb, 笔记目录, config)。"""
    root = os.path.join(WORK, "p12_lang")
    kb = os.path.join(root, "kb")
    for d in ("_meta", "00_导航", "99_收件箱", "概念索引", "素材库/_来源地图",
              "工作流/多语言/1_测试"):
        os.makedirs(os.path.join(kb, *d.split("/")), exist_ok=True)
    w(os.path.join(kb, "README.md"), "# 多语言库\n")
    w(os.path.join(kb, "AGENTS.md"), "# 规则\n\n改动分三档：L0 直接做、L1 先确认、L2 禁止。\n")
    w(os.path.join(kb, "_meta", "问题资产库.md"), "# 问题资产库\n")
    notes = os.path.join(kb, "工作流", "多语言", "1_测试")
    for fn, title, body, hook, _tag, _q in LANG_NOTES:
        text = ("---\ntitle: %s\nflow: 多语言\nstage: 1_测试\nsubstage: 语种对照\n"
                "domains: [内容创作]\nforms: [方法论]\ntools: [Codex]\ntypes: [素材]\n"
                "projects: [夹具]\ntopics: [关键词]\nq_hooks: [%s]\n"
                "updated: 2026-10-06\nstale: false\n---\n\n# %s\n\n%s\n"
                % (title, hook, title, body))
        n = len(text.encode("utf-8"))
        assert n >= 200, "lang 夹具 %s 只有 %dB（测试台方法论第 5 条）" % (fn, n)
        w(os.path.join(notes, fn), text)
    src = os.path.join(root, "src")
    os.makedirs(src, exist_ok=True)
    cfgp = os.path.join(root, "config.json")
    w(cfgp, json.dumps({
        "kb_root": kb.replace("\\", "/"), "notes_dir": "工作流",
        "source_root": src.replace("\\", "/"),
        "rules": {"new_note": "L0", "fix_format": "L0", "add_tags": "L0"},
        "sample_notes": [],
        "directories": [{"path": d, "create": True, "reason": "夹具"} for d in
                        ("_meta", "00_导航", "99_收件箱", "概念索引", "素材库/_来源地图",
                         "工作流", "工作流/多语言", "工作流/多语言/1_测试")]},
        ensure_ascii=False))
    return kb, notes, cfgp


def p12_lang():
    """P12 lang 组：A1 语言适配的 11 条断言（含 1 条端到端负控 + 1 条分母红线对照）。"""
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    import sqlite3
    import search_index as si
    import audit as au
    V, SI = os.path.join(SCRIPTS, "verify.py"), os.path.join(SCRIPTS, "search_index.py")
    kb, notes, cfgp = p12_lang_build()

    _HAN = "[" + chr(0x4e00) + "-" + chr(0x9fff) + "]"      # 旧口径只认这一段汉字

    def old_units(text, sizes=(2,), drop_stopwords=False):
        out = []
        for chunk in re.findall(r"[A-Za-z0-9_]+|" + _HAN + "+", text):
            if re.fullmatch(r"[A-Za-z0-9_]+", chunk):
                out.append(chunk.lower())
                continue
            for n in sizes:
                if n == 1:
                    out.extend(c for c in chunk if c not in si.STOP_CHARS)
                else:
                    out.extend(chunk[i:i + n] for i in range(len(chunk) - n + 1))
        return out

    run([SI, "build", "--kb", kb, "--rebuild"], 0, "P12 lang 建索引（v4）")
    new = {}
    for _fn, _t, _b, _h, tag, q in LANG_NOTES:
        rc, out = run([SI, "recall", "--kb", kb, "--query", q, "--json", "--k", "5"],
                      0, "P12 lang recall " + tag)
        j = json.loads(out)
        hs = j["hits"]
        new[tag] = {"q": q, "grams": si.gram_units(q, drop_stopwords=True),
                    "hits": [h["path"] for h in hs],
                    # 只认「走 FTS 通道且 bm25 非空」的那一条：recall 还有 hook/topic/relation
                    # 三条通道会把别的笔记补回来（夹具五篇共用 topic「关键词」），
                    # 断言的对象是分词口径，不是通道数——补回的噪音不能算命中。
                    "fts_paths": [os.path.basename(h["path"]) for h in hs
                                  if "fts" in (h.get("channels") or []) and h["bm25"] is not None],
                    "bm25": [h["bm25"] for h in hs if h["bm25"] is not None],
                    "kept": j["fts_stats"]["kept"]}
    drv_dir = os.path.join(WORK, "p12_lang", "oldcode")
    os.makedirs(drv_dir, exist_ok=True)
    drv = os.path.join(drv_dir, "oldrun.py")
    w(drv, LANG_OLD_DRIVER)
    qs = json.dumps([[tag, q] for _f, _t, _b, _h, tag, q in LANG_NOTES], ensure_ascii=False)
    rc_o, o_out, e_out = dir_run([drv, kb, SCRIPTS, qs], label="P12 lang 负控（旧口径 CLI）")
    old = json.loads(o_out.strip().split("\n")[-1]) if rc_o == 0 else {}

    langs = ("ko", "ja", "fr", "ru")
    check("P12-lang① 五语端到端全命中：v4 分词下中文对照 + 纯韩文 + 假名混汉 + 变音拉丁 + 西里尔，"
          "每篇都由 **FTS 通道**单独保住（kept==1 且带 bm25 的 FTS 命中就是本篇自己）——"
          "查询只出现在正文，hook/topic/relation 三条通道补回来的别的篇目不算命中",
          all(new[t]["kept"] == 1 and new[t]["fts_paths"] == [t + ".md"] for t in ("cn",) + langs)
          and all(len(new[t]["grams"]) >= 1 for t in langs),
          " | ".join("%s gram=%d kept=%d fts=%s bm25=%s" % (
              t, len(new[t]["grams"]), new[t]["kept"], new[t]["fts_paths"],
              round(new[t]["bm25"][0], 4) if new[t]["bm25"] else None)
              for t in ("cn",) + langs)[:240])
    check("P12-lang② **负控**：同一套夹具、同一条 CLI，把 gram_units/to_index_text 退回 A1 之前——"
          "韩文与西里尔查询切出 **0 个 gram**、FTS 保留 0、命中 0；证明 ① 不是空断言"
          "（假名混汉只剩汉字 gram 撞运气，变音拉丁碎成 vid+éos，都不在 ① 的判据里）",
          rc_o == 0 and old.get("ko", {}).get("grams") == [] and old.get("ru", {}).get("grams") == []
          and old.get("ko", {}).get("hits") == [] and old.get("ru", {}).get("hits") == []
          and old.get("ru", {}).get("fts_kept") == 0,
          "旧 ko=%s｜旧 ru=%s" % (old.get("ko"), old.get("ru"))[:200])

    cn_text = open(os.path.join(notes, "cn.md"), encoding="utf-8").read()
    a, b = set(si.gram_units(cn_text)), set(old_units(cn_text))
    diff = a ^ b
    check("P12-lang③ 中文夹具结果不变：中文篇在新旧口径下的 gram 差集**只出现在字母词段**（词干归一），"
          "汉字段一条不差——A1 改的是分流，不是中文口径",
          all(g.isascii() for g in diff)
          and {g for g in a if not g.isascii()} == {g for g in b if not g.isascii()},
          "差集=%s｜汉字集合相同=%s" % (sorted(diff), bool(diff) or "无差异"))

    ko_idx, ja_idx = si.to_index_text("키워드 선정"), si.to_index_text("動画企画の")
    check("P12-lang④ 单字档只给汉字/假名开：韩文（与泰文）段索引里**没有单字 gram**——谚文字母、"
          "泰文辅音单独成 gram 没有检索价值；汉字/假名段保留单字以兼容 1 字查询",
          all(len(t) >= 2 for t in ko_idx.split()) and any(len(t) == 1 for t in ja_idx.split()),
          "ko=%s｜ja=%s" % (ko_idx[:60], ja_idx[:60]))
    mixed = si.gram_units("关键词คัดค้น한국어문")
    check("P12-lang⑤ 跨脚本相邻**不产跨段 gram**：关键词คัดค้น한국어문 里没有「词ค」也没有「문한」"
          "（汉字/假名与韩文/泰文分属两段，合成一段时旧写法会产，那是 DF 噪音），"
          "但两段各自的 gram 都在",
          "词ค" not in mixed and "문한" not in mixed
          and "คั" in mixed and "한국" in mixed and "关键" in mixed,
          "gram=%s" % mixed[:14])
    check("P12-lang⑥ 轻量词干只三件事：变音拉丁**整词不碎**（vidéos 不被 ASCII 类拆成 vid+éos）、"
          "非 ASCII **不剥**（клучевые 原样，俄文词形变化是已知边界）、剥完**至少留 3 个码点**"
          "（cats→cat，但 cas 不剥）；无例外表，索引侧与查询侧同一函数所以同一个词永远自配",
          si.gram_units("vidéos") == ["vidéos"] and si.gram_units("клучевые") == ["клучевые"]
          and si.stem_light("cats") == "cat" and si.stem_light("cas") == "cas"
          and si.gram_units("doc_maps.jsonl") == ["doc_map", "jsonl"],
          "vidéos=%s｜клучевые=%s｜doc_maps.jsonl=%s"
          % (si.gram_units("vidéos"), si.gram_units("клучевые"), si.gram_units("doc_maps.jsonl")))
    check("P12-lang⑦ 停用词只在字母词段生效且**分侧**：表规模 en=50 / ru=30（裁决书 ~50/~30 落成定值）；"
          "索引侧不删（to_index_text 里 the 仍在 → 纯停用词查询仍有召回），查询侧删；"
          "中文段与韩文段 drop 与否结果**逐条相同**",
          len(si.STOP_WORDS["en"]) == 50 and len(si.STOP_WORDS["ru"]) == 30
          and "the" in si.to_index_text("the best videos").split()
          and "the" not in si.gram_units("the best videos", drop_stopwords=True)
          and si.gram_units("关键词选品", drop_stopwords=True) == si.gram_units("关键词选品")
          and si.gram_units("키워드 선정", drop_stopwords=True) == si.gram_units("키워드 선정"),
          "en=%d ru=%d｜索引=%s｜查询=%s" % (len(si.STOP_WORDS["en"]), len(si.STOP_WORDS["ru"]),
                                          si.to_index_text("the best videos"),
                                          si.gram_units("the best videos", drop_stopwords=True)))
    rc_n, o_n = run([SI, "recall", "--kb", kb, "--query", "the a an", "--json", "--k", "3"],
                         0, "P12 lang 纯停用词查询")
    check("P12-lang⑧ 护栏①：整段查询**全是**停用词时不删（gram 不塌成空 MATCH），端到端 rc=0 且输出里"
          "没有 Traceback / lost sys.stderr——「查不到」是数据问题，「把查询弄空」是工具崩；"
          "半停用词查询照常删（the video → 只剩 video）",
          si.gram_units("the a an", drop_stopwords=True) == ["the", "a", "an"]
          and si.gram_units("the video", drop_stopwords=True) == ["video"]
          and rc_n == 0 and "Traceback" not in o_n and "lost sys.stderr" not in o_n,
          "全停用=%s｜半停用=%s｜rc=%s" % (si.gram_units("the a an", drop_stopwords=True),
                                        si.gram_units("the video", drop_stopwords=True), rc_n))
    hook, query = "what is the price", "who can help me with the price of the course"
    landed = si.matched_hooks({"q_hooks": [hook]}, query,
                              set(si.gram_units(query, drop_stopwords=True)))
    real = si.gram_units
    try:
        si.gram_units = lambda t, sizes=(2,), drop_stopwords=False: real(t, sizes=sizes,
                                                                         drop_stopwords=False)
        naive = si.matched_hooks({"q_hooks": [hook]}, query, set(si.gram_units(query)))
        kept_true = si.matched_hooks({"q_hooks": ["how do I get started"]},
                                     "how do I get started with video editing",
                                     set(si.gram_units("how do I get started with video editing")))
    finally:
        si.gram_units = real
    check("P12-lang⑨ **红线②**：停用词不进 matched_hooks 的 gram 分母——分母留着虚词时这条 hook 会以"
          " 2/4=0.5 ≥ 0.35 **假阳性命中**；实现里分母只剩 price/what、共同 1 个 < 地板 2 → 不命中。"
          "真命中不伤（how do I get started 仍命中）",
          landed == [] and naive == [hook] and kept_true == ["how do I get started"],
          "落地=%s｜对照（虚词占分母）=%s｜真命中=%s" % (landed, naive, kept_true))
    _, ov4, _ = dir_run([V, "--kb", kb, "--config", cfgp], label="P12 lang verify（v4 索引）")
    line4 = c_line(ov4, "C12")
    db = os.path.join(kb, "_meta", "search.db")
    con = sqlite3.connect(db)
    con.execute("UPDATE meta SET value='3' WHERE key='schema_version'")
    con.commit()
    con.close()
    _, ov3, _ = dir_run([V, "--kb", kb, "--config", cfgp], label="P12 lang verify（meta 改回 v3）")
    line3 = c_line(ov3, "C12")
    run([SI, "build", "--kb", kb, "--rebuild"], 0, "P12 lang 重建回 v4")
    check("P12-lang⑩ 分词改了 schema 必须 +1：SCHEMA_VERSION==4，C12 对 v4 索引 PASS、对旧 v3 索引 "
          "FAIL 并指名「请 --rebuild 重建」——否则新分词跑旧索引，检索静默按旧口径出结果",
          si.SCHEMA_VERSION == 4 and line4.startswith("[PASS]") and "schema v4" in line4
          and line3.startswith("[FAIL]") and "v3 ≠ 期望 v4" in line3,
          "v4=%s｜v3=%s" % (line4[:76], line3[:76]))
    ko_fm = si.parse_frontmatter(open(os.path.join(notes, "ko.md"), encoding="utf-8").read())
    ko_body = si.FRONT_RE.sub("", open(os.path.join(notes, "ko.md"), encoding="utf-8").read(), count=1)
    ko_g = au._doc_bigrams(ko_fm, ko_body)
    hangul = lambda g: chr(0xac00) <= g[0] <= chr(0xd7a3)
    letter_g = au._doc_bigrams({"title": "AI 选题", "q_hooks": []}, "AI 选题 videos")
    check("P12-lang⑪ audit 的 A4 口径与 gram_units 同源：韩文篇现在**有** bigram（旧口径按「首字是汉字」"
          "筛，韩文/假名/泰文一条都进不去 DF 统计），而字母整词永远不进——长度恰好为 2 的 'ai' 也不冒充 bigram",
          len(ko_g) >= 3 and any(hangul(g) for g in ko_g)
          and all(len(g) == 2 and si.NGRAM_SEG_RE.fullmatch(g) for g in ko_g)
          and "ai" not in letter_g and "video" not in letter_g and "选题" in letter_g,
          "ko bigram=%d %s｜字母段=%s" % (len(ko_g), sorted(ko_g)[:6], sorted(letter_g)))


# ---------------------------------------------------------------- P12 · fb 组（兜底不得产出可用值）
FB_DRIVER = """# -*- coding: utf-8 -*-
import sys, io, runpy
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.modules["search_index"] = None      # 屏蔽导入：与 sys.path 无关（verify 会自己把 scripts 插到最前）
sys.argv = {argv}
runpy.run_path({vp}, run_name="__main__")
"""


def p12_fb():
    """P12 fb 组：同源 except 兜底全改 None 后的三条断言（1 条规则 + 2 条端到端）。"""
    import ast as _ast
    import io                       # probe 顶层没有 io（其他地方用的是 open）
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)  # 本组要 self-contained：单独跑也不能依赖前面的组替它铺路径
    import search_index as _si
    V = os.path.join(SCRIPTS, "verify.py")

    # ---- ① 规则条（判据而非清单：新脚本再写一份可用兜底就会被抓）----
    def fb_scan(paths):
        """扫一批文件，返回「except 兜底产出了可用常量值」的违例清单（真仓与负控共用一个实现）。"""
        found = []
        for fp in paths:
            tree = _ast.parse(io.open(fp, encoding="utf-8").read())
            for node in _ast.walk(tree):
                if isinstance(node, _ast.Try):
                    for h in node.handlers:
                        for st in h.body:
                            tg = st.targets if isinstance(st, _ast.Assign) else (
                                [st.target] if isinstance(st, _ast.AnnAssign) else [])
                            for nm in tg:
                                if (isinstance(nm, _ast.Name) and nm.id.isupper()
                                        and not (isinstance(st.value, _ast.Constant)
                                                 and st.value.value is None)):
                                    found.append("handler %s:%d %s=%s" % (
                                        os.path.basename(fp), nm.lineno, nm.id,
                                        _ast.unparse(st.value)[:22]))
                if (isinstance(node, _ast.Call) and getattr(node.func, "id", "") == "getattr"
                        and len(node.args) >= 3 and isinstance(node.args[1], _ast.Constant)
                        and isinstance(node.args[1].value, str) and node.args[1].value.isupper()
                        and not (isinstance(node.args[2], _ast.Constant)
                                 and node.args[2].value is None)):
                    found.append("getattr %s:%d getattr(...,%s,%s)" % (
                        os.path.basename(fp), node.lineno, node.args[1].value,
                        _ast.unparse(node.args[2])[:18]))
        return found

    viol = fb_scan([os.path.join(SCRIPTS, f) for f in sorted(os.listdir(SCRIPTS))
                    if f.endswith(".py")] + [os.path.abspath(__file__)])
    # 负控：现造一份"兜底给出可用值"的脚本。两条违例**各归一个子判据**（放同一行会被双计），
    # 抓到数不等于 2 就说明判据失效或双计——① 因此不是空断言。
    neg = os.path.join(WORK, "p12_fb", "negcontrol.py")
    w(neg, "import sys\ntry:\n    import zzz\n    OK = zzz.OK\n"
           "    DIR = getattr(sys, 'XDIR', '工作流')\n"
           "except Exception:\n    OK = {'a': 1}\n")
    neg_hit = fb_scan([neg])
    neg_tags = sorted({x.split()[0] for x in neg_hit})
    neg_lines = sorted({x.split()[1].split(":")[1] for x in neg_hit})
    check("P12-fb① 规则条：全仓 scripts/*.py + probe.py 里 **except handler 内对全大写常量的赋值**，"
          "右值只能是 None；`getattr(x, \"UPPER\", 字面量)` 同判。兜底一旦产出可用值，C12/C14 就会拿"
          "猜出来的口径去判真库——本批改前实测 verify 的期望索引版本停在 2，而真库已是 4。"
          "**负控**：现造的违例脚本（handler 内 dict 兜底 + try 内 getattr 字面量兜底）"
          "必须被同一函数抓到 2 条",
          viol == [] and len(neg_hit) == 2 and neg_tags == ["getattr", "handler"]
          and len(neg_lines) == 2,
          ("真仓命中：" + "；".join(viol[:4])) if viol else
          "真仓 0 处｜负控 %d/2 命中子判据=%s 行号=%s" % (
              len(neg_hit), neg_tags, neg_lines))

    # ---- 夹具库：笔记目录叫 notes；备一份不带 notes_dir 的 config，好让「没给目录」这条真有解 ----
    kb, src, cfgp = p12_dir_build("p12_fb", "notes")
    cfg = json.load(io.open(cfgp, encoding="utf-8"))
    cfgp_no = os.path.join(WORK, "p12_fb", "config_no_dir.json")
    w(cfgp_no, json.dumps({k: v for k, v in cfg.items() if k != "notes_dir"}, ensure_ascii=False))
    def spawn(argv):
        """**不往 ROWS 记账**：本组按裁决只贡献 3 项（建索引与两次驱动的证据写进断言 detail，不丢）。"""
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable] + argv, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        return p.returncode, (p.stdout or ""), (p.stderr or "")

    idx_rc, idx_out, _ie = spawn([os.path.join(SCRIPTS, "search_index.py"), "build",
                                  "--kb", kb, "--notes", "notes", "--rebuild"])
    fp0 = p10_fingerprint(kb)
    drv = os.path.join(WORK, "p12_fb", "fb_driver.py")

    def fb_run(extra):
        w(drv, FB_DRIVER.format(argv=repr(["verify.py"] + extra), vp=repr(V)))
        return spawn([drv])

    # ---- ② fb-a：口径不可用就整条红，不带着 None 往下跑 ----
    rc, out, err = fb_run(["--kb", kb, "--config", cfgp_no])
    same = p10_fingerprint(kb) == fp0
    check("P12-fb② 端到端 fb-a：屏蔽 search_index 导入 + **不给** --notes → rc=1、文案走 stderr 并指名"
          "「search_index 导入失败」（不是「笔记目录不存在，请 rebuild」那类误导）、stdout 一行 "
          "[PASS]/[FAIL] 都不打（防半跑半写）、无 Traceback、临时库指纹不变",
          rc == 1 and idx_rc == 0
          and "无法确定笔记目录口径（search_index 导入失败）" in err
          and "Traceback" not in (out + err) and not out.strip() and same,
          "索引rc=%d｜rc=%d｜stderr=%s｜stdout 行=%d｜指纹不变=%s" % (
              idx_rc, rc, (err.strip().splitlines() or ["(空)"])[-1][:52],
              len(out.splitlines()), same))

    # ---- ③ fb-b：改前这里会打出「v4 ≠ 期望 v2」，把导入失败误诊成索引过期 ----
    rc2, out2, err2 = fb_run(["--kb", kb, "--config", cfgp_no, "--notes", "notes"])
    l12 = c_line(out2 + err2, "C12")
    check("P12-fb③ 端到端 fb-b：屏蔽导入 + 给 --notes → C12 = [FAIL] 且文案只说"
          "「无法确定期望索引版本（search_index 导入失败）」，不出现「期望 None」「≠ 期望」这种拿兜底值"
          "比出来的误诊；同一进程正常导入下 SCHEMA_VERSION 仍为 4（C12 对 v4 PASS 由 P12-lang⑩ 钉住）",
          l12.startswith("[FAIL]") and "search_index 导入失败" in l12
          and "≠ 期望" not in l12 and "期望 None" not in out2 and _si.SCHEMA_VERSION == 4,
          "索引rc=%d｜C12=%s｜rc=%d" % (idx_rc, l12[:64], rc2))

    # ---- ④ 真负控：两臂各测一种「口径坏法」。为什么不按字面写 ----
    #   · 实测：monkeypatch `build_units.VALID_TYPES` 对 si **无效**——VALID_UNIT_TYPES 是 import
    #     期绑定的名字，事后改源模块只是「看起来改了」，recall 照旧 rc=0、输出正常 → 断言会空跑。
    #   · 实测：`pull` 根本不读这张表（cmd_pull → run_query；只有 cmd_recall → validate_route 用），
    #     拿 pull 当靶，rc≠0 会由「recipe 不存在」之类凑数。
    #   → 因此打消费端绑定 + 用 recall。臂A＝None（响亮红）；臂B＝集外值（有日志的软错，不对称是设计）。
    wlog = os.path.join(kb, "_meta", "logs", "route_warnings.jsonl")

    def fb4(value_src):
        route = '{"unit_type": "claim", "keywords": ["笔记甲"]}'
        drv = os.path.join(WORK, "p12_fb", "fb4_driver.py")
        w(drv, "import sys, io\n"
               "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')\n"
               "sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')\n"
               "sys.path.insert(0, %r)\n"
               "import search_index as si\n"
               "si.VALID_UNIT_TYPES = %s\n"
               "sys.argv = %r\n"
               "si.main()\n"
               % (SCRIPTS, value_src,
                  ["search_index.py", "recall", "--kb", kb, "--query", "笔记甲",
                   "--route-json", route, "--k", "3"]))
        return spawn([drv])

    before = os.path.getsize(wlog) if os.path.isfile(wlog) else 0
    rc_a, out_a, err_a = fb4("None")
    rc_b, out_b, err_b = fb4("{'__OUT_OF_SET__'}")
    newlog = ""
    if os.path.isfile(wlog) and os.path.getsize(wlog) > before:
        with io.open(wlog, encoding="utf-8") as fh:
            fh.seek(before)
            newlog = fh.read()
    check("P12-fb④ 真负控（不是空断言）：臂A 把 si.VALID_UNIT_TYPES 打成 None（＝except 分支的产物）+"
          "跑 recall → 必须 rc≠0、文案是「unit_type 口径不可用」，不得 rc=0、不得抛 Traceback；"
          "臂B 打成集外值（口径存在但坏）→ rc=0 且**必须往 route_warnings.jsonl 落一条 "
          "unit_type_invalid**，把它钉成「有日志的软错」——谁哪天改成静默丢弃，这条就红",
          rc_a != 0 and "unit_type 口径不可用" in (out_a + err_a)
          and "Traceback" not in (out_a + err_a)
          and rc_b == 0 and "unit_type_invalid" in newlog and "__OUT_OF_SET__" in newlog,
          "臂A rc=%d｜臂B rc=%d｜新增日志 %d 字节，含集外标记=%s"
          % (rc_a, rc_b, len(newlog), "__OUT_OF_SET__" in newlog))


# ---------------------------------------------------------------- P12 · sb 组（拆篇候选边界）
SB_DOC = (
    "# 拆篇边界夹具\n\n"
    "## 一、资产表与文字表同时在场\n\n"
    "这一段说明判据：因为素材链接会过期、图片不随文复刻，所以 184 个资产表单位、85,691 字"
    "不值得单独立篇；关键在于按内容判表，不是按标签判表。\n\n"
    "<table><colgroup><col/><col/></colgroup><tbody>"
    "<tr><td>![](assets/SBFAKE0001/037.jpg)</td><td>![](assets/SBFAKE0001/038.jpg)</td></tr>"
    "<tr><td>![缺失素材:None]</td><td>![缺失素材:None]</td></tr></tbody></table>\n\n"
    "**1.1 文字表格必须留下**\n\n"
    "| 判据 | 说明 |\n|---|---|\n| 高频 | 每周超过 5 次 |\n| 可标准化 | 有模板有分类，能批量 |\n\n"
    "## 二、围栏整体不可切\n\n"
    "看这个提示词模板，关键在于三行结构：\n\n"
    "```Markdown\n"
    "【角色】你是出题人。\n\n【任务】随机抽 A/B 两类组合出题，共 12 题。\n\n【禁词】不要出现霓虹灯。\n"
    "```\n\n"
    "## 三、超长无空行段落的处置流程\n\n"
    "**先讲清楚再动手：**\n\n"
    + ("这套流程的关键在于每一步都要把上一步的 3 项产物当输入来用，" * 60)
    + "\n\n收尾段：所以按语义再拆的活儿仍归深抽。\n"
    "## 四、四反引号包内嵌三反引号（发现 37 的回归面）\n\n"
    "外层模板用四个反引号开栏，是因为里面要放一个三反引号示例：\n\n"
    "````Markdown\n"
    "【外层角色】你是配置模板。\n\n"
    "示例输入：\n"
    "```Plaintext\n"
    "【内层】这段嵌在外层里面，按内容算，不是独立围栏。\n"
    "```\n\n"
    "【外层规则】输出必须是 JSON。\n"
    + ("规则条目：整段复制不得拆分，缺一条下游就跑不通；" * 60) + "\n"
    "````\n\n"
    "外层闭栏之后的正文必须独立成段，不能被吞进围栏。\n"
)
DOC_TXT = ""


def sb_bodies(rec, text):
    """sb 的 JSONL **不存正文**（存了就等于造第二份语料）——按绝对偏移回读源文件。"""
    out = []
    for b in rec["blocks"]:
        for s in b["segments"]:
            a = b["block_start"] + s["rel_start"]
            out.append((b, s, text[a:a + s["len"]]))
    return out


def p12_sb():
    """P12 sb 组：split_boundaries 三条规约定稿 + 确定性 + 1 条负控（判据必须是活的）。"""
    import io
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)
    root = os.path.join(WORK, "p12_sb")
    src = os.path.join(root, "src")
    os.makedirs(src, exist_ok=True)
    doc = os.path.join(src, "sb_doc.md")
    w(doc, SB_DOC)
    global DOC_TXT
    DOC_TXT = io.open(doc, encoding="utf-8").read()
    SBPY = os.path.join(SCRIPTS, "split_boundaries.py")
    DMPY = os.path.join(SCRIPTS, "doc_map.py")
    kbmap, out1, out2, negj = (os.path.join(root, "doc_maps.jsonl"), os.path.join(root, "sb1.jsonl"),
                               os.path.join(root, "sb2.jsonl"), os.path.join(root, "neg.jsonl"))

    def spawn(argv):
        """**不往 ROWS 记账**：本组按裁决只贡献 5 项（建图与三次候选跑的证据写进断言 detail）。"""
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        p = subprocess.run([sys.executable] + argv, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        return p.returncode, (p.stdout or ""), (p.stderr or "")

    rc_map, _, err_map = spawn([DMPY, "--source-root", src, "--out", kbmap])
    rc1, o1, e1 = spawn([SBPY, "--doc-maps", kbmap, "--source-root", src, "--out", out1])
    rc2, _, _ = spawn([SBPY, "--doc-maps", kbmap, "--source-root", src, "--out", out2])
    b1 = open(out1, "rb").read()
    rec = json.loads(b1.decode("utf-8").splitlines()[0]) if b1 else {"blocks": []}
    segs = sb_bodies(rec, DOC_TXT)
    body_all = "".join(t for _, _, t in segs)
    dstat = [l for l in (o1 + e1).splitlines() if "规约读数" in l]
    same = b1 == open(out2, "rb").read()

    # ---- ① 确定性 ----
    check("P12-sb① 同一输入两次跑**逐字节相同**：拆篇候选必须是可复核的派生物，不是每次重猜"
          "（doc_map 建图 rc=%d，本组不动 doc_map 的按标题切块口径）" % rc_map,
          rc_map == 0 and rc1 == 0 and rc2 == 0 and same and len(segs) > 0,
          "两次一致=%s｜候选段 %d｜高价值块 %d｜读数：%s" % (
              same, len(segs), len(rec["blocks"]),
              (dstat[0].split("规约读数：")[-1][:76] if dstat else "(无读数行)")))

    # ---- ② 规约①：按内容判表 ----
    mt_leak = "assets/SBFAKE0001" in body_all or "缺失素材" in body_all
    txt_tbl = "可标准化" in body_all and "每周超过 5 次" in body_all
    dropped = sum(b["table_chars"] for b in rec["blocks"])
    units_mt = sum(b["table_units"] for b in rec["blocks"])
    check("P12-sb② 规约①**按内容**判表：05 真实形状的 `![](assets/….jpg)`／`![缺失素材:None]` 资产表"
          "整块**不产候选段**（字数计入 table_chars），而「判据｜说明」型文字表格必须留在候选段里——"
          "两类表一起丢或一起留都会红（反例基准：#60 的「手动版 VS 进阶自动化」对比表必须保留）",
          not mt_leak and txt_tbl and dropped >= 100 and units_mt >= 1,
          "资产表漏进候选段=%s｜文字表格在册=%s｜弃表 %d 单位 / %d 字" % (
              mt_leak, txt_tbl, units_mt, dropped))

    # ---- ③ 规约②：围栏整体不可切，且与说明段落粘连 ----
    import re as _re
    fences = [(m.start(), m.end()) for m in _re.finditer(
        "(?m)^[ \\t]{0,3}```[\\s\\S]*?^[ \\t]{0,3}```[ \\t]*$", DOC_TXT)]
    partial = sum(1 for b, s, _t in segs
                  for fa, fb in fences
                  if fa < b["block_start"] + s["rel_start"] < fb
                  or fa < b["block_start"] + s["rel_start"] + s["len"] < fb)
    fenced = [t for _b, _s, t in segs if "【角色】" in t]
    intact = bool(fenced) and all("【禁词】" in t for t in fenced)
    glued = bool(fenced) and all(0 <= t.find("看这个提示词") < t.find("【角色】") for t in fenced)
    check("P12-sb③ 规约②：代码围栏**整体不可切**且**与它的说明段落粘连**——任何候选段的起止都不得"
          "落在围栏内部；含【角色】的段必须同时含【禁词】（没被劈开）、且引子「看这个提示词」出现在"
          "围栏之前并同段。05 实测教训：按 ` ```…``` ` 正则配对会被正文里的 replaceAll 骗出"
          "落在一行中间的假边界，故按整行配对",
          fences and partial == 0 and intact and glued,
          "围栏 %d 段｜部分覆盖 %d｜整块在册=%s｜粘连引子=%s" % (
              len(fences), partial, intact, glued))

    # ---- ④ 规约③：超限单位先粘连、不硬切 ----
    wall = [t for _b, _s, t in segs if "这套流程的关键在于" in t]
    intro_ok = bool(wall) and all(
        0 <= t.find("**先讲清楚再动手：**") < t.find("这套流程的关键在于") for t in wall)
    nfrag = sum(1 for _b, s, _t in segs if s["frag"])
    novs = sum(1 for _b, s, _t in segs if s["oversized_frag"])
    novf = sum(1 for _b, s, _t in segs if s["oversized_fence"])
    inside_line = [b["heading"] + "@" + str(s["rel_start"]) for b, s, _t in segs
                   if s["rel_start"] > 0
                   and DOC_TXT[b["block_start"] + s["rel_start"] - 1] not in "\n \t"]
    longest = max([s["len"] for _b, s, _t in segs] or [0])
    check("P12-sb④ 规约③（11 段实测定稿）：超限的普通单位**先与前段粘连**（前段是引子：标题行/冒号"
          "结尾，或 ≤400 字）且**禁链式**，粘完仍超 LIMIT ⇒ 整段标 oversized_frag 交深抽按语义再拆；"
          "**绝不在无结构处硬切**——实测「切点前一字符非空白」必须为 0 处。本夹具的 1,800 字无空行墙"
          "必须整段在册、与引子同段、带 frag+oversized_frag；oversized_fence 只许有 ⑥ 那**一段**"
          "（夹具里唯一的超长围栏），多出来就是规约③ 偷偷产了 fence 标记",
          wall and intro_ok and nfrag >= 1 and novs >= 1 and inside_line == [] and novf == 1,
          "墙段 %d（引子同段 %d）｜frag %d｜oversized_frag %d｜oversized_fence %d｜行内切点 %d｜最长段 %d 字" % (
              len(wall), int(intro_ok), nfrag, novs, novf, len(inside_line), longest))

    # ---- ⑤ 负控：把规约①的判据摘掉，资产表必须漏回候选段 ----
    drv = os.path.join(root, "negctl.py")
    w(drv, "import sys\n"
           "sys.path.insert(0, %r)\n"
           "import split_boundaries as sb\n"
           "sb.is_media_table = lambda u: False\n"
           "sys.argv = %r\n"
           "sb.main()\n"
           % (SCRIPTS, ["split_boundaries.py", "--doc-maps", kbmap,
                        "--source-root", src, "--out", negj]))
    rcn, _, _ = spawn([drv])
    nb = open(negj, "rb").read() if os.path.isfile(negj) else b""
    nrec = json.loads(nb.decode("utf-8").splitlines()[0]) if nb else {"blocks": []}
    nbody = "".join(t for _b, _s, t in sb_bodies(nrec, DOC_TXT))
    ntable = sum(b["table_chars"] for b in nrec["blocks"])
    leaked = ("assets/SBFAKE0001" in nbody or "缺失素材" in nbody) or ntable == 0
    check("P12-sb⑤ **负控**（证明 ② 不是空断言）：把 `sb.is_media_table` 摘成恒 False 再跑同一份夹具，"
          "资产表文本必须**漏回候选段**（或弃字数归零）；同时正常路径 rc 仍为 0——"
          "说明红是判据在咬，不是脚本在崩",
          rcn == 0 and leaked,
          "负控 rc=%d｜漏回候选段=%s｜负控弃字数 %d（正跑 %d）｜负控候选段 %d（正跑 %d）" % (
              rcn, leaked, ntable, dropped,
              len(sb_bodies(nrec, DOC_TXT)), len(segs)))

    # ---- ⑥ 发现 37：四反引号外层围栏必须整块配对，内层 ``` 只算内容 ----
    #   夹具把外层模板撑过 LIMIT：修后＝**1 段 oversized_fence**（内层三反引号与【外层规则】都在里面）；
    #   修前（闭栏只认恰好三个反引号）＝内层那行 ``` 提前把外层闭上，【外层规则】掉到围栏外面。
    outer = [t6 for _b, _s, t6 in segs if "【外层角色】" in t6]
    flag6 = [s for _b, s, t6 in segs if "【外层角色】" in t6 and s["oversized_fence"]]
    intact6 = bool(outer) and all(("【内层】" in t6 and "【外层规则】" in t6 and "跑不通" in t6)
                                  for t6 in outer)
    dang6 = bool(rec.get("fence_dangling"))
    drv6 = os.path.join(root, "negctl37.py")
    w(drv6, "import sys, re\n"
            "sys.path.insert(0, %r)\n"
            "import split_boundaries as sb\n"
            "sb.FENCE_CLOSE = re.compile(r\"^[ \\t]{0,3}(`{3})[ \\t]*$\")\n"   # 退回「恰好三个反引号」
            "sys.argv = %r\n"
            "sb.main()\n"
            % (SCRIPTS, ["split_boundaries.py", "--doc-maps", kbmap, "--source-root", src,
                         "--out", os.path.join(root, "neg37.jsonl")]))
    rc6, _, _ = spawn([drv6])
    n6p = os.path.join(root, "neg37.jsonl")
    nrec6 = {"blocks": [], "fence_dangling": False}
    if os.path.isfile(n6p):
        nrec6 = json.loads(open(n6p, "rb").read().decode("utf-8").splitlines()[0])
    nsegs6 = sb_bodies(nrec6, DOC_TXT)
    o6 = [t6 for _b, _s, t6 in nsegs6 if "【外层角色】" in t6]
    split6 = bool(o6) and not all("【外层规则】" in t6 for t6 in o6)
    noflag6 = not any(s["oversized_fence"] for _b, s, t6 in nsegs6 if "【外层角色】" in t6)
    dang6n = bool(nrec6.get("fence_dangling"))
    check("P12-sb⑥ **发现 37 回归面**：四反引号外层围栏（````Markdown … ````，中间嵌一个 ```Plaintext 示例）"
          "必须**整块配对**——夹具把外层撑过 LIMIT，所以修后必须是**一段 oversized_fence**，"
          "且该段同时含【内层】（内层三反引号算内容、不算独立围栏）、【外层规则】与规则条目正文；"
          "`fence_dangling` 必须为 False。**负控臂**：把闭栏判据退回\"恰好三个反引号\"再跑同一份夹具，"
          "外层必须散架——【外层规则】掉到含【外层角色】的段**外面**，或 oversized_fence 标记消失，"
          "或 `fence_dangling` 转真（三者任一即算咬住；三样都不变说明 ⑥ 是空断言）",
          bool(outer) and bool(flag6) and intact6 and not dang6 and rc6 == 0
          and (split6 or noflag6 or dang6n),
          "外层段 %d（oversized_fence %d）｜完整=%s｜dangling=%s‖负控 rc=%d｜分家=%s｜掉标=%s｜dangling=%s" % (
              len(outer), len(flag6), intact6, dang6, rc6, split6, noflag6, dang6n))

def p12_agg():
    """P12 agg 组：B8 收口另五处站点后的规则条 + 真源条 + 两臂端到端 + 现状副本负控。

    为什么判据走 AST 不走正则（他指令写的是"正则扫"，这里按实测改判）：正则 `startswith\\("_"\\)`
    在 probe.py:1666 那条 **字符串字面量**上也会命中——那行是 P12-dir⑩ 负控源码，不是用法。
    本组把两种扫法都跑一遍，把差值钉成断言的一部分，免得后人以为"扫的就是用的"。
    """
    import ast as _ast
    import io as _io
    if SCRIPTS not in sys.path:
        sys.path.insert(0, SCRIPTS)

    AGG_NOTE = """---
title: 正常笔记
flow: 测试流
stage: 3_搭建与开发
substage: 子技巧
domains: [AI]
forms: [文章]
tools: []
types: [方法]
projects: []
topics: [测试]
q_hooks:
  - 聚合页还豁不豁免
  - 下划线临时文件会不会被抓
  - 白名单外前缀谁管
sources: [x/y.md]
source_locator:
  - §测试章#char=1-20
confidence: high
status: draft
---

# 正常笔记

## 资料原话（evidence.quote）

> 原文一句
> —— `§测试章#char=1-20`

## 归纳结论

- 归纳一句

## AI 推断（inference）

- 作者未提、我的推论：只验白名单口径。
"""
    STRAY = "# 临时页\n\n没有 frontmatter，按老口径它靠 `_` 前缀逃过所有检查。\n"

    def agg_scan(paths):
        """→ (文件名级违例, 目录级豁免)。目录级＝同一条 `if` 判据里带 `isdir(...)` 调用。"""
        bad, allowed = [], []
        for fp in paths:
            tree = _ast.parse(_io.open(fp, encoding="utf-8").read())
            parents = {}
            for node in _ast.walk(tree):
                for ch in _ast.iter_child_nodes(node):
                    parents[ch] = node
            for node in _ast.walk(tree):
                if (isinstance(node, _ast.Call) and isinstance(node.func, _ast.Attribute)
                        and node.func.attr == "startswith" and node.args
                        and isinstance(node.args[0], _ast.Constant) and node.args[0].value == "_"):
                    st, test = node, None
                    while st is not None:
                        if isinstance(st, _ast.If):
                            test = st.test
                            break
                        st = parents.get(st)
                    isdir = test is not None and any(
                        isinstance(c, _ast.Call) and getattr(c.func, "attr", "") == "isdir"
                        for c in _ast.walk(test))
                    (allowed if isdir else bad).append("%s:%d" % (os.path.basename(fp), node.lineno))
        return bad, allowed

    def quiet(script, args):
        """夹具搭建类调用：不进 ROWS（建库、生成 doc_maps 不是被测行为，别把项数虚增）。"""
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + args,
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=SCRIPTS))
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    def build_arm(tag, stray):
        kb = os.path.join(WORK, tag, "kb")
        src = os.path.join(WORK, tag, "src")
        stage = os.path.join(kb, "工作流", "测试流", "3_搭建与开发")
        for d in (os.path.join(kb, "_meta"), os.path.join(kb, "00_导航"), os.path.join(kb, "99_收件箱"),
                  os.path.join(src, "x"), stage):
            os.makedirs(d, exist_ok=True)
        w(os.path.join(src, "x", "y.md"), "# 测试章\n\n原文一句归纳结论推断都在这句里，够长才不被当短文件跳过："
          + "内容" * 60 + "\n")
        w(os.path.join(stage, "正常笔记.md"), AGG_NOTE)
        w(os.path.join(stage, "_总览.md"), "# 3_搭建与开发 · 总览\n\n- [[正常笔记]]\n")
        if stray:
            w(os.path.join(stage, "_临时.md"), STRAY)
        quiet("doc_map.py", ["--source-root", src, "--out", os.path.join(kb, "_meta", "doc_maps.jsonl")])
        return kb, src, stage

    # ---- ① 规则条：全仓不许再有**文件名级** `startswith("_")`（两处负控形状自证判据不空转）----
    sfiles = [os.path.join(SCRIPTS, f) for f in sorted(os.listdir(SCRIPTS)) if f.endswith(".py")]
    probe_here = os.path.abspath(__file__)
    neg_f = os.path.join(WORK, "p12_agg", "neg_filelevel.py")
    w(neg_f, 'import os\nfor fn in os.listdir("."):\n'
             '    if fn.endswith(".md") or fn.startswith("_"):\n        continue\n')
    neg_d = os.path.join(WORK, "p12_agg", "neg_dirlevel.py")
    w(neg_d, 'import os\nfor name in os.listdir("."):\n    d = os.path.join(".", name)\n'
             '    if not os.path.isdir(d) or name.startswith("_"):\n        continue\n')
    bad_real, ok_real = agg_scan(sfiles + [probe_here])
    bad_neg, _ = agg_scan([neg_f])
    bad_neg2, ok_neg2 = agg_scan([neg_d])
    rx = sum(_io.open(p, encoding="utf-8").read().count('startswith("_")') for p in sfiles + [probe_here])
    astn = len(bad_real) + len(ok_real)
    check("P12-agg① 规则条：scripts/*.py ＋ probe.py 里**文件名级** `startswith(\"_\")` 违例必须为 0"
          "（判据走 AST：同一 `if` 判据里带 `isdir()` 的算**目录级**、豁免）。负控两形都要对——"
          "现造的 `neg_filelevel.py` 必须被抓、`neg_dirlevel.py` 必须**不**被抓；"
          "并钉住「正则命中数 > AST 命中数」（正则会把 probe.py 里那条**字符串字面量**也数进去，"
          "所以扫描口径必须是 AST，不是 grep）",
          not bad_real and ok_real == ["build_flows.py:148"] and len(bad_neg) == 1
          and not bad_neg2 and rx > astn,
          "违例=%s｜目录级豁免=%s｜负控(文件名级)=%s｜负控(目录级)=%s｜正则 %d vs AST %d" % (
              bad_real, ok_real, bad_neg, bad_neg2, rx, astn))

    # ---- ② 真源条：五个站点引用白名单，且全仓定义处不增员 ----
    FIVE = ("progress.py", "check_hooks.py", "build_flows.py", "check_verbatim_lite.py", "backfill_hooks.py")
    txts = {f: _io.open(os.path.join(SCRIPTS, f), encoding="utf-8").read() for f in FIVE}
    refs_ok = all("AGGREGATE_PAGES" in t for t in txts.values())
    no_local_def = all(not re.search(r"^AGGREGATE_PAGES = ", t, re.M) for t in txts.values())
    defs = sorted(f for f in os.listdir(SCRIPTS) if f.endswith(".py")
                  and re.search(r"^AGGREGATE_PAGES = ",
                                _io.open(os.path.join(SCRIPTS, f), encoding="utf-8").read(), re.M))
    check("P12-agg② 真源条：`progress`/`check_hooks`/`build_flows`/`check_verbatim_lite`/`backfill_hooks` "
          "五处一律引用 `search_index.AGGREGATE_PAGES`（实测这五个脚本早已直接或传递加载 search_index，"
          "所以走真源的依赖增量＝0，不需要退回复制）；五处**都不得**自定义该常量；"
          "全仓定义处必须恰是 `audit/search_index/verify` 三份（第四份复制＝漂移风险，"
          "三份逐字相同由 P12-dir⑩ 钉，这里不重复）",
          refs_ok and no_local_def and defs == ["audit.py", "search_index.py", "verify.py"],
          "五处引用齐=%s｜无本地定义=%s｜定义处=%s" % (refs_ok, no_local_def, defs))

    # ---- ③④ 两臂端到端：白名单内仍豁免 ／ 白名单外五个脚本各自表现 ----
    kbA, srcA, stA = build_arm("p12_agg_a", False)
    kbB, srcB, stB = build_arm("p12_agg_b", True)
    ND_A, ND_B = os.path.join(kbA, "工作流"), os.path.join(kbB, "工作流")

    def tot(s):
        return (re.findall(r'"notes_total": (\d+)', s) or ["?"])[0]

    rcA1, oA1 = run([os.path.join(SCRIPTS, "progress.py"), "--notes-dir", ND_A, "--format", "json"],
                    0, "P12-agg③ progress 白名单内")
    rcA2, oA2 = run([os.path.join(SCRIPTS, "check_hooks.py"), "--notes-dir", ND_A, "--format", "json"],
                    0, "P12-agg③ check_hooks 白名单内")
    rcA3, oA3 = run([os.path.join(SCRIPTS, "check_verbatim_lite.py"), "--notes-dir", ND_A,
                     "--source-root", srcA, "--kb", kbA], 0, "P12-agg③ verbatim-lite 白名单内")
    check("P12-agg③ 收口没收过头：只有「正常笔记 ＋ `_总览.md`」的库里，"
          "`_总览.md` **仍必须被跳过**（notes_total 只算 1 篇、输出里不出现把 `_总览` 当原子笔记的行）",
          tot(oA1) == "1" and tot(oA2) == "1" and "_总览" not in oA1 and "_总览" not in oA2,
          "progress 计数=%s｜check_hooks 计数=%s｜verbatim rc=%s" % (tot(oA1), tot(oA2), rcA3))

    rcB1, oB1 = run([os.path.join(SCRIPTS, "progress.py"), "--notes-dir", ND_B, "--format", "json"],
                    0, "P12-agg④ progress 临时页")
    rcB2, oB2 = run([os.path.join(SCRIPTS, "check_hooks.py"), "--notes-dir", ND_B, "--format", "json"],
                    0, "P12-agg④ check_hooks 临时页")
    rcB3, oB3 = run([os.path.join(SCRIPTS, "check_verbatim_lite.py"), "--notes-dir", ND_B,
                     "--source-root", srcB, "--kb", kbB], 0, "P12-agg④ verbatim-lite 临时页")
    rcB4, oB4 = run([os.path.join(SCRIPTS, "backfill_hooks.py"), "--notes-dir", ND_B, "--dry-run"],
                    0, "P12-agg④ backfill_hooks 临时页")
    rcB5, oB5 = run([os.path.join(SCRIPTS, "build_flows.py"), "--kb", kbB], 0, "P12-agg④ build_flows 临时页")
    gen = _io.open(os.path.join(stB, "_总览.md"), encoding="utf-8").read()
    named4 = all("_临时" in o for o in (oB1, oB2, oB3, oB4))
    check("P12-agg④ 白名单外不再免检：同一个 `_临时.md`（无 frontmatter）——"
          "`progress`/`check_hooks`/`check_verbatim_lite`/`backfill_hooks` 四处**都点名该文件**"
          "且前两处计数由 1→2；`build_flows` 按它的口径**不点名**（它是生成器不是校验器），"
          "改为钉「临时页被当原子笔记聚合进生成物」这一可见后果：`_总览.md` 里必须出现 `[[_临时`。"
          "（负控见 ⑤；把 build_flows 也算成\"点名\"会是假话，所以判据分两档写）",
          named4 and tot(oB1) == "2" and tot(oB2) == "2" and "[[_临时" in gen and "_临时" not in oB5,
          "点名 progress=%s check_hooks=%s verbatim=%s backfill=%s｜计数 %s→%s｜聚合页含临时=%s｜build_flows stdout 点名=%s" % (
              "_临时" in oB1, "_临时" in oB2, "_临时" in oB3, "_临时" in oB4,
              tot(oA1), tot(oB1), "[[_临时" in gen, "_临时" in oB5))

    # ---- ⑤ 现状副本负控：退回前缀口径后，④ 的"点名"必须消失 ----
    cur = _io.open(os.path.join(SCRIPTS, "progress.py"), encoding="utf-8").read()
    old = cur.replace("fn in AGGREGATE_PAGES", 'fn.startswith("_")', 1)
    if old == cur:
        raise SystemExit("[P12-agg] progress.py 的白名单锚点没找到——收口被改了而负控没跟着改")
    p_old = os.path.join(WORK, "p12_agg", "progress_prefix.py")
    w(p_old, old)
    rc5, o5, _e5 = dir_run([p_old, "--notes-dir", ND_B, "--format", "json"], label="P12-agg⑤ 负控(前缀版)")
    check("P12-agg⑤ 负控：把 progress 的 `fn in AGGREGATE_PAGES` 反向着陆回 `fn.startswith(\"_\")`，"
          "同一个夹具里 `_临时.md` **必须不再被点名**、notes_total 必须回到 1——"
          "证明 ④ 的\"点名\"咬在实现上，不是夹具自己就会响",
          "_临时" not in o5 and tot(o5) == "1",
          "前缀版点名=%s｜计数=%s" % ("_临时" in o5, tot(o5)))


def p12_al():
    """P12 al 组：`autolocate.parse_note` 的 evidence 配对形状。

    真库实测撞出来的：落库 29 篇全库跑 `--check` 时，8 篇老笔记被判"逐字不可回放"——
    查下去是**解析器的错**：老笔记是「一行 quote ＋ 一行引用」紧挨着排、中间不空行，
    而 parse_note 往上收 `> ` 行时**不停在上一条的引用行**，于是把
    `—— \\`§…#char=a-b\\`` 连同上一条正文一起当成 quote，第 2 条起必然找不到。
    本组把"紧凑配对"与"空行分隔"两种形状钉成同一条判据，并用**旧解析副本**做负控。
    """
    import io as _io
    D1_Q = ("商业的起点源于需求，而目前大部分老板都有三个真实的需求场景，"
            "这三个场景分别是：帮他把重复劳动自动化、帮他算清楚一笔账、帮他判断该不该做")
    D2_Q = "每周超过 5 次才算高频，低频的事情交给 AI 反而更贵"
    D3_Q = "只满足一个或零个的，最好别做，哪怕是老板强制要求的也不做"
    HEAD = "问：企业 AI 服务到底从哪儿切"

    def al_doc():
        return ("# 从需求出发，普通人如何切入企业 AI 服务\n\n## %s\n\n%s\n\n%s\n\n%s\n"
                % (HEAD, D1_Q, D2_Q, D3_Q))

    def al_note(sep):
        """sep=False → 老笔记的紧凑配对；sep=True → 新笔记的空行分隔。区间一律现场算，不手抄。"""
        doc = al_doc()
        rngs = [(doc.index(q), doc.index(q) + len(q)) for q in (D1_Q, D2_Q, D3_Q)]
        lines = ["---", "title: 定位符配对形状篇", "flow: 测试流", "stage: 3_搭建与开发",
                 "substage: 子技巧", "domains: [AI]", "forms: [文章]", "tools: []", "types: [方法]",
                 "projects: []", "topics: [配对形状]", "q_hooks:",
                 "  - 紧凑排的引用会不会被漏解析", "  - 空行分隔的引用解析结果一样吗",
                 "  - 老笔记那种写法还能逐条复核吗",
                 "sources:", "  - x/y.md", "source_locator:"] + \
                ["  - §%s#char=%d-%d" % (HEAD, a, b) for a, b in rngs] + \
                ["confidence: high", "status: draft", "---", "", "# 定位符配对形状篇", "",
                 "## 资料原话（evidence.quote）", ""]
        for q, (a, b) in zip((D1_Q, D2_Q, D3_Q), rngs):
            if sep:
                lines += [""]
            lines += ["> %s" % q, "> —— `§%s#char=%d-%d`" % (HEAD, a, b)]
        lines += ["", "## 归纳结论", "", "- 三条原话各指一件事，逐条可回放。", "",
                  "## AI 推断（inference）", "", "- 作者未提、我的推论：本组只验解析形状，不验内容。", ""]
        return "\n".join(lines), rngs

    def al_build(tag):
        kb = os.path.join(WORK, tag, "kb")
        src = os.path.join(WORK, tag, "src")
        stage = os.path.join(kb, "工作流", "测试流", "3_搭建与开发")
        for d in (os.path.join(kb, "_meta"), os.path.join(src, "x"), stage):
            os.makedirs(d, exist_ok=True)
        w(os.path.join(src, "x", "y.md"), al_doc())
        quiet("doc_map.py", ["--source-root", src, "--out", os.path.join(kb, "_meta", "doc_maps.jsonl")])
        for stem, sep in (("紧凑配对篇.md", False), ("空行分隔篇.md", True)):
            text, _ = al_note(sep)
            w(os.path.join(stage, stem), text)
        return kb, src, stage

    def quiet(script, args):
        p = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)] + args,
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=SCRIPTS))
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    kb, src, stage = al_build("p12_al")
    AL = os.path.join(SCRIPTS, "autolocate.py")

    def chk(note_path, script=AL):
        p = subprocess.run([sys.executable, script, "--check", note_path, "--source-root", src,
                            "--doc-maps", os.path.join(kb, "_meta", "doc_maps.jsonl")],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=SCRIPTS))
        ROWS.append(("P12-al %s (%s)" % (os.path.basename(note_path)[:12],
                                        os.path.basename(script)[:12]), "RAN", p.returncode, ""))
        return p.returncode, (p.stdout or "") + (p.stderr or "")

    rcA, oA = chk(os.path.join(stage, "紧凑配对篇.md"))
    rcB, oB = chk(os.path.join(stage, "空行分隔篇.md"))
    n_ev = lambda s: tuple(re.findall(r"evidence (\d+) 条复算通过 (\d+)", s)[0]) if re.findall(
        r"evidence (\d+) 条复算通过 (\d+)", s) else ("0", "0")

    # 负控：把"往上收时遇引用行即停"摘掉的旧解析副本
    cur = _io.open(AL, encoding="utf-8").read()
    anchor = 'while j >= 0 and lines[j].startswith("> ") and not CIT.match(lines[j]):'
    if anchor not in cur:
        raise SystemExit("[P12-al] parse_note 的停止锚点没找到——实现被改了而负控没跟着改")
    old = cur.replace(anchor, 'while j >= 0 and lines[j].startswith("> "):', 1)
    p_old = os.path.join(WORK, "p12_al", "autolocate_oldparse.py")
    w(p_old, old)
    rcA2, oA2 = chk(os.path.join(stage, "紧凑配对篇.md"), p_old)
    rcB2, oB2 = chk(os.path.join(stage, "空行分隔篇.md"), p_old)
    nA, nB, nA2 = int(n_ev(oA)[0]), int(n_ev(oB)[0]), int(n_ev(oA2)[0])
    pA2 = int(n_ev(oA2)[1])                      # 旧副本下"复算通过"的条数
    cite = {}
    for stem in ("紧凑配对篇.md", "空行分隔篇.md"):
        t = _io.open(os.path.join(stage, stem), encoding="utf-8").read()
        cite[stem] = len([l for l in t.splitlines() if l.startswith("> —— `§")])

    check("P12-al① 两种 evidence 配对形状必须同判据：**紧凑**（一行 quote 紧接一行引用、不空行，"
          "老笔记写法）与**空行分隔**（新笔记写法）跑 `--check` 都要 3/3 复算通过、rc=0。"
          "**负控**＝摘掉『往上收时遇上一条引用行即停』的旧解析副本：紧凑篇**必须转红**，"
          "且红在「复算」而不是「条数」——条目数仍是 3，复算通过由 3 掉到 **1**"
          "（第一条没问题，第 2 条起把上一条的 `—— §…#char=` 当成正文吞掉）；"
          "而空行篇在旧副本下**仍应 3/3 通过**，证明红的是配对形状，不是整条链路坏了",
          rcA == 0 and rcB == 0 and n_ev(oA) == ("3", "3") and n_ev(oB) == ("3", "3")
          and rcA2 != 0 and nA2 == 3 and pA2 < 3 and rcB2 == 0,
          "紧凑 rc=%s %d/%d｜空行 rc=%s %d/%d‖旧副本：紧凑 rc=%s 条数 %d 通过 %d｜旧副本：空行 rc=%s" % (
              rcA, nA, nA, rcB, nB, nB, rcA2, nA2, pA2, rcB2))

    check("P12-al② 引用行数与解析条数相等（防漏配／多配）：两篇笔记**文件里**以 `> —— \\`§` 开头的"
          "引用行数（各 3 行）必须等于各自 `--check` 报出的 evidence 条数；旧副本下条数同样相等"
          "（它没丢条目，丢的是复算）——这条专钉「解析器不静默漏配」。"
          "踩过的坑：拿 `--check` 的输出去数引用行会得到 0，因为 `--check` 不回显原文行，"
          "所以行数必须数笔记文件本身",
          cite["紧凑配对篇.md"] == cite["空行分隔篇.md"] == 3 and nA == 3 and nB == 3 and nA2 == 3,
          "行数 紧凑=%d 空行=%d‖报出条数 新=%d/%d 旧副本=%d" % (
              cite["紧凑配对篇.md"], cite["空行分隔篇.md"], nA, nB, nA2))


def main():
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK, exist_ok=True)

    # ---------- P1 骨架渲染 + verify（含模板改动回归） ----------
    kb1, cfg1 = build_base("p1_skeleton")
    tpl = os.path.join(kb1, "_meta", "模板", "note_atomic.template.md")
    tpl_txt = open(tpl, encoding="utf-8").read() if os.path.isfile(tpl) else ""
    check("原子笔记模板不再预留 `- [[相关笔记]]` 占位行",
          os.path.isfile(tpl) and not re.search(r"^\s*-\s*\[\[相关笔记\]\]", tpl_txt, flags=re.M),
          tpl_txt[-260:])
    rc, out = run([os.path.join(SCRIPTS, "verify.py"), "--kb", kb1, "--config", cfg1,
                   "--allow-empty-index"], 0, "P1 verify 骨架")

    # ---------- P2 满库 + 三篇深抽 → verify ----------
    kb2, cfg2 = build_base("p2_linked")
    add_notes(kb2)
    run([os.path.join(SCRIPTS, "check_hooks.py"), "--notes-dir", os.path.join(kb2, "工作流")],
        0, "P4 check_hooks 有链库")
    aggregates(kb2)
    rc, out = run([os.path.join(SCRIPTS, "verify.py"), "--kb", kb2, "--config", cfg2], 0,
                  "P2 verify 满库")
    c10 = c_line(out, "C10")
    print("   C10 →", c10)
    check("验收① A 正文含 [[B]]", f"[[{B_STEM}]]" in NOTE_A and
          f"[[{B_STEM}]]" in open(os.path.join(kb2, "工作流", FLOW, STAGE, A_STEM + ".md"),
                                  encoding="utf-8").read())
    check("验收③ C10 对 [[B]] 目标存在校验 PASS", c10.startswith("[PASS]"), c10)

    # ---------- 负控：链指向不存在的笔记必须仍报失效 ----------
    bad = os.path.join(kb2, "工作流", FLOW, STAGE, "坏链样本.md")
    w(bad, NOTE_C.replace("封面标题的数字承诺", "坏链样本", 1).replace(
        "标题数字必须是可验证承诺。", "标题数字必须是可验证承诺，另见[[根本不存在的一篇]]。", 1))
    rc, out = run([os.path.join(SCRIPTS, "verify.py"), "--kb", kb2, "--config", cfg2], None,
                  "负控 verify（含坏链，篇数与索引必然不一致，只看 C10）")
    c10b = c_line(out, "C10")
    print("   C10 →", c10b)
    check("负控：不存在目标仍被 C10 报失效（warn，不 fail）",
          c10b.startswith("[WARN]") and "根本不存在的一篇" in c10b, c10b)
    os.remove(bad)

    # ---------- P3 audit A1 explicit 对照 ----------
    run([os.path.join(SCRIPTS, "audit.py"), "--notes-dir", os.path.join(kb2, "工作流"),
         "--graph-mode", "explicit", "--format", "json", "--out",
         os.path.join(WORK, "audit_linked.json")], 0, "P3 audit 有链库")
    kb3, cfg3 = build_base("p3_nolink")
    add_notes(kb3)
    pa = os.path.join(kb3, "工作流", FLOW, STAGE, A_STEM + ".md")
    w(pa, NOTE_A.replace("[[" + B_STEM + "]]", B_STEM))
    aggregates(kb3)
    run([os.path.join(SCRIPTS, "audit.py"), "--notes-dir", os.path.join(kb3, "工作流"),
         "--graph-mode", "explicit", "--format", "json", "--out",
         os.path.join(WORK, "audit_nolink.json")], 0, "P3 audit 无链库")
    # 无链库里的 C 同样不加链
    run([os.path.join(SCRIPTS, "audit.py"), "--notes-dir", os.path.join(kb3, "工作流"),
         "--format", "markdown"], 0, "P3 audit 无链库（markdown 全量）")

    def ex(path):
        d = json.load(open(path, encoding="utf-8"))
        e = d["A1_relation_connectivity"]["explicit"]
        e["notes_total"] = d["notes_total"]
        return e

    L, N = ex(os.path.join(WORK, "audit_linked.json")), ex(os.path.join(WORK, "audit_nolink.json"))
    print("   有链库 explicit:", L["edges"], L["edges_by_source"], "孤岛", L["isolated_count"])
    print("   无链库 explicit:", N["edges"], N["edges_by_source"], "孤岛", N["isolated_count"])
    check("验收④ 有链 → A1 explicit 边数 > 0", L["edges"] > 0, str(L["edges_by_source"]))
    check("验收④ 无链 → A1 explicit 边数 = 0 且不报错", N["edges"] == 0, str(N["edges_by_source"]))
    check("验收② C 与 A/B 同 topic 仍为孤岛（无链库 3 篇全孤岛）",
          N["isolated_count"] == N["notes_total"] == 3,
          f"isolated={N['isolated_count']} notes={N['notes_total']}")
    p3 = [r for r in ROWS if r[0].startswith("P3 audit")]
    check("验收④ audit 三次调用均 exit 0", all(r[2] == 0 for r in p3),
          str([(r[0], r[2]) for r in p3]))

    # ---------- 验收②：C 不加链、audit 不报警 ----------
    ctext = open(os.path.join(kb2, "工作流", FLOW, STAGE, C_STEM + ".md"), encoding="utf-8").read()
    check("验收② C 正文不含任何 [[ ]]", "[[" not in ctext)
    check("验收② C 在孤岛列表中（有链库）",
          any(C_STEM in x for x in L["isolated"]), str(L["isolated"]))

    # ---------- P5 recall 有链 / 无链一致 ----------
    q = "爆款拆解怎么对照选品象限"
    _, o1 = run([os.path.join(SCRIPTS, "search_index.py"), "recall", "--kb", kb2,
                 "--query", q], 0, "P5 recall 有链库")
    _, o2 = run([os.path.join(SCRIPTS, "search_index.py"), "recall", "--kb", kb3,
                 "--query", q], 0, "P5 recall 无链库")
    hit = lambda s: re.findall(r"^\s*\d+\.\s+(\S+)", s, flags=re.M)
    t = lambda s: re.findall(r"\[([a-z+]+)\]", s)
    check("P5 recall 命中集合一致", hit(o1) == hit(o2), f"{hit(o1)} vs {hit(o2)}")
    check("P5 recall 通道标记一致", t(o1) == t(o2), f"{t(o1)} vs {t(o2)}")

    # ---------- P4 check_hooks 无链库 + 骨架库 ----------
    run([os.path.join(SCRIPTS, "check_hooks.py"), "--notes-dir", os.path.join(kb3, "工作流")],
        0, "P4 check_hooks 无链库")

    # ---------- P6 路由 JSON 契约（原因码 / 落盘 / flow×stage 交叉校验） ----------
    p6_route()

    # ---------- P7 C14 源目录只读校验 ----------
    p7_snapshot()

    # ---------- P8 输入/退出码守卫 + C5/C9/C15/C14 工单 ----------
    p8_validation_gates()

    # ---------- P9 units-off 逐字替身 + hook 阈值 + C10 目标范围 ----------
    p9_verbatim_and_gates()

    # ---------- P10 进度派生器（三档计数 / next_todo / 作废字段负控 / 两类不一致 / 只读） ----------
    p10_progress()

    # ---------- P11 progress --gate（默认关的显式门禁） ----------
    p11_gate()

    # ---------- P12 结构适配（A8 编码 + A2/A3 目录 + A4 源类型 + A1 语言） ----------
    p12_enc()
    p12_dir()
    p12_src()
    p12_lang()
    p12_fb()
    p12_sb()
    p12_agg()
    p12_al()

    print("=" * 78)
    fails = 0
    for name, status, rc, out in ROWS:
        if status in ("OK", "RC", "RAN"):
            print(f"  {status:<4} {name}  rc={rc}")
        else:
            fails += 1
            print(f"  {status:<4} {name}  rc={rc}")
            print("        " + (out or "")[:800].replace("\n", "\n        "))
    print("=" * 78)
    print(f"共 {len(ROWS)} 项，失败 {fails}；工作目录：{WORK}")
    raise SystemExit(1 if fails else 0)


if __name__ == "__main__":
    main()
