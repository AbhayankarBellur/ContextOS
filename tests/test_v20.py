"""
ContextOS v2.0 tests — user memory, proxy, benchmarks, AICF spec, dashboard.
All offline. No network calls.
"""
import json
import math
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest


# ---------------------------------------------------------------------------
# User Memory Layer
# ---------------------------------------------------------------------------

class TestUserMemory:

    def test_write_and_read_fragment(self, tmp_path):
        from contextos.user_memory import write_fragment, _read_fragments_from_file
        memory_dir = tmp_path / "memory"
        frag = write_fragment(memory_dir, "alice@test.com", "Prefers async patterns",
                               fragment_type="preference", importance=4, source_client="cursor")
        assert frag["id"].startswith("mem_")
        assert frag["user_id"] == "alice@test.com"
        assert frag["type"] == "preference"
        assert frag["importance"] == 4
        assert frag["active"] is True

        stored = _read_fragments_from_file(memory_dir, "alice@test.com")
        assert len(stored) == 1
        assert stored[0]["content"] == "Prefers async patterns"

    def test_multiple_fragments_different_types(self, tmp_path):
        from contextos.user_memory import write_fragment, _read_fragments_from_file
        memory_dir = tmp_path / "memory"
        write_fragment(memory_dir, "bob", "Uses PostgreSQL always", "fact", 3, "kiro")
        write_fragment(memory_dir, "bob", "Chose LanceDB for vector store", "decision", 5, "claude-code")
        write_fragment(memory_dir, "bob", "Finished payment service", "event", 2, "cursor")

        frags = _read_fragments_from_file(memory_dir, "bob")
        assert len(frags) == 3
        types = {f["type"] for f in frags}
        assert types == {"fact", "decision", "event"}

    def test_supersede_marks_old_inactive(self, tmp_path):
        from contextos.user_memory import write_fragment, _read_fragments_from_file
        memory_dir = tmp_path / "memory"
        old  = write_fragment(memory_dir, "alice", "Old preference", "preference", 3, "user")
        new  = write_fragment(memory_dir, "alice", "New preference", "preference", 4, "user",
                               supersedes_id=old["id"])

        frags = _read_fragments_from_file(memory_dir, "alice")
        old_frag = next(f for f in frags if f["id"] == old["id"])
        assert old_frag["active"] is False
        assert old_frag["superseded_by_id"] == new["id"]

    def test_gdpr_delete_removes_all(self, tmp_path):
        from contextos.user_memory import write_fragment, delete_user_memory, _read_fragments_from_file
        memory_dir = tmp_path / "memory"
        write_fragment(memory_dir, "user123", "Memory 1", "fact", 3, "user")
        write_fragment(memory_dir, "user123", "Memory 2", "fact", 3, "user")

        result = delete_user_memory(memory_dir, "user123")
        assert result["deleted_fragments"] == 2
        assert not _memory_file_exists(memory_dir, "user123")

    def test_gdpr_delete_other_user_unaffected(self, tmp_path):
        from contextos.user_memory import write_fragment, delete_user_memory, _read_fragments_from_file
        memory_dir = tmp_path / "memory"
        write_fragment(memory_dir, "alice", "Alice memory", "fact", 3, "user")
        write_fragment(memory_dir, "bob", "Bob memory", "fact", 3, "user")

        delete_user_memory(memory_dir, "alice")
        bob_frags = _read_fragments_from_file(memory_dir, "bob")
        assert len(bob_frags) == 1

    def test_stats(self, tmp_path):
        from contextos.user_memory import write_fragment, get_stats
        memory_dir = tmp_path / "memory"
        write_fragment(memory_dir, "alice", "Fact one",       "fact",       3, "user")
        write_fragment(memory_dir, "alice", "Preference one", "preference", 4, "user")
        write_fragment(memory_dir, "alice", "Decision one",   "decision",   5, "user")

        stats = get_stats(memory_dir, "alice")
        assert stats["total_fragments"]  == 3
        assert stats["active_fragments"] == 3
        assert stats["by_type"]["fact"]       == 1
        assert stats["by_type"]["preference"] == 1
        assert stats["by_type"]["decision"]   == 1

    def test_list_users(self, tmp_path):
        from contextos.user_memory import write_fragment, list_users
        memory_dir = tmp_path / "memory"
        write_fragment(memory_dir, "alice@x.com", "A", "fact", 3, "user")
        write_fragment(memory_dir, "bob@x.com",   "B", "fact", 3, "user")
        users = list_users(memory_dir)
        assert "alice@x.com" in users
        assert "bob@x.com"   in users

    def test_importance_clamped(self, tmp_path):
        from contextos.user_memory import write_fragment
        memory_dir = tmp_path / "memory"
        f1 = write_fragment(memory_dir, "u", "x", importance=0)
        f2 = write_fragment(memory_dir, "u", "y", importance=10)
        assert f1["importance"] == 1
        assert f2["importance"] == 5


