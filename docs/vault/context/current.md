---
project: contextos
type: context
status: approved
owner: core-team
updated_at: 2026-06-03
tags:
  - sprint
  - current
---

# Current State — ContextOS v1.0.0-rc1

## Completed

- [x] Full schema.py — all Pydantic v2 models
- [x] config.py — pydantic-settings, .contextos/ directory management
- [x] vault.py — filesystem scanner, frontmatter parser, registry
- [x] chunker.py — MarkdownHeaderTextSplitter, min/max token merging
- [x] embedder.py — BAAI/bge-small-en-v1.5, local cache, offline after first run
- [x] store.py — LanceDB upsert, cosine search, metadata pre-filter
- [x] graph.py — NetworkX builder, save/load JSON, 1-hop expansion
- [x] retrieval.py — full pipeline, priority rerank, token budget, context assembly
- [x] auth.py — ctx_ tokens, SHA-256 hash, validate, revoke, list
- [x] api.py — FastAPI, 127.0.0.1 only, /health /search /context /documents /graph
- [x] memory.py — disk breakdown, purge, archive, reset, clear embeddings
- [x] cli.py — 15 commands with premium Rich UI
- [x] AGENTS.md — single source of truth for AI agents
- [x] CLAUDE.md — Claude Code integration template
- [x] Kiro hook — .kiro/hooks/contextos-prefetch.json
- [x] docs/vault — self-documenting knowledge vault

## Active Focus

- Memory management CLI commands (context memory *)
- CLI UI/UX polish to match Claude Code / Vercel CLI quality
- context doctor command for setup validation
- Git repo polish for public release

## Known Issues

- Port 8080 blocked on some Windows machines — default changed to 8765 recommended
- LanceDB `indexed` count returns 0 from /health (lazy load) — fix: eager init on serve startup
- Windows path separators in filepaths need normalisation for display

## Architecture Decisions in Flight

- Consider making default port 8765 to avoid conflicts with common dev servers
- Memory archive format: currently JSON export — consider keeping embeddings in archive for instant restore
