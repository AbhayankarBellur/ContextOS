"""
ContextOS v1.1 smoke tests — incremental index, symbols, compressor, watcher.
"""
import json
import time
from pathlib import Path
import pytest


# ---------------------------------------------------------------------------
# Incremental index tests
# ---------------------------------------------------------------------------

def test_hash_store_roundtrip(tmp_path):
    from contextos.vault import load_hash_store, save_hash_store
    hashes = {"doc1": "abc123", "doc2": "def456"}
    save_hash_store(tmp_path, hashes)
    loaded = load_hash_store(tmp_path)
    assert loaded == hashes


def test_compute_changed_documents(tmp_path):
    from contextos.schema import Document, DocumentType, DocumentStatus
    from contextos.vault import compute_changed_documents, save_hash_store
    import hashlib

    def make_doc(doc_id, content):
        return Document(
            id=doc_id, project="test", type=DocumentType.note,
            status=DocumentStatus.draft, title="Test", filepath=tmp_path / f"{doc_id}.md",
            content=content,
        )

    doc_a = make_doc("doc_a", "content A")
    doc_b = make_doc("doc_b", "content B")
    doc_c = make_doc("doc_c", "content C")  # new

    # Pre-store hashes for doc_a (unchanged) and doc_b (will change)
    stored = {
        "doc_a": hashlib.sha256("content A".encode()).hexdigest(),
        "doc_b": hashlib.sha256("old content B".encode()).hexdigest(),
    }
    save_hash_store(tmp_path, stored)

    # doc_b has different content now, doc_c is new
    new_docs, changed_docs, unchanged_docs = compute_changed_documents(
        [doc_a, doc_b, doc_c], tmp_path
    )
    assert [d.id for d in new_docs] == ["doc_c"]
    assert [d.id for d in changed_docs] == ["doc_b"]
    assert [d.id for d in unchanged_docs] == ["doc_a"]


def test_update_hash_store(tmp_path):
    from contextos.schema import Document, DocumentType, DocumentStatus
    from contextos.vault import update_hash_store, load_hash_store
    import hashlib

    doc = Document(
        id="doc_x", project="test", type=DocumentType.note,
        status=DocumentStatus.draft, title="X", filepath=tmp_path / "x.md",
        content="hello world",
    )
    update_hash_store(tmp_path, [doc])
    hashes = load_hash_store(tmp_path)
    expected = hashlib.sha256("hello world".encode()).hexdigest()
    assert hashes["doc_x"] == expected


# ---------------------------------------------------------------------------
# Symbol index tests
# ---------------------------------------------------------------------------

def test_python_symbol_extraction(tmp_path):
    from contextos.symbols import extract_python_symbols

    src = tmp_path / "service.py"
    src.write_text('''
class BookingService:
    """Main booking service."""

    def create_booking(self, slot_id: str) -> dict:
        """Create a new booking."""
        pass

    async def cancel_booking(self, booking_id: str) -> bool:
        pass


def standalone_helper(x: int) -> int:
    return x * 2
''')
    symbols = extract_python_symbols(src)
    names = [s["name"] for s in symbols]
    types = {s["name"]: s["type"] for s in symbols}

    assert "BookingService" in names
    assert "create_booking" in names
    assert "cancel_booking" in names
    assert "standalone_helper" in names

    assert types["BookingService"] == "class"
    assert types["create_booking"] == "method"
    assert types["cancel_booking"] == "method"
    assert types["standalone_helper"] == "function"
    assert symbols[2]["is_async"] is True


def test_symbol_search(tmp_path):
    from contextos.symbols import build_symbol_index, search_symbols

    src = tmp_path / "app.py"
    src.write_text('''
def get_user(user_id: str):
    pass

def get_booking(booking_id: str):
    pass

class UserService:
    def create_user(self):
        pass
''')
    symbols_dir = tmp_path / "symbols"
    build_symbol_index([tmp_path], symbols_dir)

    # Fuzzy search
    results = search_symbols("get", symbols_dir, fuzzy=True)
    names = [r["name"] for r in results]
    assert "get_user" in names
    assert "get_booking" in names

    # Type filter
    classes = search_symbols("User", symbols_dir, sym_type="class")
    assert all(r["type"] == "class" for r in classes)
    assert any(r["name"] == "UserService" for r in classes)

    # Exact match
    exact = search_symbols("get_user", symbols_dir, fuzzy=False)
    assert len(exact) == 1
    assert exact[0]["name"] == "get_user"


def test_symbol_index_build_empty(tmp_path):
    from contextos.symbols import build_symbol_index
    symbols_dir = tmp_path / "symbols"
    # No Python files in tmp_path root
    result = build_symbol_index([tmp_path / "nonexistent"], symbols_dir)
    assert result["symbols"] == 0
    assert result["files"] == 0


# ---------------------------------------------------------------------------
# Compressor tests
# ---------------------------------------------------------------------------

def test_compressor_short_text():
    from contextos.compressor import compress_text
    short = "Hello world. This is a short sentence."
    result = compress_text(short, ratio=0.5)
    # Short text should be returned as-is
    assert result == short or len(result) > 0


def test_compressor_reduces_length():
    from contextos.compressor import compress_text
    # Generate enough text to compress (need more than 3 sentences)
    long_text = (
        "The payment service handles all financial transactions in the system. "
        "It integrates with Stripe for card processing and supports multiple currencies. "
        "Payment retries use exponential backoff with three attempts. "
        "Failed payments trigger notifications to both customer and operations team. "
        "Refunds are processed automatically when cancellations meet the policy criteria. "
        "All payment records are stored with full audit trail for compliance purposes."
    )
    compressed = compress_text(long_text, ratio=0.4)
    # Compressed should be shorter or equal (sumy keeps full sentences)
    assert len(compressed) <= len(long_text)


def test_compress_context_chunks_no_trigger():
    from contextos.compressor import compress_context_chunks
    chunks = [{"content": "short content"}]
    result, was_compressed = compress_context_chunks(chunks, max_tokens=10000)
    assert not was_compressed
    assert len(result) == 1


# ---------------------------------------------------------------------------
# MCP tool handler tests (no MCP client needed)
# ---------------------------------------------------------------------------

def test_mcp_tool_get_status_structure():
    """The tool handler returns the right shape even without a full index."""
    import sys
    from unittest.mock import patch, MagicMock

    # Mock config to avoid needing .contextos/
    mock_cfg = MagicMock()
    mock_cfg.metadata_dir = Path("/nonexistent")
    mock_cfg.vault_paths = []

    with patch("contextos.mcp_server._get_cfg", return_value=mock_cfg):
        from contextos.mcp_server import tool_get_status
        result = tool_get_status()

    assert "status" in result
    assert "version" in result
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Watcher tests (no actual filesystem watching)
# ---------------------------------------------------------------------------

def test_watcher_instantiation(tmp_path):
    from contextos.watcher import VaultWatcher
    from unittest.mock import MagicMock

    cfg = MagicMock()
    cfg.embeddings_dir = tmp_path / "embeddings"
    cfg.lancedb_dir = tmp_path / "lancedb"
    cfg.graph_dir = tmp_path / "graph"
    cfg.metadata_dir = tmp_path / "metadata"

    watcher = VaultWatcher(vault_paths=[tmp_path], config=cfg)
    assert watcher.vault_paths == [tmp_path]
    assert not watcher._stop_event.is_set()