def _memory_file_exists(memory_dir, user_id):
    safe = "".join(c for c in user_id if c.isalnum() or c in "-_@.")[:80]
    return (memory_dir / f"{safe}.jsonl").exists()


# ---------------------------------------------------------------------------
# Decay scoring
# ---------------------------------------------------------------------------

class TestDecayScoring:

    def test_fresh_fragment_score_near_1(self):
        from contextos.user_memory import _decay_score
        score = _decay_score(datetime.now(timezone.utc).isoformat())
        assert score > 0.99

    def test_30_day_old_score_near_half(self):
        from contextos.user_memory import _decay_score
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        score = _decay_score(thirty_days_ago)
        assert 0.45 <= score <= 0.55

    def test_90_day_old_score_near_0125(self):
        from contextos.user_memory import _decay_score
        ninety = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        score = _decay_score(ninety)
        assert 0.10 <= score <= 0.15

    def test_invalid_date_returns_1(self):
        from contextos.user_memory import _decay_score
        assert _decay_score("not-a-date") == 1.0

    def test_decay_formula(self):
        """Verify the exact formula: exp(-ln2 * age / 30)."""
        from contextos.user_memory import _decay_score, DECAY_HALF_LIFE_DAYS
        for days in [0, 10, 30, 60, 90]:
            past = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            score = _decay_score(past)
            expected = math.exp(-math.log(2) * days / DECAY_HALF_LIFE_DAYS)
            assert abs(score - expected) < 0.02


# ---------------------------------------------------------------------------
# Proxy — turn classification
# ---------------------------------------------------------------------------

class TestProxyClassification:

    def test_recent_turns_are_hot(self):
        from contextos.proxy import classify_turn, TurnHeat
        assert classify_turn(0, "recent message") == TurnHeat.HOT
        assert classify_turn(4, "recent message") == TurnHeat.HOT

    def test_middle_turns_are_warm(self):
        from contextos.proxy import classify_turn, TurnHeat
        assert classify_turn(5,  "middle message") == TurnHeat.WARM
        assert classify_turn(14, "middle message") == TurnHeat.WARM

    def test_old_turns_are_cold(self):
        from contextos.proxy import classify_turn, TurnHeat
        assert classify_turn(15, "old message") == TurnHeat.COLD
        assert classify_turn(50, "old message") == TurnHeat.COLD

    def test_empty_turns_are_dead(self):
        from contextos.proxy import classify_turn, TurnHeat
        assert classify_turn(0, "") == TurnHeat.DEAD
        assert classify_turn(0, "   ") == TurnHeat.DEAD

    def test_duplicate_detection(self):
        from contextos.proxy import is_duplicate
        seen = set()
        assert is_duplicate("hello world", seen) is False
        assert is_duplicate("hello world", seen) is True  # second time = duplicate
        assert is_duplicate("different content", seen) is False

    def test_process_messages_drops_dead(self):
        from contextos.proxy import process_messages
        messages = [{"role": "user", "content": ""}, {"role": "user", "content": "real message"}]
        processed, stats = process_messages(messages, project=None, vault_query=None)
        assert stats["dead"] >= 1
        contents = [m["content"] for m in processed]
        assert "real message" in contents
        assert "" not in contents

    def test_process_messages_compresses_cold(self):
        from contextos.proxy import process_messages
        # 20 messages — oldest should be COLD and compressed
        messages = [{"role": "user", "content": f"Message {i}. " * 30} for i in range(20)]
        processed, stats = process_messages(messages, project=None, vault_query=None)
        assert stats["cold"] > 0
        # COLD messages should be marked [summary]
        cold_msgs = [m for m in processed if m.get("content","").startswith("[summary]")]
        assert len(cold_msgs) > 0

    def test_process_messages_keeps_hot_verbatim(self):
        from contextos.proxy import process_messages
        messages = [{"role": "user", "content": f"Message {i}"} for i in range(20)]
        processed, stats = process_messages(messages, project=None, vault_query=None)
        # Last 5 messages should be unchanged
        last_5_content = [m["content"] for m in processed[-5:]]
        for i in range(15, 20):
            assert f"Message {i}" in last_5_content

    def test_token_savings_computed(self):
        from contextos.proxy import process_messages
        messages = [{"role": "user", "content": "word " * 100} for _ in range(20)]
        _, stats = process_messages(messages, project=None, vault_query=None)
        assert "tokens_saved" in stats
        assert stats["tokens_saved"] >= 0
        assert "compression_pct" in stats

    def test_compress_turn(self):
        from contextos.proxy import compress_turn
        long_text = ("The payment service handles all transactions. " * 10 +
                     "Retries use exponential backoff. " * 5 +
                     "Refunds processed within 24 hours. " * 5)
        compressed = compress_turn(long_text, ratio=0.3)
        assert len(compressed) < len(long_text)
        assert len(compressed) > 0


