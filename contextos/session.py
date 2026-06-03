"""
ContextOS session.py — Agent session tracking and memory.

Tracks what an agent retrieved, what files changed, and what decisions were
made during a work session. Each session is persisted as JSON in
.contextos/sessions/ and auto-exported as a Markdown vault doc on close.

This gives agents a "what happened last time" summary at the start of each
new session — eliminating repeated context bootstrapping.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SESSION_DIR = "sessions"
EVENT_TYPES = {
    "context_retrieved",
    "search_performed",
    "file_read",
    "file_changed",
    "decision_made",
    "task_started",
    "task_completed",
    "note",
}


# ---------------------------------------------------------------------------
# Data classes (plain dicts for JSON-serializability)
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_session(name: Optional[str] = None) -> dict:
    return {
        "id":         str(uuid.uuid4())[:8],
        "name":       name or f"session-{time.strftime('%Y%m%d-%H%M')}",
        "started_at": _now_iso(),
        "ended_at":   None,
        "events":     [],
        "summary":    None,
    }


def _session_file(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.json"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_session(sessions_dir: Path, name: Optional[str] = None) -> dict:
    """Create and persist a new session. Returns session dict."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    session = _new_session(name)
    _save(sessions_dir, session)
    logger.info("Session created: %s (%s)", session["id"], session["name"])
    return session


def get_session(sessions_dir: Path, session_id: str) -> Optional[dict]:
    """Load a session by ID."""
    f = _session_file(sessions_dir, session_id)
    if not f.exists():
        return None
    return json.loads(f.read_text())


def get_active_session(sessions_dir: Path) -> Optional[dict]:
    """Return the most recently created non-ended session, if any."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    sessions = list_sessions(sessions_dir, limit=10)
    for s in sessions:
        if s.get("ended_at") is None:
            return s
    return None


def get_last_session(sessions_dir: Path) -> Optional[dict]:
    """Return the most recently ended session."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    sessions = list_sessions(sessions_dir, limit=20)
    for s in sessions:
        if s.get("ended_at") is not None:
            return s
    return None


