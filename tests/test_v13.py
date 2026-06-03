"""
ContextOS v1.3 tests — logger, auth scopes, cache, plugins, scaffolder, CI.
All offline. No network calls.
"""
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
import pytest


# ---------------------------------------------------------------------------
# T1 — Structured Logger
# ---------------------------------------------------------------------------

class TestStructuredLogger:

    def test_log_request_creates_file(self, tmp_path):
        from contextos.logger import StructuredLogger
        lg = StructuredLogger(tmp_path)
        lg.log_request("req_001", "/search", "POST", 42, "ctx_abc", 200)
        assert (tmp_path / "app.jsonl").exists()
        records = [json.loads(l) for l in (tmp_path/"app.jsonl").read_text().splitlines()]
        assert records[0]["endpoint"] == "/search"
        assert records[0]["latency_ms"] == 42

    def test_slow_query_written_to_slow_log(self, tmp_path):
        from contextos.logger import StructuredLogger, SLOW_QUERY_MS
        lg = StructuredLogger(tmp_path)
        lg.log_request("req_slow", "/context", "POST", SLOW_QUERY_MS + 100, "ctx_x", 200)
        assert (tmp_path / "slow.jsonl").exists()

    def test_fast_query_not_in_slow_log(self, tmp_path):
        from contextos.logger import StructuredLogger
        lg = StructuredLogger(tmp_path)
        lg.log_request("req_fast", "/health", "GET", 10, None, 200)
        assert not (tmp_path / "slow.jsonl").exists()

    def test_audit_log(self, tmp_path):
        from contextos.logger import StructuredLogger
        lg = StructuredLogger(tmp_path)
        lg.log_audit("req_x", "ctx_id", "agent", "/search", "POST", 50, "read")
        records = lg.read_audit()
        assert len(records) == 1
        assert records[0]["token_name"] == "agent"

    def test_index_op_log(self, tmp_path):
        from contextos.logger import StructuredLogger
        lg = StructuredLogger(tmp_path)
        lg.log_index_op("full_index", 10, 150, 3.5, "my-project")
        records = lg.tail_log()
        types = [r["type"] for r in records]
        assert "index_op" in types

    def test_metrics_accumulate(self, tmp_path):
        from contextos.logger import StructuredLogger
        lg = StructuredLogger(tmp_path)
        lg.log_request("r1", "/search", "POST", 100, None, 200)
        lg.log_request("r2", "/context", "POST", 200, None, 200)
        lg.log_request("r3", "/search", "POST", 50, None, 500)
        metrics = lg.get_metrics()
        assert metrics["total_requests"] == 3
        assert metrics["errors"] == 1
        assert metrics["avg_latency_ms"] == 116  # (100+200+50)//3

    def test_tail_log_limit(self, tmp_path):
        from contextos.logger import StructuredLogger
        lg = StructuredLogger(tmp_path)
        for i in range(20):
            lg.log_request(f"req_{i}", "/health", "GET", 5, None, 200)
        records = lg.tail_log(lines=5)
        assert len(records) == 5

    def test_new_request_id_format(self):
        from contextos.logger import new_request_id
        rid = new_request_id()
        assert rid.startswith("req_")
        assert len(rid) == 12  # req_ + 8 hex chars

    def test_log_rotation(self, tmp_path):
        from contextos.logger import StructuredLogger, MAX_LOG_BYTES, _rotate
        lg = StructuredLogger(tmp_path)
        log_file = tmp_path / "app.jsonl"
        # Write enough to trigger rotation
        big_record = {"data": "x" * 1000}
        for _ in range(100):
            log_file.parent.mkdir(exist_ok=True)
            with open(log_file, "a") as f:
                f.write(json.dumps(big_record) + "\n")
        # Simulate rotation threshold
        if log_file.stat().st_size > 0:
            _rotate(log_file)
            assert (tmp_path / "app.1.jsonl").exists()


# ---------------------------------------------------------------------------
# T2+T3 — Token Scopes and Auth
# ---------------------------------------------------------------------------

