---
project: contextos
type: context
status: approved
owner: core-team
updated_at: 2026-06-04
tags:
  - sprint
  - current
---

# Current State — ContextOS v1.4.0-rc1

## Completed — v1.0 (Foundation)

- [x] schema.py, config.py, vault.py, chunker.py, embedder.py, store.py, graph.py
- [x] retrieval.py — priority rerank, token budget, context assembly
- [x] auth.py — ctx_ tokens, SHA-256 hash only, never plaintext
- [x] api.py — FastAPI 127.0.0.1 only, Bearer token auth
- [x] memory.py — disk breakdown, purge, archive, reset
- [x] cli.py — 15 commands, premium Rich UI
- [x] AGENTS.md, CLAUDE.md, Kiro hook, docs/vault

## Completed — v1.1 (Performance + Integration)

- [x] Incremental index — content hash skip (10-100x faster re-index)
- [x] MCP server — 6 native tools, stdio transport
- [x] Symbol index — Python AST + JS/TS regex (190 symbols, 17 files)
- [x] Smart compression — sumy TF-IDF, no LLM
- [x] Live watch mode — watchfiles per-file re-index (now routes PDF/DOCX/PPTX)
- [x] context context, context diff, context symbols, context mcp, context setup

## Completed — v1.2 (Enterprise Features)

- [x] session.py — full agent session lifecycle, vault export
- [x] connectors/ — github, openapi, json (pluggable BaseConnector)
- [x] dashboard.py — Textual TUI, live-refresh, inline search
- [x] context pull, context export, context dashboard
- [x] API: /session/*, /pull endpoints

## Completed — v1.3 (Auth, Logging, Cache, Plugins, Scaffolding, CI)

- [x] Token scopes: read | write | admin, expiry, rate limiting (1000 req/min)
- [x] Structured logger: app.jsonl, slow.jsonl, audit.jsonl, log rotation
- [x] Context response cache: LRU, TTL=5min, cache invalidated on index
- [x] Plugin system: ~/.contextos/plugins/, entry_points, context plugin install
- [x] Vault scaffolder: default, microservice, api-first templates + context vault init
- [x] CI commands: context ci check, context ci index (JSON output, exit 0/1)
- [x] API: /metrics, /audit, X-Request-ID headers, require_scope middleware

## Completed — v1.4 (Hybrid Search, Ingestors, Evaluator, One-command Bootstrap)

- [x] Hybrid search: BM25 + vector + RRF (alpha=0.7 default)
- [x] PDF ingestor (pymupdf), DOCX ingestor (python-docx), PPTX ingestor (python-pptx)
- [x] Retrieval evaluator: Hit Rate @K, MRR, avg score, latency
- [x] context start — one-command bootstrap (init + scaffold + import + index + token + serve)
- [x] context eval — CLI evaluation against golden question sets
- [x] MCP tool scope enforcement (CONTEXTOS_TOKEN per call)
- [x] ADR-004 (hybrid search), ADR-005 (ingestors)
- [x] eval/questions.json.example, eval/contextos-questions.json

## Bug Fixes Applied (v1.4.1)

- [x] CRITICAL: api.py require_scope() infinite recursion fixed
- [x] HIGH: retrieval.py assemble_context() now uses _rrf_score not _distance
- [x] HIGH: vault.py _ingest_document() scope guard fixed, project injected correctly
- [x] MEDIUM: auth.py check_rate_limit() merge-write (no more double-write race)
- [x] MEDIUM: memory.py get_projects_breakdown() single table scan (no N+1)
- [x] MEDIUM: watcher.py watches .pdf/.docx/.pptx, routes via ingestor
- [x] MEDIUM: mcp_server.py config cached at module level (not per-call)
- [x] MEDIUM: config.py hybrid_search + hybrid_alpha now configurable
- [x] HIGH: schema.py SearchRequest/ContextRequest expose use_hybrid + hybrid_alpha

## CLI Command Count — 30 commands

init, import, index, search, serve, status, graph, grep, read, tree,
changelog, doctor, context, diff, projects, about, symbols, mcp, setup,
start, eval, pull, export, dashboard, logs, token×3, memory×6,
cache×3, session×5, vault×3, plugin×2, ci×2

## API Endpoint Count — 20 endpoints

/health, /search, /context, /graph, /documents, /watcher, /metrics, /audit,
/session/start, /session/:id/event, /session/:id/end, /session/last,
/session/active, /pull
