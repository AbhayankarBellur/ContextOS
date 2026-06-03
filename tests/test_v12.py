"""
ContextOS v1.2 tests — session manager, connectors, dashboard, export.
All tests run offline with no network calls.
"""
import json
import time
from pathlib import Path
from typing import Optional
import pytest


# ---------------------------------------------------------------------------
# Session manager tests
# ---------------------------------------------------------------------------

class TestSessionManager:

    def test_create_session(self, tmp_path):
        from contextos.session import create_session, get_session
        sessions_dir = tmp_path / "sessions"
        s = create_session(sessions_dir, name="test-session")

        assert s["id"]
        assert s["name"] == "test-session"
        assert s["started_at"]
        assert s["ended_at"] is None
        assert s["events"] == []

        # Persisted to disk
        loaded = get_session(sessions_dir, s["id"])
        assert loaded is not None
        assert loaded["id"] == s["id"]

    def test_add_event(self, tmp_path):
        from contextos.session import create_session, add_event, get_session
        sessions_dir = tmp_path / "sessions"
        s = create_session(sessions_dir)

        ok = add_event(sessions_dir, s["id"], "task_started", {"task": "fix payment retry"})
        assert ok is True

        loaded = get_session(sessions_dir, s["id"])
        assert len(loaded["events"]) == 1
        assert loaded["events"][0]["type"] == "task_started"
        assert loaded["events"][0]["payload"]["task"] == "fix payment retry"

    def test_end_session_generates_summary(self, tmp_path):
        from contextos.session import create_session, add_event, end_session
        sessions_dir = tmp_path / "sessions"
        s = create_session(sessions_dir, name="summary-test")

        add_event(sessions_dir, s["id"], "task_completed",  {"task": "implement cancellation"})
        add_event(sessions_dir, s["id"], "decision_made",   {"text": "use Stripe refunds"})
        add_event(sessions_dir, s["id"], "search_performed",{"query": "payment retry logic"})
        add_event(sessions_dir, s["id"], "file_changed",    {"filepath": "src/payment.py"})

        ended = end_session(sessions_dir, s["id"])
        assert ended["ended_at"] is not None

        summary = ended["summary"]
        assert "implement cancellation" in summary["tasks_completed"]
        assert "use Stripe refunds"     in summary["decisions"]
        assert "payment retry logic"    in summary["searches"]
        assert "src/payment.py"         in summary["files_changed"]

    def test_cannot_add_event_to_ended_session(self, tmp_path):
        from contextos.session import create_session, end_session, add_event
        sessions_dir = tmp_path / "sessions"
        s = create_session(sessions_dir)
        end_session(sessions_dir, s["id"])

        ok = add_event(sessions_dir, s["id"], "note", {"text": "too late"})
        assert ok is False

    def test_list_sessions(self, tmp_path):
        from contextos.session import create_session, end_session, list_sessions
        sessions_dir = tmp_path / "sessions"

        s1 = create_session(sessions_dir, name="first")
        s2 = create_session(sessions_dir, name="second")
        end_session(sessions_dir, s1["id"])

        sessions = list_sessions(sessions_dir)
        assert len(sessions) == 2

    def test_get_last_session(self, tmp_path):
        from contextos.session import create_session, end_session, get_last_session
        sessions_dir = tmp_path / "sessions"

        s1 = create_session(sessions_dir, name="old")
        time.sleep(0.01)
        s2 = create_session(sessions_dir, name="recent")
        end_session(sessions_dir, s1["id"])
        end_session(sessions_dir, s2["id"])

        last = get_last_session(sessions_dir)
        assert last is not None
        assert last["ended_at"] is not None

    def test_export_to_vault(self, tmp_path):
        from contextos.session import create_session, add_event, end_session
        sessions_dir = tmp_path / "sessions"
        vault_dir    = tmp_path / "vault" / "context"

        s = create_session(sessions_dir, name="export-test")
        add_event(sessions_dir, s["id"], "task_completed", {"task": "built the feature"})
        ended = end_session(sessions_dir, s["id"], vault_export_dir=vault_dir)

        # Vault file should exist
        vault_files = list(vault_dir.glob("session-*.md"))
        assert len(vault_files) == 1

        content = vault_files[0].read_text()
        assert "export-test" in content
        assert "built the feature" in content
        assert "project: contextos" in content

    def test_session_not_found_raises(self, tmp_path):
        from contextos.session import end_session
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)
        with pytest.raises(ValueError):
            end_session(sessions_dir, "nonexistent-id")

    def test_active_session_detection(self, tmp_path):
        from contextos.session import create_session, get_active_session, end_session
        sessions_dir = tmp_path / "sessions"

        # No active session initially
        assert get_active_session(sessions_dir) is None

        s = create_session(sessions_dir, name="active")
        active = get_active_session(sessions_dir)
        assert active is not None
        assert active["id"] == s["id"]

        end_session(sessions_dir, s["id"])
        assert get_active_session(sessions_dir) is None

    def test_log_helpers(self, tmp_path):
        from contextos.session import create_session, log_search, log_context, log_file_read, get_session
        sessions_dir = tmp_path / "sessions"
        s = create_session(sessions_dir)

        log_search(sessions_dir, s["id"], "payment retry", 5)
        log_context(sessions_dir, s["id"], "implement feature", 1200)
        log_file_read(sessions_dir, s["id"], "src/payment.py")

        loaded = get_session(sessions_dir, s["id"])
        types = [e["type"] for e in loaded["events"]]
        assert "search_performed"   in types
        assert "context_retrieved"  in types
        assert "file_read"          in types