def list_sessions(sessions_dir: Path, limit: int = 20) -> list[dict]:
    """List sessions, newest first."""
    sessions_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(sessions_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    result = []
    for f in files[:limit]:
        try:
            result.append(json.loads(f.read_text()))
        except Exception:
            pass
    return result


def add_event(
    sessions_dir: Path,
    session_id: str,
    event_type: str,
    payload: dict,
) -> bool:
    """Append an event to a session. Returns True on success."""
    session = get_session(sessions_dir, session_id)
    if not session:
        logger.warning("Session not found: %s", session_id)
        return False
    if session.get("ended_at"):
        logger.warning("Session already ended: %s", session_id)
        return False
    if event_type not in EVENT_TYPES:
        logger.warning("Unknown event type: %s", event_type)

    event = {
        "type":       event_type,
        "timestamp":  _now_iso(),
        "payload":    payload,
    }
    session["events"].append(event)
    _save(sessions_dir, session)
    return True


def end_session(
    sessions_dir: Path,
    session_id: str,
    vault_export_dir: Optional[Path] = None,
) -> dict:
    """
    Close a session, generate a summary, optionally export to vault.
    Returns the closed session dict.
    """
    session = get_session(sessions_dir, session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    session["ended_at"] = _now_iso()
    session["summary"]  = _generate_summary(session)
    _save(sessions_dir, session)

    # Export to vault as Markdown
    if vault_export_dir:
        _export_to_vault(session, vault_export_dir)

    logger.info("Session ended: %s — %d events", session_id, len(session["events"]))
    return session


def _save(sessions_dir: Path, session: dict) -> None:
    f = _session_file(sessions_dir, session["id"])
    f.write_text(json.dumps(session, indent=2))


# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------

def _generate_summary(session: dict) -> dict:
    """Derive a structured summary from session events."""
    events = session.get("events", [])

    searches        = [e for e in events if e["type"] == "search_performed"]
    context_calls   = [e for e in events if e["type"] == "context_retrieved"]
    files_read      = [e for e in events if e["type"] == "file_read"]
    files_changed   = [e for e in events if e["type"] == "file_changed"]
    decisions       = [e for e in events if e["type"] == "decision_made"]
    tasks           = [e for e in events if e["type"] in ("task_started", "task_completed")]
    notes           = [e for e in events if e["type"] == "note"]

    started  = session.get("started_at", "")
    ended    = session.get("ended_at", "")
    duration = ""
    if started and ended:
        try:
            s = datetime.fromisoformat(started)
            e = datetime.fromisoformat(ended)
            secs = int((e - s).total_seconds())
            duration = f"{secs // 60}m {secs % 60}s"
        except Exception:
            pass

    return {
        "duration":          duration,
        "total_events":      len(events),
        "searches":          [e["payload"].get("query","") for e in searches],
        "context_queries":   [e["payload"].get("query","") for e in context_calls],
        "files_read":        list({e["payload"].get("filepath","") for e in files_read}),
        "files_changed":     list({e["payload"].get("filepath","") for e in files_changed}),
        "decisions":         [e["payload"].get("text","") for e in decisions],
        "tasks_completed":   [e["payload"].get("task","") for e in tasks if e["type"]=="task_completed"],
        "notes":             [e["payload"].get("text","") for e in notes],
    }


# ---------------------------------------------------------------------------
# Vault export
# ---------------------------------------------------------------------------

def _export_to_vault(session: dict, vault_dir: Path) -> Path:
    """Write session summary as a Markdown vault document."""
    vault_dir.mkdir(parents=True, exist_ok=True)
    s = session.get("summary", {})
    started = session.get("started_at","")[:10]
    sid     = session.get("id","")
    name    = session.get("name","")

    lines = [
        "---",
        f"project: contextos",
        f"type: context",
        f"status: approved",
        f"updated_at: {started}",
        f"tags:",
        f"  - session",
        f"  - agent-memory",
        "---",
        "",
        f"# Session: {name}",
        "",
        f"**ID:** {sid}  ",
        f"**Started:** {session.get('started_at','')}  ",
        f"**Ended:** {session.get('ended_at','')}  ",
        f"**Duration:** {s.get('duration','')}  ",
        f"**Events:** {s.get('total_events',0)}",
        "",
    ]

    if s.get("tasks_completed"):
        lines += ["## Tasks Completed", ""]
        for t in s["tasks_completed"]:
            lines.append(f"- {t}")
        lines.append("")

    if s.get("decisions"):
        lines += ["## Decisions Made", ""]
        for d in s["decisions"]:
            lines.append(f"- {d}")
        lines.append("")

    if s.get("searches"):
        lines += ["## Searches Performed", ""]
        for q in s["searches"]:
            lines.append(f"- `{q}`")
        lines.append("")

    if s.get("files_changed"):
        lines += ["## Files Changed", ""]
        for f in s["files_changed"]:
            lines.append(f"- `{f}`")
        lines.append("")

    if s.get("notes"):
        lines += ["## Notes", ""]
        for n in s["notes"]:
            lines.append(f"- {n}")
        lines.append("")

    content = "\n".join(lines)
    out_path = vault_dir / f"session-{started}-{sid}.md"
    out_path.write_text(content)
    logger.info("Session exported to vault: %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Session-aware API helpers
# ---------------------------------------------------------------------------

def log_search(sessions_dir: Path, session_id: Optional[str], query: str, result_count: int):
    if session_id:
        add_event(sessions_dir, session_id, "search_performed",
                  {"query": query, "results": result_count})


def log_context(sessions_dir: Path, session_id: Optional[str], query: str, token_estimate: int):
    if session_id:
        add_event(sessions_dir, session_id, "context_retrieved",
                  {"query": query, "token_estimate": token_estimate})


def log_file_read(sessions_dir: Path, session_id: Optional[str], filepath: str):
    if session_id:
        add_event(sessions_dir, session_id, "file_read", {"filepath": filepath})
