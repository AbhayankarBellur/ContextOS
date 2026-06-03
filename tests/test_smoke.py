"""
ContextOS smoke tests — verify core modules import and basic logic works.
No network calls. No file system side effects outside of tmp_path.
"""
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

def test_schema_imports():
    from contextos.schema import (
        Document, Chunk, GraphNode, GraphEdge, Token,
        DocumentType, DocumentStatus, EdgeType,
    )
    assert DocumentType.architecture.value == "architecture"
    assert DocumentStatus.approved.value == "approved"
    assert EdgeType.depends_on.value == "depends_on"


def test_document_model():
    from contextos.schema import Document, DocumentType, DocumentStatus
    doc = Document(
        id="abc123",
        project="test-project",
        type=DocumentType.architecture,
        status=DocumentStatus.approved,
        title="Test Doc",
        filepath=Path("/tmp/test.md"),
        content="# Test\n\nHello world.",
        tags=["test", "architecture"],
    )
    assert doc.id == "abc123"
    assert doc.type == DocumentType.architecture
    assert doc.tags == ["test", "architecture"]


def test_chunk_model():
    from contextos.schema import Chunk
    chunk = Chunk(
        id="chunk1",
        doc_id="doc1",
        heading="Overview",
        content="Some content here.",
        token_count=4,
    )
    assert chunk.embedding == []
    assert chunk.token_count == 4


def test_token_model():
    from datetime import datetime, timezone
    from contextos.schema import Token
    token = Token(
        id="ctx_abc123",
        name="test",
        hash=hashlib.sha256(b"raw").hexdigest(),
        created_at=datetime.now(timezone.utc),
    )
    assert token.id.startswith("ctx_")
    assert token.revoked is False


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

def test_config_defaults(tmp_path):
    from contextos.config import Config
    cfg = Config(root=tmp_path)
    assert cfg.port == 8080
    assert cfg.embedding_model == "BAAI/bge-small-en-v1.5"
    assert cfg.contextos_dir == tmp_path / ".contextos"


def test_config_save_load(tmp_path):
    from contextos.config import Config, save_config, load_config
    cfg = Config(root=tmp_path, project_name="my-test", port=9000)
    (tmp_path / ".contextos").mkdir()
    save_config(cfg)
    loaded = load_config(tmp_path)
    assert loaded.project_name == "my-test"
    assert loaded.port == 9000


# ---------------------------------------------------------------------------
# Vault tests
# ---------------------------------------------------------------------------

def test_vault_scan(tmp_path):
    from contextos.vault import scan_vault, write_registry
    # Create a minimal vault
    vault = tmp_path / "vault"
    vault.mkdir()
    md = vault / "test.md"
    md.write_text("---\nproject: test\ntype: note\nstatus: draft\n---\n# Hello\n\nWorld.")

    docs = scan_vault(vault)
    assert len(docs) == 1
    assert docs[0].project == "test"
    assert docs[0].title == "Hello"


def test_vault_missing_frontmatter(tmp_path):
    from contextos.vault import scan_vault
    vault = tmp_path / "vault"
    vault.mkdir()
    md = vault / "plain.md"
    md.write_text("# Just a heading\n\nNo frontmatter here.")

    docs = scan_vault(vault)
    assert len(docs) == 1
    assert docs[0].title == "Just a heading"


# ---------------------------------------------------------------------------
# Chunker tests
# ---------------------------------------------------------------------------

def test_chunker_basic(tmp_path):
    from contextos.schema import Document, DocumentType, DocumentStatus
    from contextos.chunker import chunk_document

    doc = Document(
        id="doc1",
        project="test",
        type=DocumentType.architecture,
        status=DocumentStatus.approved,
        title="Architecture Overview",
        filepath=tmp_path / "arch.md",
        content="# Architecture Overview\n\n## Layer 1\n\nThe vault layer stores files.\n\n## Layer 2\n\nThe index layer handles embeddings.",
    )
    chunks = chunk_document(doc)
    assert len(chunks) >= 1
    assert all(c.doc_id == "doc1" for c in chunks)
    assert all(c.embedding == [] for c in chunks)  # embeddings not filled yet


def test_chunker_no_headers(tmp_path):
    from contextos.schema import Document, DocumentType, DocumentStatus
    from contextos.chunker import chunk_document

    doc = Document(
        id="doc2",
        project="test",
        type=DocumentType.note,
        status=DocumentStatus.draft,
        title="Plain Note",
        filepath=tmp_path / "note.md",
        content="Just some plain text with no headers. " * 20,
    )
    chunks = chunk_document(doc)
    assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

def test_token_generate_and_validate(tmp_path):
    from contextos.auth import generate_token, validate_token

    tokens_dir = tmp_path / "tokens"
    tokens_dir.mkdir()

    raw, token = generate_token("test-agent", tokens_dir)

    # Raw token starts with ctx_
    assert raw.startswith("ctx_")
    assert token.name == "test-agent"
    assert token.revoked is False

    # Validate works
    validated = validate_token(raw, tokens_dir)
    assert validated is not None
    assert validated.name == "test-agent"

    # Wrong token returns None
    assert validate_token("ctx_wrongtoken", tokens_dir) is None


def test_token_revoke(tmp_path):
    from contextos.auth import generate_token, validate_token, revoke_token

    tokens_dir = tmp_path / "tokens"
    tokens_dir.mkdir()

    raw, token = generate_token("revoke-test", tokens_dir)
    assert validate_token(raw, tokens_dir) is not None

    revoke_token(token.id, tokens_dir)
    assert validate_token(raw, tokens_dir) is None


def test_token_list(tmp_path):
    from contextos.auth import generate_token, list_tokens

    tokens_dir = tmp_path / "tokens"
    tokens_dir.mkdir()

    generate_token("token-a", tokens_dir)
    generate_token("token-b", tokens_dir)

    tokens = list_tokens(tokens_dir)
    assert len(tokens) == 2
    names = {t.name for t in tokens}
    assert "token-a" in names
    assert "token-b" in names


# ---------------------------------------------------------------------------
# Memory tests
# ---------------------------------------------------------------------------

def test_memory_disk_breakdown(tmp_path):
    from contextos.memory import get_disk_breakdown
    ctx_dir = tmp_path / ".contextos"
    for sub in ["lancedb", "embeddings", "graph", "cache", "tokens", "metadata", "logs"]:
        (ctx_dir / sub).mkdir(parents=True)
    # Write a small file
    (ctx_dir / "cache" / "test.json").write_text("{}")

    bd = get_disk_breakdown(ctx_dir)
    assert "_total" in bd
    assert bd["_total"]["size_bytes"] > 0
    assert "cache" in bd


def test_memory_reset(tmp_path):
    from contextos.memory import reset_index
    ctx_dir = tmp_path / ".contextos"
    for sub in ["lancedb", "graph", "cache", "metadata", "logs", "tokens", "embeddings"]:
        (ctx_dir / sub).mkdir(parents=True)
    (ctx_dir / "cache" / "data.json").write_text('{"test": 1}')
    (ctx_dir / "tokens" / "tok1.json").write_text('{"id": "ctx_x"}')

    result = reset_index(ctx_dir, keep_tokens=True)
    assert result["freed_bytes"] >= 0
    # Tokens preserved
    assert (ctx_dir / "tokens" / "tok1.json").exists()
    # Cache wiped
    assert not any((ctx_dir / "cache").iterdir())