# ---------------------------------------------------------------------------
# Connector base tests
# ---------------------------------------------------------------------------

class TestBaseConnector:

    def test_connector_result_hash(self):
        from contextos.connectors.base import ConnectorResult
        r = ConnectorResult(filename="test.md", content="# Hello\n\nWorld.")
        assert len(r.content_hash) == 64  # SHA-256 hex

    def test_write_creates_files(self, tmp_path):
        from contextos.connectors.base import ConnectorResult, BaseConnector

        class MockConnector(BaseConnector):
            name = "mock"
            def fetch(self): return []

        conn = MockConnector(project="test")
        results = [
            ConnectorResult(filename="doc1.md", content="# Doc 1\n\nContent."),
            ConnectorResult(filename="doc2.md", content="# Doc 2\n\nContent."),
        ]
        written, skipped, total = conn.write(results, tmp_path)
        assert written == 2
        assert skipped == 0
        assert total == 2
        assert (tmp_path / "doc1.md").exists()
        assert (tmp_path / "doc2.md").exists()

    def test_write_idempotent(self, tmp_path):
        from contextos.connectors.base import ConnectorResult, BaseConnector

        class MockConnector(BaseConnector):
            name = "mock"
            def fetch(self): return []

        conn = MockConnector(project="test")
        results = [ConnectorResult(filename="doc.md", content="# Same content")]

        # First write
        written1, skipped1, _ = conn.write(results, tmp_path)
        # Second write — same content, should skip
        written2, skipped2, _ = conn.write(results, tmp_path)

        assert written1 == 1
        assert skipped2 == 1  # idempotent
        assert written2 == 0

    def test_write_force_overwrites(self, tmp_path):
        from contextos.connectors.base import ConnectorResult, BaseConnector

        class MockConnector(BaseConnector):
            name = "mock"
            def fetch(self): return []

        conn = MockConnector(project="test")
        results = [ConnectorResult(filename="doc.md", content="# Same")]

        conn.write(results, tmp_path)
        written, skipped, _ = conn.write(results, tmp_path, force=True)
        assert written == 1
        assert skipped == 0

    def test_frontmatter_generation(self):
        from contextos.connectors.base import BaseConnector

        class MockConnector(BaseConnector):
            name = "mock"
            def fetch(self): return []

        conn = MockConnector(project="test")
        fm = conn._frontmatter({
            "project": "test",
            "type": "note",
            "tags": ["a", "b"],
        })
        assert fm.startswith("---")
        assert "project: test" in fm
        assert "type: note" in fm
        assert "  - a" in fm


# ---------------------------------------------------------------------------
# OpenAPI connector tests
# ---------------------------------------------------------------------------

