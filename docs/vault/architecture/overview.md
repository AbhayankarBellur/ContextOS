---
project: contextos
type: architecture
status: approved
owner: core-team
updated_at: 2026-06-03
tags:
  - architecture
  - overview
  - layers
---

# ContextOS System Architecture

## Three-Layer Design

ContextOS is intentionally a three-layer system. Each layer has a single responsibility.

### Layer 1 — Vault (Filesystem)
Plain Markdown files with YAML frontmatter. Organised into typed folders. Human-readable without ContextOS installed. The vault is the source of truth — ContextOS never writes to it.

### Layer 2 — Index (Local Process)
- `embedder.py` — sentence-transformers BAAI/bge-small-en-v1.5 (384-dim, CPU)
- `store.py` — LanceDB embedded vector store in `.contextos/lancedb/`
- `graph.py` — NetworkX directed graph in `.contextos/graph/graph.json`
- `chunker.py` — LangChain MarkdownHeaderTextSplitter at H1/H2/H3

### Layer 3 — API (localhost only)
FastAPI server bound to `127.0.0.1` only. Never exposes to network. Agents call this to retrieve context, search documents, and traverse the knowledge graph.

## Module Dependency Order

```
schema.py → config.py → vault.py → chunker.py → embedder.py
→ store.py → graph.py → memory.py → retrieval.py → auth.py → api.py → cli.py
```

Imports must always flow in this direction. Never import cli.py from api.py, for example.

## Key Design Constraints

- `host='127.0.0.1'` hardcoded in `api.py` — never `0.0.0.0`
- `local_files_only=True` after first model download
- All file paths use `pathlib.Path` — never `os.path`
- Index is rebuilt from vault, never from itself
- `.contextos/` is ephemeral — deletable and rebuildable at any time
