# -*- coding: utf-8 -*-
"""本地审计日志（security 设计 §7.2 权威字段，platform 设计 §5.5 管道承载）。

写入位置：article_formate/logs/audit.log（JSON Lines，每行一条）。
字段（security §7.2.1 本地 5 维度 + OCR 专用）：
  timestamp, traceId, event_type, source_trust_domain, target, result, detail
  + OCR 专用：fail_count, timeout_ms, skip_action, feedback, error_code

设计约定：
- 追加写，文件权限仅追加；审计失败绝不阻断主流程。
- 保留期 ≥90 天（由部署设计 §5.5 落盘），本模块只负责写入。
"""
import os
import json
import time
import threading

_lock = threading.Lock()


def _project_root():
    # common/audit.py -> article_formate/
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(here)


def _log_path():
    return os.path.join(_project_root(), "logs", "audit.log")


def write(event_type, target="", result="", detail=None,
          source_trust_domain="TD-0", trace_id=None, extra=None):
    """写一条审计记录（JSON Lines，追加写）。"""
    rec = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "traceId": trace_id or os.environ.get("TRACE_ID", ""),
        "event_type": event_type,
        "source_trust_domain": source_trust_domain,
        "target": target,
        "result": result,
        "detail": detail or {},
    }
    if extra:
        rec.update(extra)
    line = json.dumps(rec, ensure_ascii=False)
    try:
        log_dir = os.path.join(_project_root(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        with _lock:
            with open(_log_path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        # 审计写入失败不应阻断主流程
        pass


def ocr_failure(target, fail_count, timeout_ms, skip_action, feedback,
                error_code, trace_id=None, source_trust_domain="TD-0"):
    """OCR 失败 / 降级审计（G4⑨，错误码 A010003 / A010004）。

    error_code:
      A010003 = OCR 不可达已降级（微服务网络错误 / 5xx / 超时重试后仍失败）
      A010004 = 引导图识别失败已降级（OCR 可达但未命中引导词，退化为结构启发式）
    """
    write(
        event_type="ocr_fail",
        target=target,
        result="degraded",
        source_trust_domain=source_trust_domain,
        trace_id=trace_id,
        extra={
            "fail_count": fail_count,
            "timeout_ms": timeout_ms,
            "skip_action": skip_action,
            "feedback": feedback,
            "error_code": error_code,
        },
    )