# ---------------------------------------------------------------------------
# Schema: new memory models
# ---------------------------------------------------------------------------

def test_memory_fragment_type_enum():
    from contextos.schema import MemoryFragmentType
    assert MemoryFragmentType.fact       == "fact"
    assert MemoryFragmentType.preference == "preference"
    assert MemoryFragmentType.decision   == "decision"
    assert MemoryFragmentType.event      == "event"


def test_write_memory_request_validation():
    from contextos.schema import WriteMemoryRequest, MemoryFragmentType
    req = WriteMemoryRequest(user_id="alice", content="test", type=MemoryFragmentType.preference,
                              importance=4)
    assert req.user_id == "alice"
    assert req.importance == 4
    assert req.source_client == "user"

    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        WriteMemoryRequest(user_id="alice", content="test", importance=10)  # > 5


def test_query_memory_request():
    from contextos.schema import QueryMemoryRequest
    req = QueryMemoryRequest(user_id="bob", query="payment patterns")
    assert req.limit == 10
    assert req.min_importance == 1
    assert req.include_superseded is False


# ---------------------------------------------------------------------------
# AICF spec file exists and is valid
# ---------------------------------------------------------------------------

def test_aicf_spec_exists():
    spec = Path("docs/AICF-SPEC.md")
    assert spec.exists(), "docs/AICF-SPEC.md missing"
    content = spec.read_text(encoding="utf-8")
    assert "AICF" in content
    assert "project" in content
    assert "type" in content
    assert "status" in content


def test_aicf_spec_has_required_sections():
    spec = Path("docs/AICF-SPEC.md").read_text(encoding="utf-8")
    for section in ["Required Frontmatter", "Document Types", "ADR Format", "User Memory"]:
        assert section in spec, f"Missing section: {section}"


# ---------------------------------------------------------------------------
# Benchmarks file exists
# ---------------------------------------------------------------------------

def test_benchmarks_exist():
    assert Path("benchmarks/README.md").exists()
    assert Path("benchmarks/hybrid-results.json").exists()
    assert Path("benchmarks/vector-results.json").exists()


def test_benchmarks_show_hybrid_advantage():
    combined = json.loads(Path("benchmarks/combined.json").read_text())
    vector = combined["vector"]
    hybrid = combined["hybrid"]
    # Hybrid avg_top1_score must be >= vector
    assert hybrid["avg_top1_score"] >= vector["avg_top1_score"]
    # Hybrid latency should be much better (cached BM25)
    assert hybrid["avg_latency_ms"] < vector["avg_latency_ms"]


# ---------------------------------------------------------------------------
# Dashboard static file exists
# ---------------------------------------------------------------------------

def test_dashboard_html_exists():
    html = Path("contextos/static/dashboard.html")
    assert html.exists()
    content = html.read_text(encoding="utf-8")
    assert "ContextOS" in content
    assert "search" in content.lower()
    assert "tokens" in content.lower()


# ---------------------------------------------------------------------------
# API imports cleanly (no recursion)
# ---------------------------------------------------------------------------

def test_api_imports_with_new_endpoints():
    import sys
    for key in list(sys.modules.keys()):
        if "contextos.api" in key:
            del sys.modules[key]
    try:
        import contextos.api as api
        assert hasattr(api, "app")
        # Check new routes exist
        routes = [r.path for r in api.app.routes]
        assert "/memory/write"    in routes
        assert "/memory/query"    in routes
        assert "/memory/stats"    in routes
        assert "/admin/memory"    in routes
        assert "/dashboard"       in routes
    except RecursionError:
        pytest.fail("api.py caused RecursionError on import")


# ---------------------------------------------------------------------------
# Proxy module imports
# ---------------------------------------------------------------------------

def test_proxy_imports():
    import contextos.proxy as proxy
    assert hasattr(proxy, "run_proxy")
    assert hasattr(proxy, "process_messages")
    assert hasattr(proxy, "classify_turn")
    assert hasattr(proxy, "TurnHeat")


# ---------------------------------------------------------------------------
# CLI commands exist
# ---------------------------------------------------------------------------

def test_new_cli_commands_registered():
    from contextos.cli import app
    # Find all command names
    all_names = set()
    for cmd in app.registered_commands:
        all_names.add(cmd.name or cmd.callback.__name__)
    for group in app.registered_groups:
        all_names.add(group.name)
    assert "memory-user" in all_names or any("memory" in n for n in all_names)
    assert "proxy" in all_names
    assert "suggest" in all_names
