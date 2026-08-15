# -*- coding: utf-8 -*-
"""article-format 本地预览服务（零依赖，仅用标准库）。

用法：
    python serve.py [--port 8004]

提供：
    /                        预览界面 preview.html
    /api/files              列出 outputs 下所有 .html（已生成文件，含克隆/草稿产物，打 type 标记）
    /api/styles             列出 outputs/styles/*.json（样式预设）
    /api/themes            列出 references/theme.json 的可用主题（draft 模式用）
    /api/contents           列出 outputs/*.md（草稿内容）
    /api/article?file=NAME  取某篇生成 html 原文（支持子目录，用于静态预览注入）
    /api/render  (POST)     实时渲染：mode=clone（style+content）/ mode=draft（theme+content）
    /api/extract-style (POST) 给定参考文章 URL，提取样式存为 styles/<name>.json
    /<path>                 静态托管 skill 根目录

仅允许访问脚本所在根目录（及子目录），防止路径穿越。

解耦说明（系统设计 V2 / P3）：
    本服务进程**禁止 import** clone / draft 的任何内部函数。
    /api/render（clone / draft）、/api/extract-style 全部经 common/cli_bridge
    以子进程方式调用对应 CLI 完成，实现进程级解耦、防命令注入。
"""
import argparse
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))          # article-format-preview/
PROJECT_ROOT = os.path.dirname(HERE)                        # article_formate/
OUTPUTS = os.path.join(PROJECT_ROOT, "outputs")
IMAGES_DIR = os.path.join(OUTPUTS, "images")
STYLES = os.path.join(OUTPUTS, "styles")
COMMON_DIR = os.path.join(PROJECT_ROOT, "common")
CLONE_CLI = os.path.join(PROJECT_ROOT, "article-format-clone", "scripts", "clone_cli.py")
DRAFT_CLI = os.path.join(PROJECT_ROOT, "article-format-draft", "scripts", "draft_cli.py")
REF_DIR = os.path.join(PROJECT_ROOT, "references")
DISPATCH = os.path.join(REF_DIR, "theme.json")  # 主题分发器（default_theme / available）
PREVIEW_HTML = os.path.join(HERE, "preview.html")

# 注入 common，用于子进程 CLI 桥接（preview → clone / draft）
if COMMON_DIR not in sys.path:
    sys.path.insert(0, COMMON_DIR)

HAVE_CLONE = os.path.isfile(CLONE_CLI)
CLONE_ERR = "" if HAVE_CLONE else f"未找到 {CLONE_CLI}"
HAVE_DRAFT = os.path.isfile(DRAFT_CLI)
DRAFT_ERR = "" if HAVE_DRAFT else f"未找到 {DRAFT_CLI}"
try:
    import cli_bridge  # noqa: E402
except Exception as e:  # 桥接模块缺失时静态预览仍可用
    cli_bridge = None
    HAVE_CLONE = False
    CLONE_ERR = "cli_bridge 不可用：" + str(e)


def _trace_id():
    return "pv-" + uuid.uuid4().hex[:12]


# 自动重载监控的文件：任一改动即让浏览器刷新（免手动重启）。
#   - serve.py 自身改动 → 真正重启进程（释放端口后 execv）
#   - preview.html / clone_cli.py 改动 → 仅版本号刷新（clone 为子进程，下次请求自动用最新代码）
WATCH_FILES = [
    os.path.abspath(__file__),
    PREVIEW_HTML,
    CLONE_CLI,
    DRAFT_CLI,
]


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _version():
    return max(_mtime(f) for f in WATCH_FILES)


