"""
ContextOS logger.py — Structured JSON logging engine.

Writes structured JSONL logs to .contextos/logs/:
  app.jsonl   — all requests and operations
  slow.jsonl  — queries exceeding SLOW_QUERY_MS threshold
  audit.jsonl — token usage and access events

Features:
  - Log rotation: max 10MB per file, keep 3 files
  - Request ID generation: req_<8hex>
  - Zero external dependencies (stdlib only)
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SLOW_QUERY_MS = 500
MAX_LOG_BYTES = 10 * 1024 * 1024   # 10 MB
MAX_LOG_FILES = 3


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_request_id() -> str:
    return "req_" + secrets.token_hex(4)


# ---------------------------------------------------------------------------
# Low-level writer with rotation
# ---------------------------------------------------------------------------

def _write_jsonl(log_file: Path, record: dict) -> None:
    """Append a JSON record to a log file. Rotates if over MAX_LOG_BYTES."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Rotate if needed
        if log_file.exists() and log_file.stat().st_size >= MAX_LOG_BYTES:
            _rotate(log_file)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        logging.getLogger(__name__).debug("Log write failed: %s", exc)


def _rotate(log_file: Path) -> None:
    """Rotate logs: app.3.jsonl gets deleted, .2→.3, .1→.2, base→.1"""
    base = log_file.with_suffix("")
    suffix = log_file.suffix
    for i in range(MAX_LOG_FILES - 1, 0, -1):
        src = Path(f"{base}.{i}{suffix}")
        dst = Path(f"{base}.{i + 1}{suffix}")
        if src.exists():
            if dst.exists():
                dst.unlink()
            src.rename(dst)
    rotated = Path(f"{base}.1{suffix}")
    if rotated.exists():
        rotated.unlink()
    log_file.rename(rotated)


# ---------------------------------------------------------------------------
# StructuredLogger
# ---------------------------------------------------------------------------

class StructuredLogger:
    """
    Structured JSON logger for ContextOS.
    Writes to .contextos/logs/ directory.
    """

    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._app_log   = logs_dir / "app.jsonl"
        self._slow_log  = logs_dir / "slow.jsonl"
        self._audit_log = logs_dir / "audit.jsonl"
        self._stats = {"total_requests": 0, "total_latency_ms": 0,
                       "slow_queries": 0, "errors": 0}

    def log_request(
        self,
        request_id: str,
        endpoint: str,
        method: str,
        latency_ms: int,
        token_id: Optional[str],
        status_code: int,
        extra: Optional[dict] = None,
    ) -> None:
        record = {
            "ts":         _now_iso(),
            "type":       "request",
            "request_id": request_id,
            "endpoint":   endpoint,
            "method":     method,
            "latency_ms": latency_ms,
            "token_id":   token_id or "—",
            "status":     status_code,
        }
        if extra:
            record.update(extra)
        _write_jsonl(self._app_log, record)

        # Update rolling stats
        self._stats["total_requests"] += 1
        self._stats["total_latency_ms"] += latency_ms
        if status_code >= 400:
            self._stats["errors"] += 1

        # Slow query log
        if latency_ms >= SLOW_QUERY_MS:
            self._stats["slow_queries"] += 1
            slow_record = {**record, "type": "slow_query"}
            _write_jsonl(self._slow_log, slow_record)

    def log_index_op(
        self,
        operation: str,
        doc_count: int,
        chunk_count: int,
        duration_s: float,
        project: Optional[str] = None,
    ) -> None:
        _write_jsonl(self._app_log, {
            "ts":          _now_iso(),
            "type":        "index_op",
            "operation":   operation,
            "doc_count":   doc_count,
            "chunk_count": chunk_count,
            "duration_s":  round(duration_s, 3),
            "project":     project or "all",
        })

    def log_audit(
        self,
        request_id: str,
        token_id: str,
        token_name: str,
        endpoint: str,
        method: str,
        latency_ms: int,
        scope: str = "read",
    ) -> None:
        _write_jsonl(self._audit_log, {
            "ts":          _now_iso(),
            "type":        "audit",
            "request_id":  request_id,
            "token_id":    token_id,
            "token_name":  token_name,
            "endpoint":    endpoint,
            "method":      method,
            "latency_ms":  latency_ms,
            "scope":       scope,
        })

    def log_error(self, message: str, exc: Optional[Exception] = None,
                  extra: Optional[dict] = None) -> None:
        record = {"ts": _now_iso(), "type": "error", "message": message}
        if exc:
            record["exception"] = str(exc)
        if extra:
            record.update(extra)
        _write_jsonl(self._app_log, record)
        self._stats["errors"] += 1

    def get_metrics(self) -> dict:
        total = self._stats["total_requests"]
        avg_latency = (
            self._stats["total_latency_ms"] // total
            if total > 0 else 0
        )
        return {
            "total_requests":    total,
            "avg_latency_ms":    avg_latency,
            "slow_queries":      self._stats["slow_queries"],
            "errors":            self._stats["errors"],
        }

    def tail_log(
        self,
        lines: int = 50,
        level: str = "all",
        log_type: str = "app",
    ) -> list[dict]:
        """Read last N lines from a log file."""
        log_file = {"app": self._app_log, "slow": self._slow_log,
                    "audit": self._audit_log}.get(log_type, self._app_log)

        if not log_file.exists():
            return []

        records = []
        try:
            raw_lines = log_file.read_text(encoding="utf-8").splitlines()
            for line in raw_lines[-lines * 2:]:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                    if level == "all" or r.get("type") == level:
                        records.append(r)
                except Exception:
                    pass
        except Exception:
            pass
        return records[-lines:]

    def read_audit(self, limit: int = 100) -> list[dict]:
        return self.tail_log(lines=limit, log_type="audit")


# ---------------------------------------------------------------------------
# Global singleton — lazily initialised by api.py
# ---------------------------------------------------------------------------

_logger: Optional[StructuredLogger] = None


def get_logger(logs_dir: Optional[Path] = None) -> StructuredLogger:
    global _logger
    if _logger is None:
        if logs_dir is None:
            from contextos.config import load_config
            cfg = load_config()
            logs_dir = cfg.logs_dir
        _logger = StructuredLogger(logs_dir)
    return _logger


def init_logger(logs_dir: Path) -> StructuredLogger:
    global _logger
    _logger = StructuredLogger(logs_dir)
    return _logger
