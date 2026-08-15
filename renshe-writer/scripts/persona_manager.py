#!/usr/bin/env python3
"""Persona manager for the renshe-writer skill.

Stores writing personas (identity + style profiles) as JSON and provides
CRUD operations: list, view, add, update, rename, delete, export, path.
"""
import argparse
import json
import os
import sys
from datetime import datetime

DEFAULT_STORE = os.path.expanduser("~/.workbuddy/personas/personas.json")


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_store(store_path):
    if not os.path.exists(store_path):
        return {"personas": []}
    try:
        with open(store_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "personas" not in data:
            data = {"personas": []}
        return data
    except (json.JSONDecodeError, OSError):
        return {"personas": []}


def save_store(store_path, data):
    os.makedirs(os.path.dirname(store_path), exist_ok=True)
    with open(store_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def deep_merge(base, patch):
    """Recursively merge patch into base (patch wins on conflicts)."""
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def make_id(existing):
    date = datetime.now().strftime("%Y%m%d")
    seq = 1
    ids = {p.get("id") for p in existing}
    while f"p_{date}_{seq:03d}" in ids:
        seq += 1
    return f"p_{date}_{seq:03d}"


def summary_of(p):
    prof = p.get("profile", {})
    role = (prof.get("identity") or {}).get("role") or ""
    tone = (prof.get("style") or {}).get("tone") or ""
    parts = [x for x in [role, tone] if x]
    return " · ".join(parts) if parts else "（信息待补全）"


def find_persona(personas, key):
    return next((x for x in personas if x.get("id") == key or x.get("name") == key), None)


# 领域 → 默认人设 id 路由（单一事实来源；新增/调整默认人设请改此表）
DEFAULT_PERSONA_BY_DOMAIN = {
    "母婴": "p_20260707_001",  # 福宝妈·温柔坚定育儿
}


def get_default_by_domain(domain):
    """按选题领域返回默认人设 id；未列出的域返回 None（由调用方指定或 AskUserQuestion 确认）。"""
    if not domain:
        return None
    return DEFAULT_PERSONA_BY_DOMAIN.get(domain)


def load_ip_identity():
    """读取 references/ip_identity.json —— 成文身份单一事实来源。"""
    path = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "references", "ip_identity.json"))
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("ip_identities", {})
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_author_mapping(p, ip_identities=None):
    """将 author_mapping 中的 ip_key 引用解析为完整身份块。

    - 无 ip_key 的人设（非母婴 / 已写死字面量）原样返回，不受影响；
    - ip_key 解析失败时保留原样（含 ip_key），不做静默编造，便于排查。
    """
    am = p.get("author_mapping") if isinstance(p, dict) else None
    if not isinstance(am, dict):
        return am
    ip_key = am.get("ip_key")
    if not ip_key:
        return am
    if ip_identities is None:
        ip_identities = load_ip_identity()
    block = ip_identities.get(ip_key)
    if not isinstance(block, dict):
        return am
    resolved = dict(block)
    resolved["ip_key"] = ip_key
    return resolved


def cmd_list(args):
    data = load_store(args.store)
    personas = data.get("personas", [])
    if args.json:
        print(json.dumps(personas, ensure_ascii=False, indent=2))
        return
    if not personas:
        print("（暂无已保存的人设）")
        return
    print(f"已保存 {len(personas)} 个人设：\n")
    for i, p in enumerate(personas, 1):
        dom = p.get("domain")
        head = f"{i}. [{dom}] [{p.get('id')}] {p.get('name')}" if dom else f"{i}. [{p.get('id')}] {p.get('name')}"
        print(head)
        print(f"   {summary_of(p)}")
        print(f"   更新于 {p.get('updated_at', '-')}")
        print()


def cmd_view(args):
    data = load_store(args.store)
    p = find_persona(data.get("personas", []), args.id)
    if not p:
        print(f"未找到人设：{args.id}", file=sys.stderr)
        sys.exit(1)
    if args.json:
        out = dict(p)
        out["author_mapping"] = resolve_author_mapping(out)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    print(f"人设：{p.get('name')}  (id: {p.get('id')})")
    print(f"创建：{p.get('created_at', '-')}   更新：{p.get('updated_at', '-')}")
    if p.get("domain"):
        print(f"领域：{p.get('domain')}")
    am = resolve_author_mapping(p)
    if am:
        ip_note = f" | ip_key={am.get('ip_key')}" if am.get("ip_key") else ""
        print(f"成文映射：resolved={am.get('resolved')} | 署名={am.get('sign_name')} | 落款={am.get('signoff')} | 自称={am.get('self_refer')} | 宝宝名={am.get('baby_name')}{ip_note}")
    if p.get("source_articles"):
        print(f"来源文章：{', '.join(p['source_articles'])}")
    print("\n--- 人设档案 ---")
    print(json.dumps(p.get("profile", {}), ensure_ascii=False, indent=2))


