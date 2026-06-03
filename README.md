# ContextOS

**Local-first knowledge OS for AI coding agents.**

A 100% local, filesystem-native vault that gives AI agents structured, searchable project memory — architecture decisions, domain models, workflows, and sprint context — via a localhost-only HTTP API.

Zero cloud. Zero tracking. Works fully offline after first model download.

---

## Quick Start

```bash
pip install -e .

# 1. Initialize
context init

# 2. Register your Markdown vault
context import ./my-project

# 3. Build the index (downloads ~130MB model once, then fully offline)
context index

# 4. Search
context search "payment retry logic"

# 5. Start the API server
context serve
```

---

## CLI Commands

| Command | Description |
|---|---|
| `context init` | Initialize `.contextos/` in current directory |
| `context import <path>` | Register a Markdown vault |
| `context index` | Build vector index + knowledge graph |
| `context search "<query>"` | Semantic search with scores |
| `context serve` | Start API server on `127.0.0.1:8080` |
| `context status` | Index health and server status |
| `context graph` | Show knowledge graph summary |
| `context grep "<pattern>"` | Fast regex search across codebase |
| `context read <file>` | Read file with optional line range |
| `context tree` | Project directory tree |
| `context changelog` | Recent git commits |
| `context token create <name>` | Generate API token |
| `context token list` | List all tokens |
| `context token revoke <id>` | Revoke a token |
| `context cache ls` | List cached files |
| `context cache clear` | Clear file cache |

---

## API Endpoints

Server runs at `http://127.0.0.1:8080`. All endpoints require `Authorization: Bearer <token>` except `/health`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Server health (no auth) |
| POST | `/search` | Semantic document search |
| POST | `/context` | Assembled agent context block |
| GET | `/documents` | List indexed documents |
| GET | `/graph` | Full knowledge graph |

### Agent Usage

```bash
# Get a context block for your task
curl -X POST http://127.0.0.1:8080/context \
  -H "Authorization: Bearer $CONTEXTOS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "implement booking cancellation", "project": "my-project", "max_tokens": 4000}'

# Search for specific docs
curl -X POST http://127.0.0.1:8080/search \
  -H "Authorization: Bearer $CONTEXTOS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "payment retry", "project": "my-project", "limit": 5}'
```

---

## Vault Structure

```
my-project/
  product/          # Vision, requirements, roadmap
  architecture/     # System architecture docs
  domain/           # Domain models (one file per entity)
  decisions/        # ADRs (Architecture Decision Records)
  workflows/        # Process flows
  context/          # Current sprint, backlog, todo
```

Every file uses YAML frontmatter:

```yaml
---
project: my-project
type: architecture       # architecture|adr|domain|workflow|product|context|note
domain: booking          # optional
status: approved         # draft|approved|deprecated
owner: engineering
updated_at: 2026-06-01
tags:
  - booking
  - api
---
```

---

## Kiro Integration

A pre-task hook is included at `.kiro/hooks/contextos-prefetch.json`. It automatically fetches relevant context before every Kiro task.

Setup:
```bash
context token create kiro
export CONTEXTOS_TOKEN=ctx_<your-token>
context serve  # keep running in background
```

---

## Claude Code Integration

Add to `CLAUDE.md` in your project root:

```markdown
## Project Memory

Before starting any task, retrieve context from ContextOS:

curl -s -X POST http://127.0.0.1:8080/context \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"query": "<task description>", "project": "<project-name>"}'
```

---

## Architecture

```
Layer 1 — Vault       Plain Markdown files with YAML frontmatter
Layer 2 — Index       sentence-transformers + LanceDB + NetworkX graph
Layer 3 — API         FastAPI on 127.0.0.1:8080 (localhost only)
```

**Tech stack:** Python 3.11+ · FastAPI · LanceDB · BAAI/bge-small-en-v1.5 · NetworkX · Typer · Rich

**Constraints:**
- API binds only to `127.0.0.1` — never `0.0.0.0`
- No external API calls at runtime
- All paths use `pathlib.Path`
- Vault documents are read-only — ContextOS never modifies source files

---

*v1.0.0-rc1 — See PRD and Appendix A for full specification*
