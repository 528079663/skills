# -*- coding: utf-8 -*-
"""子进程 CLI 桥接封装（preview → clone / draft）。

设计约束（系统设计 V2 / P3）：preview 进程**禁止 import** clone / draft 的任何内部函数，
所有渲染 / 提取必须经本模块的子进程调用完成，实现进程级解耦。

- 参数以数组形式传递（subprocess.run([...])），禁 shell=True、禁字符串拼接不可信输入，防命令注入。
- trace_id 经环境变量 TRACE_ID 透传，供下游审计日志串联（安全设计 §7.2）。
"""
import os
import sys
import subprocess

# 单次 CLI 调用超时（秒）。提取样式 / 渲染通常远小于此；超时不阻塞主链，由调用方降级。
DEFAULT_TIMEOUT = 120


def call_cli(cli_path, args, trace_id=None, timeout=DEFAULT_TIMEOUT, cwd=None, input_text=None):
    """调用一个子 skill CLI，返回 (returncode, stdout, stderr)。

    cli_path  : 目标 CLI 脚本绝对路径（如 article-format-clone/scripts/clone_cli.py）
    args      : 参数列表（不含脚本名），元素均为字符串 / 数字，禁止拼接 shell
    trace_id  : 可选，写入子进程环境变量 TRACE_ID，用于审计串联
    input_text: 可选，作为标准输入传给子进程（如把原始 Markdown 经 stdin 喂给 clone_cli）
    """
    cmd = [sys.executable, cli_path] + [str(a) for a in args]
    env = dict(os.environ)
    if trace_id:
        env["TRACE_ID"] = str(trace_id)
    # 强制子进程以 UTF-8 收发：与子 CLI 内的 _force_utf8() 对齐，避免中文 Windows 下
    # 父进程按 GBK 解码子进程 UTF-8 输出导致 mojibake / 解码崩溃（P3 解耦通信边界）。
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=cwd,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
            input=input_text if input_text is not None else None,
        )
    except subprocess.TimeoutExpired:
        return (-1, "", f"CLI 调用超时（>{timeout}s）：{cli_path}")
    except Exception as e:  # 启动失败 / 找不到解释器等
        return (-2, "", f"CLI 调用异常：{e}")
    return (proc.returncode, proc.stdout or "", proc.stderr or "")
