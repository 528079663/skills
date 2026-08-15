#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""renshe-writer Web 管理服务（端口 8003，默认常驻）。

启动策略（方案 b，经中间确认裁决）：
- 激活即后台常驻（python app.py start）。
- 启动前 socket 探测 127.0.0.1:8003：
  * 外部程序占用 -> 明确报错、sys.exit(非0)、不静默降级、不自动换端口；
  * 本应用历史实例（pid 文件指向的进程命令行确属 renshe-writer/scripts/app.py）
    -> 精准 SIGTERM 后自动重启，用户无感。
- 提供 stop（python app.py stop）写 pid 文件 + SIGTERM 优雅退出。
- 仅绑 127.0.0.1，不启 TLS、无登录态（本地单用户）。
"""

import argparse
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import persona_manager as pm  # noqa: E402

try:
    from flask import Flask, request, jsonify, send_file  # noqa: E402
except ImportError:
    sys.stderr.write("缺少依赖 flask，请先安装：pip install flask\n")
    sys.exit(2)

import platform  # noqa: E402
import preprocess_html as ph  # noqa: E402

HOST = "127.0.0.1"
PORT = 8003
PID_FILE = os.path.join(HERE, ".webui.pid")
LOG_FILE = os.path.join(HERE, "webui.log")

app = Flask(__name__)


def _store():
    return os.environ.get("RENHE_WRITER_STORE", pm.DEFAULT_STORE)


# ---------- 进程 / 端口工具 ----------

def _read_pid():
    try:
        with open(PID_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return None


def _remove_pid():
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def _cmdline_of(pid):
    try:
        if platform.system() == "Windows":
            out = subprocess.run(
                ["wmic", "process", "where", "processid=%d" % pid,
                 "get", "commandline", "/value"],
                capture_output=True, text=True, timeout=5).stdout
            return out
        with open("/proc/%d/cmdline" % pid, "rb") as f:
            return f.read().decode("utf-8", "ignore")
    except Exception:
        return ""


def _is_our_instance(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    cmd = _cmdline_of(pid).lower()
    return "renshe-writer" in cmd and "app.py" in cmd


def _kill(pid):
    if platform.system() == "Windows":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def _port_free():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((HOST, PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _launch_serve():
    log = open(LOG_FILE, "a", encoding="utf-8")
    if platform.system() == "Windows":
        p = subprocess.Popen(
            [sys.executable, __file__, "serve"],
            stdout=log, stderr=log,
            creationflags=0x00000008)  # DETACHED_PROCESS
    else:
        p = subprocess.Popen(
            [sys.executable, __file__, "serve"],
            stdout=log, stderr=log, start_new_session=True)
    with open(PID_FILE, "w") as f:
        f.write(str(p.pid))
    return p.pid


# ---------- CLI 子命令 ----------

def cmd_start(args):
    pid = _read_pid()
    if pid and _is_our_instance(pid):
        _kill(pid)
        time.sleep(1)
        _remove_pid()
    if not _port_free():
        sys.stderr.write(
            "8003 已被外部程序占用，请释放冲突进程后再启动 Web 管理端"
            "（CLI/agent 入口不受影响）。\n")
        sys.exit(3)
    new_pid = _launch_serve()
    print("renshe-writer Web 管理端已启动：http://localhost:8003  (pid=%d)" % new_pid)


def cmd_stop(args):
    pid = _read_pid()
    if not pid or not _is_our_instance(pid):
        print("Web 管理端未运行或 pid 文件缺失。")
        _remove_pid()
        return
    _kill(pid)
    time.sleep(1)
    _remove_pid()
    print("Web 管理端已停止。")


def cmd_serve(args):
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


# ---------- 业务辅助（复用 persona_manager） ----------

def _add_persona(payload):
    name = payload.get("name")
    profile = payload.get("profile")
    if not name or not isinstance(profile, dict):
        return None, "payload 必须包含 name 与 profile 字段"
    data = pm.load_store(_store())
    pid = pm.make_id(data.get("personas", []))
    now = pm._now()
    persona = {
        "id": pid, "name": name, "created_at": now, "updated_at": now,
        "source_articles": payload.get("source_articles", []),
        "profile": profile,
    }
    data.setdefault("personas", []).append(persona)
    pm.save_store(_store(), data)
    return persona, None


def _update_persona(key, patch):
    data = pm.load_store(_store())
    p = pm.find_persona(data.get("personas", []), key)
    if not p:
        return None, "未找到人设：%s" % key
    top = {k: v for k, v in patch.items() if k != "profile"}
    pm.deep_merge(p, top)
    if isinstance(patch.get("profile"), dict):
        pm.deep_merge(p["profile"], patch["profile"])
    p["updated_at"] = pm._now()
    pm.save_store(_store(), data)
    return p, None


def _delete_persona(key):
    data = pm.load_store(_store())
    personas = data.get("personas", [])
    idx = next((i for i, x in enumerate(personas)
                if x.get("id") == key or x.get("name") == key), None)
    if idx is None:
        return None, "未找到人设：%s" % key
    removed = personas.pop(idx)
    pm.save_store(_store(), data)
    return removed, None


# ---------- 路由 ----------

@app.route("/")
def index():
    return send_file(os.path.join(HERE, "webui.html"))


@app.route("/health")
def health():
    return jsonify({"status": "ok", "port": PORT, "store": _store()})


@app.route("/api/v1/personas", methods=["GET"])
def list_personas():
    data = pm.load_store(_store())
    personas = data.get("personas", [])
    return jsonify([{**p, "author_mapping": pm.resolve_author_mapping(p)} for p in personas])


@app.route("/api/v1/personas/<key>", methods=["GET"])
def view_persona(key):
    data = pm.load_store(_store())
    p = pm.find_persona(data.get("personas", []), key)
    if not p:
        return jsonify({"code": "A010001", "msg": "人设不存在"}), 200
    return jsonify({**p, "author_mapping": pm.resolve_author_mapping(p)})


@app.route("/api/v1/personas", methods=["POST"])
def add_persona():
    payload = request.get_json(force=True, silent=True) or {}
    persona, err = _add_persona(payload)
    if err:
        return jsonify({"code": "A010003", "msg": err}), 200
    return jsonify(persona), 200


@app.route("/api/v1/personas/<key>", methods=["PATCH"])
def update_persona(key):
    patch = request.get_json(force=True, silent=True) or {}
    persona, err = _update_persona(key, patch)
    if err:
        return jsonify({"code": "A010001", "msg": err}), 200
    return jsonify(persona), 200


@app.route("/api/v1/personas/<key>", methods=["DELETE"])
def delete_persona(key):
    removed, err = _delete_persona(key)
    if err:
        return jsonify({"code": "A010001", "msg": err}), 200
    return jsonify({"code": "A000000", "msg": "已删除：%s" % removed.get("name")}), 200


@app.route("/api/v1/preprocess", methods=["POST"])
def preprocess():
    body = request.get_json(force=True, silent=True) or {}
    html_path = body.get("html_path")
    url = body.get("url")
    svc = body.get("svc")
    try:
        if url:
            html = ph._read_html(url, True)
        elif html_path:
            html = ph._read_html(html_path, False)
        else:
            return jsonify({"code": "C400001", "msg": "需提供 html_path 或 url"}), 400
    except Exception as e:
        return jsonify({"code": "A020002", "msg": "读取 HTML 失败：%s" % e}), 200
    material, err = ph.preprocess(html, svc=svc)
    if err:
        return jsonify({"code": "A020001", "msg": err}), 200
    return jsonify({"material": material}), 200


def main():
    ap = argparse.ArgumentParser(description="renshe-writer Web 管理服务 (端口 8003)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("start").set_defaults(func=cmd_start)
    sub.add_parser("stop").set_defaults(func=cmd_stop)
    sub.add_parser("serve").set_defaults(func=cmd_serve)
    args = ap.parse_args()
    if not getattr(args, "cmd", None):
        ap.print_help()
        sys.exit(1)
    args.func(args)


if __name__ == "__main__":
    main()