class TestTokenScopes:

    def test_scope_hierarchy_admin_allows_all(self):
        from contextos.schema import TokenScope
        assert TokenScope.allows(TokenScope.admin, TokenScope.read)
        assert TokenScope.allows(TokenScope.admin, TokenScope.write)
        assert TokenScope.allows(TokenScope.admin, TokenScope.admin)

    def test_scope_hierarchy_write_allows_read(self):
        from contextos.schema import TokenScope
        assert TokenScope.allows(TokenScope.write, TokenScope.read)
        assert TokenScope.allows(TokenScope.write, TokenScope.write)
        assert not TokenScope.allows(TokenScope.write, TokenScope.admin)

    def test_scope_hierarchy_read_only(self):
        from contextos.schema import TokenScope
        assert TokenScope.allows(TokenScope.read, TokenScope.read)
        assert not TokenScope.allows(TokenScope.read, TokenScope.write)
        assert not TokenScope.allows(TokenScope.read, TokenScope.admin)

    def test_generate_token_with_scope(self, tmp_path):
        from contextos.auth import generate_token
        from contextos.schema import TokenScope
        tokens_dir = tmp_path / "tokens"
        tokens_dir.mkdir()
        raw, token = generate_token("ci-agent", tokens_dir, scope=TokenScope.read)
        assert token.scope == TokenScope.read
        assert raw.startswith("ctx_")

    def test_generate_token_with_expiry(self, tmp_path):
        from contextos.auth import generate_token
        from contextos.schema import TokenScope
        tokens_dir = tmp_path / "tokens"
        tokens_dir.mkdir()
        raw, token = generate_token("temp-token", tokens_dir,
                                     scope=TokenScope.write, expires_days=30)
        assert token.expires_at is not None
        assert not token.is_expired()

    def test_expired_token_returns_none(self, tmp_path):
        from contextos.auth import generate_token, validate_token
        from contextos.schema import TokenScope
        import json as _json

        tokens_dir = tmp_path / "tokens"
        tokens_dir.mkdir()
        raw, token = generate_token("old-token", tokens_dir, scope=TokenScope.read, expires_days=1)

        # Manually set expiry to the past
        token_file = tokens_dir / f"{token.id}.json"
        data = _json.loads(token_file.read_text())
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        data["expires_at"] = past
        token_file.write_text(_json.dumps(data))

        result = validate_token(raw, tokens_dir)
        assert result is None  # expired

    def test_token_has_scope_check(self, tmp_path):
        from contextos.auth import generate_token
        from contextos.schema import TokenScope
        tokens_dir = tmp_path / "tokens"
        tokens_dir.mkdir()
        _, read_token = generate_token("reader", tokens_dir, scope=TokenScope.read)
        assert read_token.has_scope(TokenScope.read)
        assert not read_token.has_scope(TokenScope.write)

    def test_rate_limit_allows_under_limit(self, tmp_path):
        from contextos.auth import generate_token, check_rate_limit
        from contextos.schema import TokenScope
        tokens_dir = tmp_path / "tokens"
        tokens_dir.mkdir()
        raw, token = generate_token("rate-test", tokens_dir)
        # Should allow 10 requests under limit of 1000
        for _ in range(10):
            assert check_rate_limit(token, tokens_dir, limit=1000) is True

    def test_rate_limit_blocks_over_limit(self, tmp_path):
        from contextos.auth import generate_token, check_rate_limit
        from contextos.schema import TokenScope
        tokens_dir = tmp_path / "tokens"
        tokens_dir.mkdir()
        raw, token = generate_token("rate-block", tokens_dir)
        # Allow 5, then block at limit=5
        for _ in range(5):
            check_rate_limit(token, tokens_dir, limit=5)
        result = check_rate_limit(token, tokens_dir, limit=5)
        assert result is False  # over limit

    def test_request_count_increments(self, tmp_path):
        from contextos.auth import generate_token, validate_token
        from contextos.schema import TokenScope
        import json as _json
        tokens_dir = tmp_path / "tokens"
        tokens_dir.mkdir()
        raw, token = generate_token("counter", tokens_dir)
        validate_token(raw, tokens_dir)
        validate_token(raw, tokens_dir)
        # Read token file directly
        token_file = tokens_dir / f"{token.id}.json"
        data = _json.loads(token_file.read_text())
        assert data["request_count"] >= 2

    def test_token_scope_persisted(self, tmp_path):
        from contextos.auth import generate_token, validate_token
        from contextos.schema import TokenScope
        tokens_dir = tmp_path / "tokens"
        tokens_dir.mkdir()
        raw, _ = generate_token("scoped", tokens_dir, scope=TokenScope.admin)
        loaded = validate_token(raw, tokens_dir)
        assert loaded.scope == TokenScope.admin


# ---------------------------------------------------------------------------
# T5 — Context Cache
# ---------------------------------------------------------------------------

