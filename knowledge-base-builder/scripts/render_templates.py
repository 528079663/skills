#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render_templates.py — config.json + assets/templates → 目标知识库骨架。

职责（对应 SKILL.md Step 5 与 references/04_pipeline.md 第 5 节）：
  - 仅创建 config 中 create=true 的目录；
  - 渲染 README/AGENTS/问题资产库；复制笔记模板（保留槽位原样）；
  - 为无模板文件生成最小可用骨架。
默认不覆盖已存在文件（--force 才覆盖），保护用户已有内容。
"""
import argparse
import json
import os
import re
import sys
from datetime import date

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # A8：GBK 控制台不炸（Python 3.7+）
sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # 提示/报错文案走 stderr，同样要包

ARCH_CN = {"learn": "学习型", "create": "创作型", "project": "项目型"}

ACTION_CN = {
    "new_note": "新建笔记", "fix_format": "格式规整", "add_tags": "补标签",
    "build_index": "构建检索索引", "move_in_inbox": "收件箱内移动",
    "batch_20plus": "批量(≥20)操作", "edit_source": "改源资料",
    "delete": "删除文件", "rename_topic": "重命名主题", "write_rules": "改规则文件",
}
PRIVACY_CN = {"income": "收入等个人数字不写入笔记",
              "accounts": "账号链接 / token 不入库",
              "internal": "内部手册不入库，整库标记私有"}
OUTPUT_CN = {"local": "本地 Obsidian/编辑器（md + wikilink）",
             "feishu": "飞书（标题层级≤3，表格规整）",
             "notion_pub": "公众号/Notion（开头给结论，引用≤5 段）",
             "rag": "RAG（结论原子化，每段≤300 字，tags 完整）"}
UNSORTED_CN = {
    "suggest_table": "先生成待分拣索引 / 归桶建议表，你审完再移动（移动走 L2）",
    "skip": "未归桶资料暂不处理",
    "handpick": "仅处理你圈定的篇目",
}
FLOW_CN = {
    "learn": "源资料(只读) → 高价值块原子笔记 → 工作流/<flow>/<stage>/ → 00_导航/主题地图",
    "create": "源资料(只读) → 高价值块原子笔记 → 工作流/<flow>/<stage>/ → 概念索引 → 输出",
    "project": "源资料(只读) → 高价值块原子笔记 → 工作流/<flow>/<stage>/ → projects/<项目>/recipe 拉取",
}
PURPOSE_FALLBACK = {
    "learn": "系统学习并形成可检索的知识地图",
    "create": "做内容时快速调出案例、提示词与素材",
    "project": "推进具体项目并沉淀可复用方法",
}

# 无模板文件的初始骨架
SEED_CONTENT = {
    "00_导航/文件目录.md": "# 文件目录\n\n> 源资料文件索引（相对路径），由扫描生成/重建；本文件可直接重建。\n\n| 路径 | 类型 | 备注 |\n|---|---|---|\n",
    "00_导航/模块视图.md": "# 模块视图\n\n> 模块 = 工作流/环节视图（物理目录）。下列为常用入口，结果由检索脚本实时生成。\n\n## 工作流\n- 全部：`search --flow <工作流名>`\n- 某环节：`search --flow <工作流名> --stage <环节名>`\n- 某子分组：`search --flow <工作流名> --stage <环节名> --substage 子技巧`\n\n## 跨工作流（辅助标签）\n- 按主题：`search --topics <主题>`\n- 按关键词：`search --query \"...\"`\n\n> 项目配方见 `projects/<项目>/recipe.yaml`，用 `pull` 一键拉取。\n",
    "00_导航/学习路径.md": "# 学习路径\n\n> 由学习目标反推的阶段顺序；每阶段列资料与掌握标准。\n\n## 阶段 1\n- 资料：\n- 掌握标准：\n",
    "00_导航/素材地图.md": "# 素材地图\n\n> 按选题组织的素材索引（案例/数据/金句/链接）。\n\n",
    "00_导航/主题地图.md": "# 主题地图\n\n> 内容主题（区别于六维属性标签：标签决定在哪个模块/项目被拉到，主题决定跨文档怎么聚合）。\n> 打标后运行 `build_topics.py` 自动生成本文件与 `_meta/topics.json`。\n\n（待 build_topics 生成）\n",
    "_meta/生成日志.md": "# 生成日志\n\n| 时间 | 动作 | 结果 |\n|---|---|---|\n",
    "概念索引/_说明.md": "# 概念索引\n\n> units 产物入口（开 units 时）。\n>\n> - `_meta/units.jsonl`：结构化知识单元（claim/concept/relation/procedure/qa/open_question/conflict）\n> - `_meta/units_index.json`：聚合索引（按类型/主题/置信度）\n> - 查询：`search_index.py units --type ... --confidence ... --status ...`\n>\n> 未开 units 时本目录为空，属正常。\n",
}


def load(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def render_rules(rules):
    lines = ["| 动作 | 许可档 |", "|---|---|"]
    for k, v in rules.items():
        lines.append(f"| {ACTION_CN.get(k, k)} | {v} |")
    return "\n".join(lines)


def directory_tree(config):
    paths = sorted(d["path"] for d in config["directories"] if d["create"])
    tree = {}
    for p in paths:
        node = tree
        for part in p.split("/"):
            node = node.setdefault(part, {})

    lines = []

    def walk(node, prefix=""):
        items = sorted(node)
        for i, name in enumerate(items):
            last = i == len(items) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{name}/")
            walk(node[name], prefix + ("    " if last else "│   "))

    walk(tree)
    return "\n".join(lines)


def strip_header_comment(tpl):
    """去掉模板开头的开发说明注释块（<!-- ... -->），不改正文其它注释。"""
    tpl = tpl.lstrip("﻿")
    m = re.match(r"^\s*<!--.*?-->\s*", tpl, re.DOTALL)
    return tpl[m.end():] if m else tpl


def yaml_dump_recipe(recipe, today):
    lines = [f'project: "{recipe.get("project", "")}"', "filters:"]
    for dim in ["domains", "forms", "tools", "types", "topics"]:
        vals = recipe.get("filters", {}).get(dim, [])
        lines.append(f"  {dim}: {json.dumps(vals, ensure_ascii=False)}")
    lines.append(f'keywords: "{recipe.get("keywords", "")}"')
    lines.append(f"exclude: {json.dumps(recipe.get('exclude', []), ensure_ascii=False)}")
    lines.append(f"rank: {json.dumps(recipe.get('rank', []), ensure_ascii=False)}")
    lines.append(f"limit: {recipe.get('limit', 50)}")
    lines.append("# 可选：units 过滤（开 units 后按类型/置信/状态拉取）")
    lines.append(f"units_type: {json.dumps(recipe.get('units_type', []), ensure_ascii=False)}")
    lines.append(f"units_confidence: {json.dumps(recipe.get('units_confidence', []), ensure_ascii=False)}")
    lines.append(f"units_status: {json.dumps(recipe.get('units_status', []), ensure_ascii=False)}")
    lines.append(f"created: {today}")
    return "\n".join(lines) + "\n"


def render(template, mapping):
    out = template
    for k, v in mapping.items():
        out = out.replace("{{" + k + "}}", v)
    return out


def main():
    ap = argparse.ArgumentParser(description="渲染知识库骨架")
    ap.add_argument("--config", required=True)
    ap.add_argument("--templates", required=True, help="assets/templates 目录")
    ap.add_argument("--target", required=True, help="知识库目标目录")
    ap.add_argument("--kb-name", default=None)
    ap.add_argument("--force", action="store_true", help="覆盖已存在文件")
    args = ap.parse_args()

    config = load(args.config)
    arch = config.get("archetype", "create")
    flows = config.get("flows", [])
    kb_name = args.kb_name or "我的知识库"
    today = date.today().isoformat()

    os.makedirs(args.target, exist_ok=True)

    # 1. 目录
    made_dirs = []
    for d in config["directories"]:
        if d["create"]:
            os.makedirs(os.path.join(args.target, d["path"].replace("/", os.sep)),
                        exist_ok=True)
            made_dirs.append(d["path"])

    # 2. 变量
    privacy = config.get("privacy_exclusions") or []
    outputs = config.get("output_targets") or ["local"]
    purpose = config.get("first_task") or PURPOSE_FALLBACK[arch]
    mapping = {
        "kb_name": kb_name,
        "archetype_name": ARCH_CN[arch],
        "purpose": purpose,
        "source_root": config["source_root"],
        "directory_tree": directory_tree(config),
        "flow": FLOW_CN[arch],
        "date": today,
        "rules_table": render_rules(config["rules"]),
        "privacy_rules": "；".join(PRIVACY_CN.get(x, x) for x in privacy)
                         or "无特殊排除",
        "output_rules": "；".join(OUTPUT_CN.get(x, x) for x in outputs),
        "unsorted_rules": UNSORTED_CN.get(
            config["special_handling"]["unsorted"]["policy"], ""),
    }

    # 3. 文件
    created, skipped = [], []
    for f in config["files"]:
        target_rel = f["target"]
        template_name = f["template"]
        dest = os.path.join(args.target, target_rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)

        if os.path.exists(dest) and not args.force:
            skipped.append(target_rel)
            continue

        if template_name == "recipe.template.yaml":
            proj = next((p for p in config["projects"]
                         if p["recipe_path"] == target_rel), None)
            if proj:
                content = yaml_dump_recipe(proj["recipe"], today)
            else:
                content = (f'# 项目配方（占位）：未在 config.projects 找到匹配项\n'
                           f'project: ""\nfilters: {{}}\nexclude: []\n'
                           f'rank: []\nlimit: 50\ncreated: {today}\n')
        elif template_name:
            with open(os.path.join(args.templates, template_name),
                      "r", encoding="utf-8") as fh:
                tpl = fh.read()
            content = tpl if target_rel.startswith("_meta/模板/") \
                else render(strip_header_comment(tpl), mapping)
        else:
            content = SEED_CONTENT.get(target_rel,
                                       f"# {os.path.basename(target_rel)[:-3]}\n\n> 待补充。\n")
        with open(dest, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        created.append(target_rel)

    print(f"[render] 目录 {len(made_dirs)} 个；文件 新建={len(created)} 跳过={len(skipped)}")
    for c in created:
        print("  +", c)
    for s in skipped:
        print("  =", s, "(已存在)")
    print(f"[render] 目标：{args.target}")


if __name__ == "__main__":
    main()