def _list_dir(folder, pattern):
    """列出 folder 下匹配 pattern（子串）的文件，按修改时间倒序。"""
    items = []
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if pattern in name and os.path.isfile(os.path.join(folder, name)):
                full = os.path.join(folder, name)
                try:
                    st = os.stat(full)
                    items.append({"name": name, "size": st.st_size, "mtime": int(st.st_mtime)})
                except OSError:
                    continue
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def list_files():
    """列出 outputs 下所有 .html（克隆 / 草稿产物），按修改时间倒序，每项带 type 标记。
    type: 文件名含 'clone' → clone，否则 draft（含其它通用 html）。
    跳过 references/archive 等归档目录；支持一层子目录（如 demo_clone/）。
    name 字段返回相对 outputs 的路径，供 /api/article 与静态访问定位。
    """
    items = []
    for root, dirs, files in os.walk(OUTPUTS):
        dirs[:] = [d for d in dirs if d != "archive"]  # 不展示归档内容
        for name in files:
            if not name.lower().endswith(".html"):
                continue
            full = os.path.join(root, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            rel = os.path.relpath(full, OUTPUTS)
            typ = "clone" if "clone" in name.lower() else "draft"
            items.append({
                "name": rel,
                "type": typ,
                "size": st.st_size,
                "mtime": int(st.st_mtime),
            })
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def list_styles():
    out = []
    for it in _list_dir(STYLES, ".json"):
        name = it["name"]
        base = name[:-5] if name.endswith(".json") else name
        out.append({"name": base, "file": name, "size": it["size"], "mtime": it["mtime"]})
    return out


def list_contents():
    return _list_dir(OUTPUTS, ".md")


def _safe_join(folder, name):
    """仅允许 folder 下的纯文件名，禁止穿越。返回绝对路径或 None。"""
    base = os.path.basename(name)
    if not base or base != name:
        return None
    full = os.path.normpath(os.path.join(folder, base))
    if full != folder and not full.startswith(folder + os.sep):
        return None
    return full


def _safe_output_path(name):
    """允许 name 含相对子目录（如 demo_clone/x.html），但必须位于 OUTPUTS 内，禁止穿越。
    返回绝对路径或 None。用于 /api/article 取已生成文件。"""
    if not name or not name.strip():
        return None
    parts = name.replace("\\", "/").split("/")
    if name.startswith(("/", "\\")) or os.path.isabs(name) or ".." in parts:
        return None
    full = os.path.normpath(os.path.join(OUTPUTS, *parts))
    if full != OUTPUTS and not full.startswith(OUTPUTS + os.sep):
        return None
    return full


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html", "/preview.html"):
            self._serve_file(PREVIEW_HTML, "text/html; charset=utf-8")
            return
        if path == "/api/files":
            self._send_json(200, list_files())
            return
        if path == "/api/styles":
            self._send_json(200, list_styles())
            return
        if path == "/api/contents":
            self._send_json(200, list_contents())
            return
        if path == "/api/version":
            self._send_json(200, {"v": _version()})
            return
        if path == "/api/themes":
            self._send_json(200, self._list_themes())
            return
        if path == "/api/article":
            qs = urllib.parse.parse_qs(parsed.query)
            name = qs.get("file", [""])[0]
            if not name:
                self._send_json(400, {"error": "missing file"})
                return
            full = _safe_output_path(name)
            if not full or not os.path.isfile(full):
                self._send_json(404, {"error": "not found"})
                return
            try:
                with open(full, "r", encoding="utf-8") as f:
                    text = f.read()
            except OSError as e:
                self._send_json(500, {"error": str(e)})
                return
            # 相对资源（images/xxx.png）需指向服务根，否则在 /api/article 路径下会解析到
            # /api/article/images/... 而 404。注入 <base href="/">（若已有则不重复）。
            if "<base" not in text:
                if re.search(r"<head[^>]*>", text):
                    text = re.sub(r"(<head[^>]*>)", r'\1<base href="/">', text, count=1)
                elif re.search(r"<html[^>]*>", text):
                    text = re.sub(r"(<html[^>]*>)", r'\1<head><base href="/"></head>', text, count=1)
            # 用 text/html，使「新标签打开」能正确渲染（showFragment 用 r.text() 不受影响）
            self._send(200, text, "text/html; charset=utf-8")
            return

        if path.startswith("/images/"):
            self._serve_images(path[len("/images/"):])
            return

        # 静态文件
        abs_path = self._safe_path(path)
        if abs_path is None or not os.path.isfile(abs_path):
            self._send_json(404, {"error": "not found"})
            return
        self._serve_file(abs_path, self._guess_type(abs_path))

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            payload = self._read_json()
        except Exception as e:
            self._send_json(400, {"error": "bad json: " + str(e)})
            return

        if path == "/api/render":
            self._api_render(payload)
            return
        if path == "/api/extract-style":
            self._api_extract_style(payload)
            return
        self._send_json(404, {"error": "unknown endpoint"})

    def _api_render(self, payload):
        """动态渲染：按 mode 经 cli_bridge 子进程调用 clone_cli / draft_cli（禁止 import 内部函数）。"""
        mode = payload.get("mode", "clone")
        if mode == "draft":
            self._api_render_draft(payload)
            return
        # 默认 clone 模式
        if not HAVE_CLONE:
            self._send_json(500, {"error": "渲染模块不可用：" + CLONE_ERR})
            return
        style_arg = payload.get("style", "")
        content_arg = payload.get("content", "")
        if not style_arg or not content_arg:
            self._send_json(400, {"error": "需要 style 与 content"})
            return

        # content 形态映射：URL / outputs 下 .md 文件 / 原始 Markdown 文本（经 stdin）
        stdin_text = None
        if content_arg.startswith(("http://", "https://")):
            content_passthrough = content_arg
        elif content_arg.endswith((".md", ".txt")) and _safe_join(OUTPUTS, content_arg):
            content_passthrough = _safe_join(OUTPUTS, content_arg)
        else:
            # 原始 Markdown 文本：经 stdin 传给 clone_cli（"-"），避免落临时文件
            content_passthrough = "-"
            stdin_text = content_arg

        args = ["--style", style_arg, "--content", content_passthrough]
        if not payload.get("follow", True):
            args.append("--no-follow")
        if not payload.get("end_img", True):
            args.append("--no-end")
        if payload.get("keep_account", False):
            args.append("--keep-account")

        rc, out, err = cli_bridge.call_cli(
            CLONE_CLI, args,
            trace_id=_trace_id(),
            input_text=stdin_text,
        )
        if rc != 0:
            self._send_json(500, {"error": "渲染失败：" + (err.strip() or "未知错误（exit %d）" % rc)})
            return
        self._send(200, out, "text/plain; charset=utf-8")

    def _api_extract_style(self, payload):
        """提取样式：经 cli_bridge 子进程调用 clone_cli.py --dump-style 捕获 JSON 落盘。"""
        if not HAVE_CLONE:
            self._send_json(500, {"error": "渲染模块不可用：" + CLONE_ERR})
            return
        url = payload.get("url", "")
        name = (payload.get("name") or "").strip()
        if not url.startswith("http"):
            self._send_json(400, {"error": "需要合法的参考文章 URL"})
            return
        if not name:
            name = urllib.parse.quote(url, safe="")[:40]
        name = os.path.basename(name).replace("/", "_")
        if not name.endswith(".json"):
            name += ".json"
        rc, out, err = cli_bridge.call_cli(
            CLONE_CLI, ["--style", url, "--dump-style"],
            trace_id=_trace_id(),
        )
        if rc != 0:
            self._send_json(500, {"error": "提取失败：" + (err.strip() or "未知错误（exit %d）" % rc)})
            return
        try:
            st = json.loads(out)
        except Exception as e:
            self._send_json(500, {"error": "提取结果解析失败：" + str(e)})
            return
        os.makedirs(STYLES, exist_ok=True)
        fp = os.path.join(STYLES, name)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False, indent=2, default=str)
        self._send_json(200, {"ok": True, "name": name[:-5], "file": name, "count": len(st.get("headings", []))})

    def _api_render_draft(self, payload):
        """草稿渲染：经 cli_bridge 子进程调用 draft_cli.py 完成（禁止 import 内部函数）。
        draft 仅处理本地 Markdown：raw 文本走 stdin（'-'），outputs 下 .md/.txt 走文件路径。"""
        if not HAVE_DRAFT:
            self._send_json(500, {"error": "草稿排版模块不可用：" + DRAFT_ERR})
            return
        content_arg = payload.get("content", "")
        theme = (payload.get("theme") or "").strip()
        if not content_arg:
            self._send_json(400, {"error": "需要 content（Markdown 文本或 outputs 下 .md 文件名）"})
            return

        stdin_text = None
        if content_arg.endswith((".md", ".txt")) and _safe_join(OUTPUTS, content_arg):
            content_passthrough = _safe_join(OUTPUTS, content_arg)  # 文件路径
        else:
            content_passthrough = None  # 走 stdin
            stdin_text = content_arg

        args = []
        if theme:
            args += ["-t", theme]
        if content_passthrough:
            args.append(content_passthrough)  # 位置参数：输入文件（省略则读 stdin）

        rc, out, err = cli_bridge.call_cli(
            DRAFT_CLI, args,
            trace_id=_trace_id(),
            input_text=stdin_text,
        )
        if rc != 0:
            self._send_json(500, {"error": "渲染失败：" + (err.strip() or "未知错误（exit %d）" % rc)})
            return
        self._send(200, out, "text/plain; charset=utf-8")

    def _list_themes(self):
        """读取 references/theme.json 分发器（default_theme / available），不 import draft 内部函数。"""
        default = "xiangxiang"
        themes = []
        try:
            with open(DISPATCH, encoding="utf-8") as f:
                d = json.load(f)
            default = d.get("default_theme", default)
            themes = d.get("available") or []
        except Exception:
            pass
        if not themes:
            themes = [default]
        return {"default": default, "themes": themes}

    def _safe_path(self, url_path):
        rel = urllib.parse.unquote(urllib.parse.urlparse(url_path).path).lstrip("/")
        abs_path = os.path.normpath(os.path.join(HERE, rel))
        if abs_path != HERE and not abs_path.startswith(HERE + os.sep):
            return None
        return abs_path

    def _serve_images(self, rel):
        """静态托管 outputs/images/（渲染产物本地化的图片）。禁止路径穿越。"""
        rel = urllib.parse.unquote(rel).lstrip("/")
        full = os.path.normpath(os.path.join(IMAGES_DIR, rel))
        if full != IMAGES_DIR and not full.startswith(IMAGES_DIR + os.sep):
            self._send_json(403, {"error": "forbidden"})
            return
        if not os.path.isfile(full):
            self._send_json(404, {"error": "not found"})
            return
        self._serve_file(full, self._guess_type(full))

    def _serve_file(self, full, ctype):
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError as e:
            self._send_json(500, {"error": str(e)})
            return
        self._send(200, data, ctype)

    @staticmethod
    def _guess_type(path):
        if path.endswith((".html", ".htm")):
            return "text/html; charset=utf-8"
        if path.endswith(".js"):
            return "application/javascript; charset=utf-8"
        if path.endswith(".css"):
            return "text/css; charset=utf-8"
        if path.endswith(".json"):
            return "application/json; charset=utf-8"
        if path.endswith(".png"):
            return "image/png"
        if path.endswith((".jpg", ".jpeg")):
            return "image/jpeg"
        if path.endswith(".gif"):
            return "image/gif"
        if path.endswith(".svg"):
            return "image/svg+xml"
        return "application/octet-stream"

    def log_message(self, fmt, *args):
        sys.stderr.write("[serve] " + (fmt % args) + "\n")

    def log_request(self, code='-', size='-'):
        # 静默前端热重载心跳：preview.html 每 1.5s 轮询一次 /api/version，
        # 仅用于检测文件改动自动刷新，不写访问日志，避免刷屏。
        if self.path.split('?', 1)[0] == "/api/version":
            return
        super().log_request(code, size)