class TestContextCache:

    def _make_response(self, text="test context"):
        from contextos.schema import ContextResponse
        return ContextResponse(context=text, sources=[], token_estimate=100)

    def test_miss_returns_none(self):
        from contextos.cache_layer import ContextCache
        cache = ContextCache()
        assert cache.get("nonexistent") is None

    def test_set_and_get(self):
        from contextos.cache_layer import ContextCache
        cache = ContextCache()
        resp = self._make_response()
        cache.set("key1", resp)
        result = cache.get("key1")
        assert result is not None
        assert result.context == "test context"

    def test_ttl_expiry(self):
        from contextos.cache_layer import ContextCache
        cache = ContextCache(ttl_seconds=1)
        cache.set("expiring", self._make_response())
        assert cache.get("expiring") is not None
        time.sleep(1.1)
        assert cache.get("expiring") is None  # expired

    def test_lru_eviction(self):
        from contextos.cache_layer import ContextCache
        cache = ContextCache(max_size=3)
        cache.set("a", self._make_response("a"))
        cache.set("b", self._make_response("b"))
        cache.set("c", self._make_response("c"))
        # Access 'a' to make it recent
        cache.get("a")
        # Add 'd' — should evict 'b' (oldest unaccessed)
        cache.set("d", self._make_response("d"))
        assert cache.get("b") is None
        assert cache.get("a") is not None
        assert cache.get("d") is not None

    def test_invalidate_clears_all(self):
        from contextos.cache_layer import ContextCache
        cache = ContextCache()
        cache.set("x", self._make_response())
        cache.set("y", self._make_response())
        count = cache.invalidate()
        assert count == 2
        assert len(cache) == 0

    def test_stats_hit_rate(self):
        from contextos.cache_layer import ContextCache
        cache = ContextCache()
        cache.set("k", self._make_response())
        cache.get("k")   # hit
        cache.get("k")   # hit
        cache.get("miss") # miss
        stats = cache.stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate_pct"] == 66.7

    def test_make_key_deterministic(self):
        from contextos.cache_layer import ContextCache
        k1 = ContextCache.make_key("payment retry", "my-project", 4000)
        k2 = ContextCache.make_key("payment retry", "my-project", 4000)
        k3 = ContextCache.make_key("different query", "my-project", 4000)
        assert k1 == k2
        assert k1 != k3

    def test_make_key_case_insensitive_query(self):
        from contextos.cache_layer import ContextCache
        k1 = ContextCache.make_key("Payment Retry", "proj", 4000)
        k2 = ContextCache.make_key("payment retry", "proj", 4000)
        assert k1 == k2

    def test_thread_safety(self):
        from contextos.cache_layer import ContextCache
        import threading
        cache = ContextCache(max_size=100)
        errors = []

        def writer(i):
            try:
                cache.set(f"key_{i}", self._make_response(f"val_{i}"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors


# ---------------------------------------------------------------------------
# T4 — Plugin System
# ---------------------------------------------------------------------------

class TestPluginSystem:

    def test_builtin_connectors_in_registry(self):
        from contextos.plugins import build_registry
        registry = build_registry()
        assert "github"  in registry
        assert "openapi" in registry
        assert "json"    in registry

    def test_scan_empty_dir_returns_builtins(self, tmp_path):
        from contextos.plugins import scan_plugins
        # With no custom plugin dirs, should still return builtins
        plugins = scan_plugins()
        names = [p.name for p in plugins]
        assert "github"  in names
        assert "openapi" in names

    def test_load_custom_connector(self, tmp_path):
        from contextos.plugins import _scan_directory
        # Write a minimal connector plugin
        plugin_file = tmp_path / "my_connector.py"
        plugin_file.write_text("""
from contextos.connectors.base import BaseConnector, ConnectorResult

class MyConnector(BaseConnector):
    name = "my_connector"
    description = "Test connector"

    def fetch(self):
        return [ConnectorResult(filename="test.md", content="# Test")]
""")
        plugins = _scan_directory(tmp_path, "test")
        assert len(plugins) == 1
        assert plugins[0].name == "my_connector"
        assert plugins[0].source == "test"

    def test_invalid_plugin_skipped(self, tmp_path):
        from contextos.plugins import _scan_directory
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("this is not valid python !!!")
        # Should not raise, just skip
        plugins = _scan_directory(tmp_path, "test")
        assert plugins == []

    def test_plugin_meta_fields(self, tmp_path):
        from contextos.plugins import _scan_directory
        plugin_file = tmp_path / "full_connector.py"
        plugin_file.write_text("""
from contextos.connectors.base import BaseConnector, ConnectorResult

class FullConnector(BaseConnector):
    name = "full_connector"
    description = "A full test connector"
    version = "2.0.0"

    def fetch(self):
        return []
""")
        plugins = _scan_directory(tmp_path, "local")
        assert plugins[0].description == "A full test connector"
        assert plugins[0].source == "local"


# ---------------------------------------------------------------------------
# T6 — Vault Scaffolder
# ---------------------------------------------------------------------------

class TestVaultScaffolder:

    def test_scaffold_default_template(self, tmp_path):
        from contextos.scaffolder import scaffold_vault
        target = tmp_path / "my-vault"
        created = scaffold_vault(target, template_name="default", variables={
            "project_name": "test-project",
            "team": "eng",
            "domain_name": "core",
        })
        assert len(created) > 0
        assert target.exists()
        # Check a file was created
        assert any(f.suffix == ".md" for f in created)

    def test_scaffold_microservice_template(self, tmp_path):
        from contextos.scaffolder import scaffold_vault
        target = tmp_path / "my-service"
        created = scaffold_vault(target, template_name="microservice", variables={
            "project_name": "payments-service",
            "team": "platform",
        })
        assert len(created) > 0

    def test_scaffold_api_first_template(self, tmp_path):
        from contextos.scaffolder import scaffold_vault
        target = tmp_path / "my-api"
        created = scaffold_vault(target, template_name="api-first", variables={
            "project_name": "booking-api",
            "team": "backend",
        })
        assert len(created) > 0

    def test_interpolation(self, tmp_path):
        from contextos.scaffolder import scaffold_vault
        target = tmp_path / "vault"
        scaffold_vault(target, template_name="default", variables={
            "project_name": "MYPROJECT",
            "team": "MYTEAM",
            "domain_name": "core",
        })
        # Any created file should have interpolated content
        for md_file in target.rglob("*.md"):
            content = md_file.read_text()
            assert "{{project_name}}" not in content
            if "MYPROJECT" in content or "MYTEAM" in content:
                break

    def test_scaffold_idempotent(self, tmp_path):
        from contextos.scaffolder import scaffold_vault
        target = tmp_path / "vault"
        vars_ = {"project_name": "p", "team": "t", "domain_name": "d"}
        created1 = scaffold_vault(target, variables=vars_)
        created2 = scaffold_vault(target, variables=vars_)
        # Second run should create nothing (files exist)
        assert len(created2) == 0

    def test_unknown_template_raises(self, tmp_path):
        from contextos.scaffolder import scaffold_vault
        with pytest.raises(ValueError, match="not found"):
            scaffold_vault(tmp_path / "x", template_name="nonexistent")

    def test_validate_vault_clean(self, tmp_path):
        from contextos.scaffolder import validate_vault
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "arch.md").write_text(
            "---\nproject: test\ntype: architecture\nstatus: approved\nupdated_at: 2026-01-01\ntags:\n  - test\n---\n# Arch\n"
        )
        result = validate_vault(vault)
        assert result["errors"] == []
        assert result["valid"] == 1

    def test_validate_vault_missing_fields(self, tmp_path):
        from contextos.scaffolder import validate_vault
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "bad.md").write_text("# No frontmatter at all")
        result = validate_vault(vault)
        assert len(result["errors"]) > 0

    def test_validate_vault_warns_missing_optional(self, tmp_path):
        from contextos.scaffolder import validate_vault
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "minimal.md").write_text(
            "---\nproject: test\ntype: note\nstatus: draft\n---\n# Minimal\n"
        )
        result = validate_vault(vault)
        assert result["errors"] == []
        # Should warn about missing updated_at and tags
        assert len(result["warnings"]) > 0

    def test_list_templates_includes_builtins(self):
        from contextos.scaffolder import list_templates
        templates = list_templates()
        assert "default"      in templates
        assert "microservice" in templates
        assert "api-first"    in templates