class TestOpenAPIConnector:

    def _write_spec(self, tmp_path: Path, spec: dict) -> Path:
        p = tmp_path / "openapi.json"
        p.write_text(json.dumps(spec))
        return p

    def _minimal_spec(self) -> dict:
        return {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0",
                     "description": "A test API"},
            "paths": {
                "/users": {
                    "get": {
                        "tags": ["users"],
                        "summary": "List users",
                        "parameters": [
                            {"name": "limit", "in": "query", "schema": {"type": "integer"}}
                        ],
                        "responses": {"200": {"description": "OK"}}
                    }
                },
                "/users/{id}": {
                    "get": {
                        "tags": ["users"],
                        "summary": "Get user",
                        "responses": {"200": {"description": "OK"}, "404": {"description": "Not found"}}
                    }
                },
                "/payments": {
                    "post": {
                        "tags": ["payments"],
                        "summary": "Create payment",
                        "responses": {"201": {"description": "Created"}}
                    }
                }
            },
            "components": {
                "schemas": {
                    "User": {
                        "description": "A user object",
                        "properties": {
                            "id":    {"type": "string"},
                            "email": {"type": "string", "description": "User email"},
                        }
                    }
                }
            }
        }

    def test_fetch_from_file(self, tmp_path):
        from contextos.connectors.openapi import OpenAPIConnector
        spec_path = self._write_spec(tmp_path, self._minimal_spec())
        conn = OpenAPIConnector(project="test", config={"source": str(spec_path)})
        results = conn.fetch()

        filenames = [r.filename for r in results]
        assert "api-overview.md" in filenames
        assert "api-users.md" in filenames
        assert "api-payments.md" in filenames
        assert "api-schemas.md" in filenames

    def test_overview_content(self, tmp_path):
        from contextos.connectors.openapi import OpenAPIConnector
        spec_path = self._write_spec(tmp_path, self._minimal_spec())
        conn = OpenAPIConnector(project="test", config={"source": str(spec_path)})
        results = conn.fetch()

        overview = next(r for r in results if r.filename == "api-overview.md")
        assert "Test API" in overview.content
        assert "Endpoints:" in overview.content
        assert "project: test" in overview.content

    def test_tag_doc_content(self, tmp_path):
        from contextos.connectors.openapi import OpenAPIConnector
        spec_path = self._write_spec(tmp_path, self._minimal_spec())
        conn = OpenAPIConnector(project="test", config={"source": str(spec_path)})
        results = conn.fetch()

        users_doc = next(r for r in results if r.filename == "api-users.md")
        assert "GET /users" in users_doc.content
        assert "List users" in users_doc.content
        assert "limit" in users_doc.content

    def test_schemas_doc(self, tmp_path):
        from contextos.connectors.openapi import OpenAPIConnector
        spec_path = self._write_spec(tmp_path, self._minimal_spec())
        conn = OpenAPIConnector(project="test", config={"source": str(spec_path)})
        results = conn.fetch()

        schemas = next(r for r in results if r.filename == "api-schemas.md")
        assert "User" in schemas.content
        assert "email" in schemas.content

    def test_write_to_output(self, tmp_path):
        from contextos.connectors.openapi import OpenAPIConnector
        spec_file = tmp_path / "openapi.json"   # file in tmp_path directly
        spec_file.write_text(json.dumps(self._minimal_spec()))
        out_dir = tmp_path / "out"
        conn = OpenAPIConnector(project="test", config={"source": str(spec_file)})
        result = conn.pull(out_dir)
        assert result["written"] >= 4
        assert (out_dir / "api-overview.md").exists()

    def test_missing_spec_returns_empty(self, tmp_path):
        """Missing spec logs an error and returns empty list (does not raise)."""
        from contextos.connectors.openapi import OpenAPIConnector
        conn = OpenAPIConnector(project="test", config={"source": str(tmp_path / "missing.json")})
        results = conn.fetch()
        assert results == []

    def test_no_source_raises(self):
        from contextos.connectors.openapi import OpenAPIConnector
        conn = OpenAPIConnector(project="test", config={})
        with pytest.raises(ValueError):
            conn.fetch()


# ---------------------------------------------------------------------------
# JSON connector tests
# ---------------------------------------------------------------------------