def cmd_add(args):
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            payload = json.load(f)
    elif args.data:
        payload = json.loads(args.data)
    else:
        print("add 需要 --data 或 --file", file=sys.stderr)
        sys.exit(1)
    name = payload.get("name")
    profile = payload.get("profile")
    if not name or not isinstance(profile, dict):
        print("payload 必须包含 name 与 profile 字段", file=sys.stderr)
        sys.exit(1)
    data = load_store(args.store)
    pid = make_id(data.get("personas", []))
    now = _now()
    persona = {
        "id": pid,
        "name": name,
        "created_at": now,
        "updated_at": now,
        "source_articles": payload.get("source_articles", []),
        "profile": profile,
    }
    # 透传领域与成文映射等顶层字段（不写死，便于扩展）
    for k in ("domain", "author_mapping"):
        if k in payload:
            persona[k] = payload[k]
    data.setdefault("personas", []).append(persona)
    save_store(args.store, data)
    print(f"已添加人设：{name} (id: {pid})")


def cmd_update(args):
    if args.patch:
        patch = json.loads(args.patch)
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            patch = json.load(f)
    else:
        print("update 需要 --patch 或 --file", file=sys.stderr)
        sys.exit(1)
    data = load_store(args.store)
    p = find_persona(data.get("personas", []), args.id)
    if not p:
        print(f"未找到人设：{args.id}", file=sys.stderr)
        sys.exit(1)
    top = {k: v for k, v in patch.items() if k != "profile"}
    deep_merge(p, top)
    if "profile" in patch and isinstance(patch["profile"], dict):
        deep_merge(p["profile"], patch["profile"])
    p["updated_at"] = _now()
    save_store(args.store, data)
    print(f"已更新人设：{p.get('name')} (id: {p.get('id')})")


def cmd_rename(args):
    data = load_store(args.store)
    p = find_persona(data.get("personas", []), args.id)
    if not p:
        print(f"未找到人设：{args.id}", file=sys.stderr)
        sys.exit(1)
    old = p.get("name")
    p["name"] = args.name
    p["updated_at"] = _now()
    save_store(args.store, data)
    print(f"已重命名人设：{old} -> {args.name}")


def cmd_delete(args):
    data = load_store(args.store)
    personas = data.get("personas", [])
    idx = next((i for i, x in enumerate(personas) if x.get("id") == args.id or x.get("name") == args.id), None)
    if idx is None:
        print(f"未找到人设：{args.id}", file=sys.stderr)
        sys.exit(1)
    removed = personas.pop(idx)
    save_store(args.store, data)
    print(f"已删除人设：{removed.get('name')} (id: {removed.get('id')})")


def cmd_export(args):
    data = load_store(args.store)
    p = find_persona(data.get("personas", []), args.id)
    if not p:
        print(f"未找到人设：{args.id}", file=sys.stderr)
        sys.exit(1)
    out = dict(p)
    out["author_mapping"] = resolve_author_mapping(out)
    with open(args.file, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"已导出人设到：{args.file}")


def cmd_path(args):
    print(args.store)


def cmd_default(args):
    pid = get_default_by_domain(args.domain)
    if not pid:
        print(f"领域「{args.domain}」暂无默认人设，需调用方指定或用 AskUserQuestion 确认", file=sys.stderr)
        sys.exit(1)
    p = find_persona(load_store(args.store).get("personas", []), pid)
    if not p:
        print(f"默认人设 {pid} 不存在于人设库", file=sys.stderr)
        sys.exit(1)
    if args.json:
        out = dict(p)
        out["author_mapping"] = resolve_author_mapping(out)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(pid)


def build_parser():
    parser = argparse.ArgumentParser(description="renshe-writer 人设管理器")
    parser.add_argument(
        "--store",
        default=DEFAULT_STORE,
        help="人设存储 JSON 路径（默认 ~/.workbuddy/personas/personas.json）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出所有人设")
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_view = sub.add_parser("view", help="查看某个人设详情")
    p_view.add_argument("id", help="人设 id 或名称")
    p_view.add_argument("--json", action="store_true")
    p_view.set_defaults(func=cmd_view)

    p_add = sub.add_parser("add", help="新增人设")
    p_add.add_argument("--data", help="JSON 字符串，含 name 与 profile")
    p_add.add_argument("--file", help="包含 name 与 profile 的 JSON 文件")
    p_add.set_defaults(func=cmd_add)

    p_upd = sub.add_parser("update", help="更新人设（合并补丁）")
    p_upd.add_argument("id", help="人设 id 或名称")
    p_upd.add_argument("--patch", help="JSON 字符串补丁")
    p_upd.add_argument("--file", help="JSON 补丁文件")
    p_upd.set_defaults(func=cmd_update)

    p_ren = sub.add_parser("rename", help="重命名人设")
    p_ren.add_argument("id", help="人设 id 或名称")
    p_ren.add_argument("name", help="新名称")
    p_ren.set_defaults(func=cmd_rename)

    p_del = sub.add_parser("delete", help="删除人设")
    p_del.add_argument("id", help="人设 id 或名称")
    p_del.set_defaults(func=cmd_delete)

    p_exp = sub.add_parser("export", help="导出人设为 JSON 文件")
    p_exp.add_argument("id", help="人设 id 或名称")
    p_exp.add_argument("file", help="输出文件路径")
    p_exp.set_defaults(func=cmd_export)

    p_path = sub.add_parser("path", help="打印存储路径")
    p_path.set_defaults(func=cmd_path)

    p_def = sub.add_parser("default", help="按领域取默认人设 id")
    p_def.add_argument("domain", help="领域标签（如 母婴）")
    p_def.add_argument("--json", action="store_true")
    p_def.set_defaults(func=cmd_default)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
