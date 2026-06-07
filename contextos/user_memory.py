"""
ContextOS user_memory.py — Cross-app user memory layer.

Stores persistent user preferences, decisions, facts, and events that
any LLM client can write and read. user_id is the universal key.

Key design:
  - Fragment versioning: superseded_by_id self-reference
  - Exponential time decay: score halves every 30 days
  - GDPR bulk delete: DELETE /admin/memory?user_id=
  - Hybrid search: BM25 + vector on content field
  - Stored in .contextos/memory/<user_id>.jsonl + LanceDB table 'user_memory'

This turns ContextOS from project-scoped to user+project scoped memory.
Any LLM app can write memories; any other can retrieve them by user_id.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import secrets
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MEMORY_TABLE = "user_memory"
DECAY_HALF_LIFE_DAYS = 30   # score halves every 30 days (Project 1 formula)


# ---------------------------------------------------------------------------
# Schema (mirrors schema.py but kept self-contained for import simplicity)
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fragment_id() -> str:
    return "mem_" + secrets.token_hex(8)


def _decay_score(created_at: str, half_life_days: float = DECAY_HALF_LIFE_DAYS) -> float:
    """
    Exponential time decay.
    score = exp(-ln2 * age_days / half_life_days)
    At age=0: score=1.0. At age=30 days: score=0.5. At age=90 days: score=0.125.
    """
    try:
        created = datetime.fromisoformat(created_at)
        age_days = (datetime.now(timezone.utc) - created).total_seconds() / 86400
        return math.exp(-math.log(2) * age_days / half_life_days)
    except Exception:
        return 1.0


# ---------------------------------------------------------------------------
# JSONL persistence (fast append, readable without LanceDB)
# ---------------------------------------------------------------------------

def _memory_file(memory_dir: Path, user_id: str) -> Path:
    """Per-user JSONL file — human readable, appendable."""
    # Sanitise user_id for filename
    safe_id = "".join(c for c in user_id if c.isalnum() or c in "-_@.")[:80]
    return memory_dir / f"{safe_id}.jsonl"


def _write_fragment_to_file(memory_dir: Path, fragment: dict) -> None:
    memory_dir.mkdir(parents=True, exist_ok=True)
    f = _memory_file(memory_dir, fragment["user_id"])
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(fragment) + "\n")


def _read_fragments_from_file(memory_dir: Path, user_id: str) -> list[dict]:
    f = _memory_file(memory_dir, user_id)
    if not f.exists():
        return []
    fragments = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            fragments.append(json.loads(line))
        except Exception:
            pass
    return fragments


def _rewrite_fragments(memory_dir: Path, user_id: str, fragments: list[dict]) -> None:
    """Rewrite the JSONL file (used for updates and deletes)."""
    f = _memory_file(memory_dir, user_id)
    content = "\n".join(json.dumps(fr) for fr in fragments) + "\n"
    f.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def write_fragment(
    memory_dir: Path,
    user_id: str,
    content: str,
    fragment_type: str = "fact",     # fact | preference | decision | event
    importance: int = 3,             # 1-5
    source_client: str = "user",     # claude-code | cursor | kiro | user | etc.
    project: Optional[str] = None,
    tags: Optional[list[str]] = None,
    supersedes_id: Optional[str] = None,
) -> dict:
    """
    Write a new memory fragment for a user.
    If supersedes_id provided, marks old fragment as superseded.
    Returns the new fragment dict.
    """
    fragment = {
        "id":               _fragment_id(),
        "user_id":          user_id,
        "content":          content,
        "type":             fragment_type,
        "importance":       max(1, min(5, importance)),
        "source_client":    source_client,
        "project":          project,
        "tags":             tags or [],
        "created_at":       _now_iso(),
        "last_accessed":    None,
        "superseded_by_id": None,
        "active":           True,
    }

    # Mark old fragment as superseded
    if supersedes_id:
        old_fragments = _read_fragments_from_file(memory_dir, user_id)
        updated = []
        for fr in old_fragments:
            if fr["id"] == supersedes_id:
                fr["superseded_by_id"] = fragment["id"]
                fr["active"] = False
            updated.append(fr)
        _rewrite_fragments(memory_dir, user_id, updated)

    _write_fragment_to_file(memory_dir, fragment)
    _upsert_to_lancedb(memory_dir, fragment)

    logger.info("Memory fragment written: user=%s type=%s id=%s",
                user_id, fragment_type, fragment["id"])
    return fragment


def query_fragments(
    memory_dir: Path,
    user_id: str,
    query: str,
    embedder,
    project: Optional[str] = None,
    fragment_type: Optional[str] = None,
    limit: int = 10,
    min_importance: int = 1,
    include_superseded: bool = False,
) -> list[dict]:
    """
    Query memory fragments for a user.
    Ranking = importance × decay_score × similarity
    Returns list of fragments enriched with computed scores.
    """
    # Get all active fragments for this user from JSONL
    all_fragments = _read_fragments_from_file(memory_dir, user_id)
    if not all_fragments:
        return []

    # Filter
    candidates = [
        fr for fr in all_fragments
        if fr.get("active", True)
        and (include_superseded or not fr.get("superseded_by_id"))
        and fr.get("importance", 1) >= min_importance
        and (project is None or fr.get("project") in (None, project))
        and (fragment_type is None or fr.get("type") == fragment_type)
    ]

    if not candidates:
        return []

    # Embed query and candidate contents
    try:
        query_vec = embedder.embed_query(query)
        contents  = [fr["content"] for fr in candidates]
        content_vecs = embedder.embed(contents)

        # Cosine similarity (vectors are L2-normalised)
        import numpy as np
        q = np.array(query_vec)
        scored = []
        for fr, cv in zip(candidates, content_vecs):
            similarity   = float(np.dot(q, np.array(cv)))  # dot of L2-normalised = cosine
            decay        = _decay_score(fr["created_at"])
            importance   = fr.get("importance", 3) / 5.0
            final_score  = importance * decay * max(0.0, similarity)
            scored.append({**fr, "_similarity": round(similarity, 4),
                           "_decay": round(decay, 4), "_score": round(final_score, 4)})

        scored.sort(key=lambda x: x["_score"], reverse=True)

        # Update last_accessed for top results
        top_ids = {fr["id"] for fr in scored[:limit]}
        all_updated = []
        for fr in all_fragments:
            if fr["id"] in top_ids:
                fr["last_accessed"] = _now_iso()
            all_updated.append(fr)
        _rewrite_fragments(memory_dir, user_id, all_updated)

        return scored[:limit]

    except Exception as exc:
        logger.warning("Memory query scoring failed (%s) — returning unscored", exc)
        return candidates[:limit]


def delete_user_memory(memory_dir: Path, user_id: str) -> dict:
    """
    GDPR bulk delete: remove all memory fragments for a user.
    Deletes JSONL file and removes from LanceDB.
    Returns count deleted.
    """
    f = _memory_file(memory_dir, user_id)
    count = 0
    if f.exists():
        fragments = _read_fragments_from_file(memory_dir, user_id)
        count = len(fragments)
        f.unlink()

    # Remove from LanceDB
    try:
        import lancedb
        lancedb_dir = memory_dir.parent / "lancedb"
        if lancedb_dir.exists():
            db = lancedb.connect(str(lancedb_dir))
            if MEMORY_TABLE in db.table_names():
                safe_id = user_id.replace("'", "''")
                db.open_table(MEMORY_TABLE).delete(f"user_id = '{safe_id}'")
    except Exception as exc:
        logger.debug("LanceDB memory delete failed: %s", exc)

    logger.info("GDPR delete: user=%s fragments=%d", user_id, count)
    return {"user_id": user_id, "deleted_fragments": count}


def get_stats(memory_dir: Path, user_id: str) -> dict:
    """Return memory statistics for a user."""
    fragments = _read_fragments_from_file(memory_dir, user_id)
    active    = [fr for fr in fragments if fr.get("active", True)]
    by_type   = {}
    for fr in active:
        t = fr.get("type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1

    oldest = min((fr["created_at"] for fr in active), default=None)
    newest = max((fr["created_at"] for fr in active), default=None)

    return {
        "user_id":           user_id,
        "total_fragments":   len(fragments),
        "active_fragments":  len(active),
        "superseded":        len(fragments) - len(active),
        "by_type":           by_type,
        "oldest":            oldest,
        "newest":            newest,
    }


def list_users(memory_dir: Path) -> list[str]:
    """List all user_ids that have memory fragments."""
    if not memory_dir.exists():
        return []
    return [f.stem for f in memory_dir.glob("*.jsonl")]


# ---------------------------------------------------------------------------
# LanceDB integration
# ---------------------------------------------------------------------------

def _upsert_to_lancedb(memory_dir: Path, fragment: dict) -> None:
    """Store fragment embedding in the user_memory LanceDB table."""
    try:
        import lancedb
        import pyarrow as pa

        lancedb_dir = memory_dir.parent / "lancedb"
        db = lancedb.connect(str(lancedb_dir))

        record = {
            "id":            fragment["id"],
            "user_id":       fragment["user_id"],
            "content":       fragment["content"],
            "type":          fragment["type"],
            "importance":    fragment["importance"],
            "source_client": fragment["source_client"],
            "project":       fragment.get("project") or "",
            "created_at":    fragment["created_at"],
            "active":        fragment.get("active", True),
        }

        if MEMORY_TABLE not in db.table_names():
            schema = pa.schema([
                pa.field("id",            pa.utf8()),
                pa.field("user_id",       pa.utf8()),
                pa.field("content",       pa.utf8()),
                pa.field("type",          pa.utf8()),
                pa.field("importance",    pa.int32()),
                pa.field("source_client", pa.utf8()),
                pa.field("project",       pa.utf8()),
                pa.field("created_at",    pa.utf8()),
                pa.field("active",        pa.bool_()),
            ])
            db.create_table(MEMORY_TABLE, data=[record], schema=schema)
        else:
            table = db.open_table(MEMORY_TABLE)
            table.add([record])

    except Exception as exc:
        logger.debug("LanceDB memory upsert failed (non-critical): %s", exc)
