# Changelog

All notable changes to ContextOS are documented here.
This project follows [Semantic Versioning](https://semver.org/).

---

## [1.5.0rc1] — 2026-06-04

### Added — Production Maturity

- **E2E test suite** (`tests/test_e2e.py`) — 29 tests covering full pipeline, incremental index, API auth flow, CLI commands, BM25 cache, batch delete, watch mode
- **BM25 disk cache** — index built at `context index` time, pickled to `.contextos/cache/bm25.pkl`, loaded on first query. Eliminates per-query corpus rebuild
- **Batch delete** — re-index uses `doc_id IN (...)` instead of N individual deletes
- **Configurable embedding dimension** — `embedding_dim: 384` in config; auto-detected from loaded model
- **Path containment check** — `context read` validates `is_relative_to()` against vault roots

### Fixed

- `--watch` mode: `cmd_serve` now uses `try/finally` to stop watcher on shutdown
- `embedder.py`: `get_embedding_dimension()` FutureWarning fixed with proper fallback
- Bare `except: pass` eliminated — all silent failures now log at `debug` level

---

## [1.4.1] — 2026-06-04

### Fixed — Audit-Driven Bug Fixes

- **CRITICAL**: `api.py require_scope()` infinite recursion at import time — inner `_check` now depends on `require_token`, not `require_scope`
- **HIGH**: `retrieval.py assemble_context()` now uses `_rrf_score` (hybrid) correctly, not stale `_distance`
- **HIGH**: `vault._ingest_document()` injects `project_name` from caller — PDF/DOCX/PPTX no longer get `project: unknown`
- **MEDIUM**: `auth.check_rate_limit()` merge-write — no longer overwrites `request_count`
- **MEDIUM**: `memory.get_projects_breakdown()` single table scan — eliminated N+1 LanceDB queries
- **MEDIUM**: `watcher.py` now watches `.pdf`, `.docx`, `.pptx` in addition to `.md`
- **MEDIUM**: `mcp_server._mcp_cfg` cached at module level — not reloaded per tool call
- **MEDIUM**: `store.hybrid_search()` returns vector results when BM25 returns empty

### Added

- `schema.py SearchRequest/ContextRequest`: `use_hybrid` and `hybrid_alpha` fields exposed on API
- `config.py`: `hybrid_search` and `hybrid_alpha` configurable in `config.yaml`
- `eval/contextos-questions.json` — 8 golden questions for ContextOS self-evaluation

---

## [1.4.0rc1] — 2026-06-04

### Added — Hybrid Search, Multi-format Ingestors, Evaluator, One-command Bootstrap

- **Hybrid Search** — BM25 + vector + Reciprocal Rank Fusion. `alpha=0.7` default. 30-50% better retrieval for exact terms
- **PDF ingestor** — `pymupdf` page-by-page extraction
- **DOCX ingestor** — `python-docx` headings/tables/bold/italic → Markdown
- **PPTX ingestor** — `python-pptx` slides + speaker notes
- **Retrieval evaluator** — Hit Rate @K, MRR, avg score, latency. `context eval` CLI
- **`context start`** — one-command bootstrap: init + scaffold + import + index + token + serve
- **MCP tool scope enforcement** — `CONTEXTOS_TOKEN` validated per tool call
- ADR-004 (hybrid search), ADR-005 (ingestors)

---

## [1.3.0rc1] — 2026-06-03

### Added — Auth Scopes, Logging, Cache, Plugins, Scaffolding, CI

- **Token scopes**: `read | write | admin` with hierarchical enforcement
- **Token expiry** and **rate limiting** (1000 req/min sliding window)
- **Structured logging**: `app.jsonl`, `slow.jsonl`, `audit.jsonl` with rotation
- **Context response cache**: LRU, TTL=5min, invalidated on index
- **Plugin system**: `~/.contextos/plugins/`, PyPI `entry_points`, `context plugin install`
- **Vault scaffolder**: `default`, `microservice`, `api-first` templates
- **CI commands**: `context ci check`, `context ci index`
- API: `/metrics`, `/audit`, `X-Request-ID` headers, `require_scope` middleware

---

## [1.2.0rc1] — 2026-06-03

### Added — Session Memory, Connectors, TUI Dashboard

- **Session manager**: create, event, end, summary, vault export
- **Connectors**: GitHub Issues/Wiki, OpenAPI spec, JSON/YAML/TOML
- **Textual TUI dashboard**: `context dashboard` — live 4-panel system monitor
- **`context export`** — vault to single Markdown or JSON
- API: `/session/*`, `/pull`

---

## [1.1.0rc1] — 2026-06-03

### Added — Performance + Integration

- **Incremental index** — content-hash change detection, skip unchanged docs
- **MCP server** — 6 native tools (stdio transport)
- **Symbol index** — Python AST + JS/TS regex extraction
- **Smart compression** — sumy TF-IDF extractive, no LLM
- **Live watch mode** — watchfiles per-file re-index
- `context context`, `context diff`, `context projects`, `context symbols`, `context setup`
- Agent templates: `.cursorrules`, `mcp.json`, `.continue/config.json`, copilot instructions

---

## [1.0.0rc1] — 2026-06-03

### Initial Release

- Core 3-layer architecture: Vault → Index → API
- FastAPI server bound exclusively to `127.0.0.1`
- BAAI/bge-small-en-v1.5 embeddings (384-dim, local CPU)
- LanceDB vector store
- NetworkX knowledge graph
- 15 CLI commands with Rich UI
- Token authentication (SHA-256 hash, never plaintext)
- Memory management (purge, archive, reset)
- Kiro pre-task hook
- Self-documenting vault (`docs/vault/`)
- Example project vault (`examples/my-project/`)
- 15 smoke tests
