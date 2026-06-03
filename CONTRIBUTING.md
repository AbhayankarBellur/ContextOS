# Contributing to ContextOS

Thank you for your interest in contributing. ContextOS is an enterprise open-source project. All contributions must maintain the core design principles — especially the zero-network-at-runtime guarantee.

---

## Quick Start for Contributors

```bash
git clone https://github.com/AbhayankarBellur/ContextOS.git
cd ContextOS
pip install -e ".[dev]"
context init
context import docs/vault
context index
```

---

## Development Setup

### Requirements
- Python 3.11+
- pip

### Install with dev dependencies
```bash
pip install -e ".[dev]"
```

### Run the CLI
```bash
context --help
context doctor    # validate your setup
```

### Run tests
```bash
pytest tests/ -v
```

---

## Architecture Rules (Non-Negotiable)

These rules apply to every pull request. PRs that violate them will not be merged.

| Rule | Requirement |
|---|---|
| API binding | `host='127.0.0.1'` only — never `0.0.0.0` |
| Network calls | Zero external calls at runtime |
| Paths | `pathlib.Path` only — never `os.path` |
| Vault files | Read-only — ContextOS never modifies source documents |
| Token storage | SHA-256 hash only — raw value never persisted |
| Data models | All Pydantic v2 models in `contextos/schema.py` |
| UI output | Rich only — no manual ANSI, no `print()` outside `ui.py` |

---

## File Structure

```
contextos/
  schema.py      ← All Pydantic models (source of truth)
  config.py      ← pydantic-settings Config
  vault.py       ← Filesystem scanner + frontmatter parser
  chunker.py     ← MarkdownHeaderTextSplitter
  embedder.py    ← sentence-transformers wrapper
  store.py       ← LanceDB vector store
  graph.py       ← NetworkX knowledge graph
  memory.py      ← Disk management engine
  retrieval.py   ← Full retrieval pipeline
  auth.py        ← Token generation + validation
  api.py         ← FastAPI server (127.0.0.1 only)
  cli.py         ← Typer CLI (all commands)
  ui.py          ← Rich UI theme + shared components

docs/vault/      ← ContextOS's own knowledge vault
examples/        ← Example vaults for testing
tests/           ← Test suite
```

**Dependency order must be respected.** Never import `cli.py` from `api.py`. Never import `api.py` from `retrieval.py`. See `AGENTS.md` for the full dependency graph.

---

## Pull Request Checklist

- [ ] `pip install -e .` succeeds cleanly
- [ ] `context doctor` reports all checks passing
- [ ] `context index` runs fully offline (after first model download)
- [ ] `context search "test"` returns results
- [ ] No new external network calls introduced
- [ ] All new data models added to `schema.py`
- [ ] All new CLI commands follow the UI spec in `ui.py`
- [ ] `AGENTS.md` updated if API surface changed

---

## Commit Message Format

```
type: short description

Types: feat | fix | docs | refactor | test | chore
```

Examples:
```
feat: add POST /grep endpoint for codebase search
fix: handle missing frontmatter on vault documents
docs: update AGENTS.md with memory management commands
```

---

## Versioning

ContextOS follows semantic versioning. Version is set in `pyproject.toml` and `contextos/__init__.py`.

| Version | Scope |
|---|---|
| v1.0.x | Bug fixes |
| v1.1.x | New endpoints, new CLI commands |
| v1.2.x | New retrieval modes (GraphRAG, symbol search) |
| v2.0.0 | Breaking changes (new schema, protocol changes) |

---

## Reporting Issues

Use GitHub Issues. Include:
- Output of `context doctor`
- OS and Python version
- Exact command and error output

---

*ContextOS — Local-first. Agent-native. Enterprise-grade.*
