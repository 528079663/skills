#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
topic_log.py — 同人设「已写主题 / 角度」登记工具

支撑 renshe-writer「同主题再创作差异化门禁」：
- 把同一人设写过的 主题 / 角度 / 核心论点 持久化到 JSON，
  替代原来"或会话记忆"的漏洞（易丢、不可查、可糊弄）。
- 创作前 `check` 查已用角度，强制本次换不同内容组织轴。

命令：
  record <persona_id> --topic <规范化主题> --angle <内容角度> [--thesis <核心论点>] [--title <标题>]
  list   <persona_id>
  check  <persona_id> --topic <规范化主题>

stdlib only，无外部依赖。
"""
import argparse
import json
import os
import sys
from datetime import datetime

DEFAULT_STORE = os.path.join(
    os.path.expanduser("~"), ".workbuddy", "personas", "topic_log.json"
)


def load(store):
    if not os.path.exists(store):
        return {}
    try:
        with open(store, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save(store, data):
    os.makedirs(os.path.dirname(store), exist_ok=True)
    with open(store, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def cmd_record(args, store):
    if not args.topic or not args.angle:
        print("record 需要 --topic 与 --angle")
        sys.exit(2)
    data = load(store)
    rec = {
        "topic": args.topic,
        "angle": args.angle,
        "thesis": args.thesis or "",
        "title": args.title or "",
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    data.setdefault(args.persona, []).append(rec)
    save(store, data)
    print("OK: 已登记 [%s] 主题=%s 角度=%s" % (args.persona, args.topic, args.angle))


def cmd_list(args, store):
    data = load(store)
    recs = data.get(args.persona, [])
    if not recs:
        print("[%s] 暂无已写主题记录" % args.persona)
        return
    for i, r in enumerate(recs, 1):
        print("%d. 主题=%s | 角度=%s | 标题=%s | %s"
              % (i, r.get("topic"), r.get("angle"), r.get("title"), r.get("ts")))


def cmd_check(args, store):
    if not args.topic:
        print("check 需要 --topic")
        sys.exit(2)
    data = load(store)
    recs = [r for r in data.get(args.persona, []) if r.get("topic") == args.topic]
    if not recs:
        print("OK: [%s] 主题「%s」尚无记录，可直接创作（仍需满足三新）"
              % (args.persona, args.topic))
        return
    print("CONFLICT: [%s] 主题「%s」已用过以下角度，本次【必须】换不同内容组织轴："
          % (args.persona, args.topic))
    for i, r in enumerate(recs, 1):
        print("  %d. 角度=%s | 标题=%s | 论点=%s"
              % (i, r.get("angle"), r.get("title"), r.get("thesis")))


def main():
    p = argparse.ArgumentParser(description="同人设已写主题/角度登记")
    p.add_argument("action", choices=["record", "list", "check"])
    p.add_argument("persona")
    p.add_argument("--topic")
    p.add_argument("--angle")
    p.add_argument("--thesis")
    p.add_argument("--title")
    p.add_argument("--store", default=DEFAULT_STORE)
    args = p.parse_args()

    if args.action == "record":
        cmd_record(args, args.store)
    elif args.action == "list":
        cmd_list(args, args.store)
    elif args.action == "check":
        cmd_check(args, args.store)


if __name__ == "__main__":
    main()