# ---------------------------------------------------------------------------
# T7 — CI Mode
# ---------------------------------------------------------------------------

class TestCIMode:

    def test_validate_clean_vault_exit_0(self, tmp_path):
        from contextos.scaffolder import validate_vault
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "good.md").write_text(
            "---\nproject: test\ntype: architecture\nstatus: approved\nupdated_at: 2026-01-01\ntags:\n  - arch\n---\n# Good\n"
        )
        result = validate_vault(vault)
        assert result["errors"] == []

    def test_validate_bad_vault_has_errors(self, tmp_path):
        from contextos.scaffolder import validate_vault
        vault = tmp_path / "vault"
        vault.mkdir()
        (vault / "missing.md").write_text("# No frontmatter")
        result = validate_vault(vault)
        assert len(result["errors"]) > 0

    def test_validate_reports_all_files(self, tmp_path):
        from contextos.scaffolder import validate_vault
        vault = tmp_path / "vault"
        vault.mkdir()
        for i in range(5):
            (vault / f"doc{i}.md").write_text(
                f"---\nproject: test\ntype: note\nstatus: draft\nupdated_at: 2026-01-01\ntags:\n  - t\n---\n# Doc {i}\n"
            )
        result = validate_vault(vault)
        assert result["total"] == 5
        assert result["valid"] == 5