class TestJSONConnector:

    def test_generic_json(self, tmp_path):
        from contextos.connectors.json_source import JSONConnector
        data_file = tmp_path / "config.json"
        data_file.write_text(json.dumps({"key1": "value1", "key2": 42, "nested": {"a": 1}}))

        conn = JSONConnector(project="test", config={"source": str(data_file)})
        results = conn.fetch()
        assert len(results) == 1
        assert "config.json" in results[0].content
        assert "key1" in results[0].content

    def test_package_json(self, tmp_path):
        from contextos.connectors.json_source import JSONConnector
        pkg = {
            "name": "my-app", "version": "2.0.0",
            "description": "Test app",
            "scripts": {"start": "node index.js", "test": "jest"},
            "dependencies": {"express": "^4.18.0", "axios": "^1.0.0"},
        }
        pkg_file = tmp_path / "package.json"
        pkg_file.write_text(json.dumps(pkg))

        conn = JSONConnector(project="test", config={"source": str(pkg_file)})
        results = conn.fetch()
        assert len(results) == 1
        content = results[0].content
        assert "my-app" in content
        assert "express" in content
        assert "Scripts" in content

    def test_yaml_source(self, tmp_path):
        from contextos.connectors.json_source import JSONConnector
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text("database:\n  host: localhost\n  port: 5432\n")

        conn = JSONConnector(project="test", config={"source": str(yaml_file)})
        results = conn.fetch()
        assert len(results) == 1
        assert "database" in results[0].content

    def test_missing_source_raises(self, tmp_path):
        from contextos.connectors.json_source import JSONConnector
        conn = JSONConnector(project="test", config={"source": str(tmp_path / "missing.json")})
        with pytest.raises(FileNotFoundError):
            conn.fetch()

    def test_no_source_raises(self):
        from contextos.connectors.json_source import JSONConnector
        conn = JSONConnector(project="test", config={})
        with pytest.raises(ValueError):
            conn.fetch()


# ---------------------------------------------------------------------------
# Connector registry tests
# ---------------------------------------------------------------------------

def test_connector_registry():
    from contextos.connectors import CONNECTORS
    assert "github"  in CONNECTORS
    assert "openapi" in CONNECTORS
    assert "json"    in CONNECTORS


def test_connector_instantiation():
    from contextos.connectors import GitHubConnector, OpenAPIConnector, JSONConnector
    for cls in (GitHubConnector, OpenAPIConnector, JSONConnector):
        c = cls(project="test", config={})
        assert c.project == "test"
        assert c.name


# ---------------------------------------------------------------------------
# Dashboard import test (no UI — just verify module loads)
# ---------------------------------------------------------------------------

def test_dashboard_imports():
    """Dashboard module should import cleanly even without Textual."""
    import importlib
    mod = importlib.import_module("contextos.dashboard")
    assert hasattr(mod, "run_dashboard")
    assert hasattr(mod, "_get_system_data")


def test_dashboard_system_data(tmp_path):
    """_get_system_data should return a complete dict even with empty dirs."""
    from contextos.dashboard import _get_system_data
    from unittest.mock import MagicMock

    cfg = MagicMock()
    cfg.port = 8080
    cfg.metadata_dir = tmp_path / "metadata"
    cfg.graph_dir    = tmp_path / "graph"
    cfg.contextos_dir= tmp_path
    cfg.lancedb_dir  = tmp_path / "lancedb"
    cfg.embeddings_dir = tmp_path / "embeddings"
    cfg.vault_paths  = []

    # Create dirs so memory scan doesn't fail
    for d in [cfg.metadata_dir, cfg.graph_dir, cfg.lancedb_dir, cfg.embeddings_dir]:
        d.mkdir(parents=True, exist_ok=True)

    data = _get_system_data(cfg)
    assert "server"      in data
    assert "documents"   in data
    assert "graph_nodes" in data
    assert "disk_mb"     in data
    assert "projects"    in data
    assert "sessions"    in data


# ---------------------------------------------------------------------------
# Export command test
# ---------------------------------------------------------------------------

def test_export_markdown(tmp_path):
    """Test the export logic directly."""
    from contextos.vault import write_registry, scan_vault

    # Create a minimal vault
    vault = tmp_path / "vault"
    vault.mkdir()
    doc = vault / "arch.md"
    doc.write_text("---\nproject: my-app\ntype: architecture\nstatus: approved\n---\n# Backend\n\nContent here.")

    docs = scan_vault(vault)
    metadata_dir = tmp_path / ".contextos" / "metadata"
    metadata_dir.mkdir(parents=True)
    write_registry(docs, metadata_dir)

    from contextos.vault import load_registry
    registry = load_registry(metadata_dir)
    project_docs = [r for r in registry if r.get("project") == "my-app"]
    assert len(project_docs) == 1

    # Simulate export
    out_path = tmp_path / "export.md"
    lines = [f"# my-app — Vault Export\n\n---\n"]
    for rec in project_docs:
        fp = Path(rec["filepath"])
        if fp.exists():
            content = fp.read_text()
            if content.startswith("---"):
                parts = content.split("---", 2)
                content = parts[2].strip() if len(parts) >= 3 else content
            lines.append(f"\n## {rec['title']}\n\n{content}\n\n---")
    out_path.write_text("\n".join(lines))

    assert out_path.exists()
    assert "Backend" in out_path.read_text()
    assert "Content here" in out_path.read_text()