def build_server(port):
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def _find_free_port(start):
    """从 start 起找第一个能 bind 的空闲端口，避免 Windows 端口被占导致启动即崩。"""
    import socket
    p = start
    while p < start + 100:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p))
            s.close()
            return p
        except OSError:
            p += 1
    return start


def _open_browser(port):
    try:
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{port}/")
    except Exception as e:
        print(f"[警告] 无法自动打开浏览器：{e}（请手动访问 http://127.0.0.1:{port}/）")


def main():
    parser = argparse.ArgumentParser(description="article-format 预览服务")
    parser.add_argument("--port", type=int, default=8004, help="监听端口（默认 8004）")
    parser.add_argument("--no-reload", action="store_true", help="关闭文件改动自动重启")
    parser.add_argument("--open", action="store_true", help="启动后自动打开默认浏览器")
    args = parser.parse_args()

    # --open 时从 --port 起自动选空闲端口，避开 Windows 端口被占导致启动即崩
    port = args.port
    if args.open:
        port = _find_free_port(args.port)
        args.port = port

    def startup_msg(httpd):
        url = f"http://127.0.0.1:{port}/"
        print(f"预览服务已启动：{url}")
        if not HAVE_CLONE and not HAVE_DRAFT:
            print(f"[警告] 渲染模块均不可用，动态渲染将不可用，仅静态预览。")
        elif not HAVE_CLONE:
            print(f"[警告] clone 渲染不可用（{CLONE_ERR}），仅 draft 主题渲染可用。")
        elif not HAVE_DRAFT:
            print(f"[警告] draft 渲染不可用（{DRAFT_ERR}），仅 clone 渲染可用。")

    def launch(httpd):
        startup_msg(httpd)
        if args.open:
            _open_browser(port)

    if args.no_reload:
        httpd = build_server(port)
        launch(httpd)
        print("按 Ctrl+C 停止。（已关闭自动重启）")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        httpd.shutdown(); httpd.server_close()
        print("\n已停止。")
        return

    base = {f: _mtime(f) for f in WATCH_FILES}
    httpd = build_server(port)
    launch(httpd)
    print("按 Ctrl+C 停止。改动 serve.py / clone_cli.py / preview.html 将自动热重载，浏览器自动刷新。")

    state = {"restart": False, "execv": False}

    def watchdog():
        while True:
            time.sleep(1.0)
            for f in WATCH_FILES:
                mt = _mtime(f)
                if mt != base.get(f):
                    base[f] = mt  # 更新基线，避免重复触发
                    name = os.path.basename(f)
                    if f == __file__:
                        # serve.py 自身改动需真正重启进程；先释放端口再 execv，避免 Windows 端口占用
                        print(f"\n[reload] 检测到 {name} 改动，重启服务…")
                        state["execv"] = True
                        try:
                            httpd.shutdown()
                        except Exception:
                            pass
                        try:
                            httpd.server_close()
                        except Exception:
                            pass
                        # 重启带上当前端口与 --open，保持行为一致
                        cmd = [sys.executable, os.path.abspath(__file__),
                               "--port", str(port)]
                        if args.open:
                            cmd.append("--open")
                        os.execv(sys.executable, cmd)
                    else:
                        # clone_cli.py / preview.html：进程内热重载（版本号刷新，浏览器自动刷新）；
                        # clone 为子进程调用，下次请求自动用最新代码，无需重绑端口
                        print(f"\n[reload] 检测到 {name} 改动，热重载…")
                        state["restart"] = True
                        httpd.shutdown()
                        return

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        while True:
            httpd.serve_forever()
            if state["restart"]:
                state["restart"] = False
                httpd.server_close()
                httpd = build_server(port)
                print("[reload] 已就绪，继续服务。")
                continue
            break
    except KeyboardInterrupt:
        pass
    httpd.shutdown(); httpd.server_close()
    print("\n已停止。")


if __name__ == "__main__":
    main()
