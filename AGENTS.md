# ContextOS — Agent Rulebook & Operating Manual

## What is ContextOS?

ContextOS is a 100% local, filesystem-native knowledge operating system for software projects. It is both:
1. **A tool you USE** — to give yourself persistent project memory across sessions
2. **A codebase you MAINTAIN** — this repo is the ContextOS source code

As an AI coding agent working in this repo, you must use ContextOS itself while you build it (dogfooding).

---

## Quick Start for Agents (Read First)

### Step 1 — Install
```bash
pip install -e .
```

### Step 2 — Initialize in this repo
```bash
context init
```

### Step 3 — Import the knowledge vault
```bash
context import ./docs/vault
```

### Step 4 — Index (first run downloads ~130MB model, then fully offline)
```bash
context index
```

### Step 5 — Create your session token
```bash
context token create agent-session
# Copy the printed ctx_ token — shown once only
export CONTEXTOS_TOKEN=ctx_<your-token>
```

### Step 6 — Start the server (keep running in background)
```bash
context serve --port 8765
```

### Step 7 — Verify
```bash
curl http://127.0.0.1:8765/health
```

---

## Using ContextOS FROM Other Project Folders

You do NOT need to be in the ContextOS repo directory to use it. From any project folder:

```bash
# The server is already running at 127.0.0.1:8765
# Just call the API with your token

# Get context before starting a task
curl -s -X POST http://127.0.0.1:8765/context \
  -H "Authorization: Bearer $CONTEXTOS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "YOUR TASK DESCRIPTION", "project": "contextos"}'

# Search for specific knowledge
curl -s -X POST http://127.0.0.1:8765/search \
  -H "Authorization: Bearer $CONTEXTOS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"query": "how does chunking work", "project": "contextos", "limit": 5}'
```

**The graph updates automatically** when you run `context index` from the ContextOS repo directory. Run it after significant code changes to keep the knowledge graph current.

---

## Agent Workflow Per Session

Follow this workflow EVERY session without exception:

### Before Starting Any Task
```
1. Check server: curl http://127.0.0.1:8765/health
2. If not running: cd /path/to/contextos && context serve --port 8765 &
3. Fetch context: POST /context with your task description
4. Read the returned context block before writing any code
```

### During a Task
```
- Use context grep "<pattern>" to find relevant code fast (faster than reading files)
- Use context read <file> --lines X:Y to read specific sections
- Use POST /search for semantic lookups ("how does X work")
- Never re-explain architecture you can retrieve — ask the server
```

### After Completing a Task
```
1. Run: context index  (update the knowledge graph with your changes)
2. Update relevant vault docs if architecture changed
3. If you added a new module: add a corresponding doc to docs/vault/architecture/
```

---

## Architecture Rules (Non-Negotiable)

These rules govern every line of code in this repo. Violating them breaks the system.

### 1. API Server MUST bind to 127.0.0.1 only
```python
# CORRECT
uvicorn.run(app, host="127.0.0.1", port=port)

# FORBIDDEN — will be rejected in code review
uvicorn.run(app, host="0.0.0.0", port=port)
```

### 2. No external network calls at runtime
```python
# FORBIDDEN at runtime
import requests
requests.get("https://api.openai.com/...")  # Never

# The embedding model must use local_files_only=True after first download
SentenceTransformer(model_name, local_files_only=True)  # Correct
```

### 3. All paths use pathlib.Path
```python
# CORRECT
from pathlib import Path
config_path = Path.cwd() / ".contextos" / "config.yaml"

# FORBIDDEN
import os
config_path = os.path.join(os.getcwd(), ".contextos", "config.yaml")
```

### 4. Vault documents are read-only
```python
# ContextOS NEVER writes to vault documents
# All writes go to .contextos/ only
# Never: open(vault_path / "file.md", "w")
```

### 5. Token raw values are never stored
```python
# Only SHA-256 hash is persisted
# Raw token printed once at creation, never again
# Never: json.dump({"token": raw_token}, f)
# Always: json.dump({"hash": sha256(raw_token)}, f)
```

### 6. All Pydantic models live in schema.py
```python
# New data models MUST be added to contextos/schema.py
# Never create ad-hoc dicts where a Pydantic model should exist
# Import from contextos.schema — never duplicate model definitions
```

---

## File Generation Order (Strict — Avoids Import Errors)

When adding new modules, always respect this dependency order:

```
1. contextos/schema.py      ← Pydantic models (no dependencies)
2. contextos/config.py      ← Config (depends on schema)
3. contextos/vault.py       ← Filesystem scanner (depends on schema, config)
4. contextos/chunker.py     ← Chunker (depends on schema)
5. contextos/embedder.py    ← Embedder (depends on schema)
6. contextos/store.py       ← LanceDB (depends on schema)
7. contextos/graph.py       ← NetworkX graph (depends on schema)
8. contextos/memory.py      ← Memory manager (depends on config, store, graph)
9. contextos/retrieval.py   ← Retrieval pipeline (depends on all above)
10. contextos/auth.py       ← Token auth (depends on schema)
11. contextos/api.py        ← FastAPI (depends on retrieval, auth)
12. contextos/cli.py        ← CLI (depends on everything)
```

---

## Project Vault Structure

The knowledge vault lives in `docs/vault/`. This is what gets indexed.

```
docs/vault/
  architecture/
    overview.md          ← System architecture (3 layers)
    api.md               ← API endpoint reference
    retrieval.md         ← Retrieval pipeline internals
    storage.md           ← LanceDB + vector store design
  domain/
    document.md          ← Document model
    chunk.md             ← Chunk model
    token.md             ← Token model
    graph.md             ← Graph node/edge models
  decisions/
    ADR-001-lancedb.md
    ADR-002-bge-small.md
    ADR-003-local-only.md
  workflows/
    indexing-flow.md     ← How context index works end-to-end
    search-flow.md       ← How POST /search works
    context-flow.md      ← How POST /context assembles output
  context/
    current.md           ← Updated each sprint with current goals
```

---

## Tech Stack Reference

| Component | Package | Version |
|---|---|---|
| Language | Python | 3.11+ |
| CLI | Typer | 0.12+ |
| UI | Rich | 13.7+ |
| API | FastAPI | 0.111+ |
| Embeddings | sentence-transformers | 3.x |
| Embedding model | BAAI/bge-small-en-v1.5 | local, 384-dim |
| Vector store | LanceDB | 0.6+ |
| Graph | NetworkX | 3.x |
| Config | pydantic-settings | 2.x |
| Models | Pydantic | v2 |

---

## API Quick Reference

All endpoints at `http://127.0.0.1:8765` (or configured port).

```bash
# No auth required
GET  /health

# All others require: Authorization: Bearer ctx_<token>
POST /search          # Semantic document search
POST /context         # Assembled context block for agent
GET  /documents       # List indexed documents
GET  /graph           # Full knowledge graph
POST /grep            # Fast regex codebase search (v1.1)
POST /files/read      # Read file with metadata (v1.1)
GET  /tree            # Project structure (v1.1)
GET  /changelog       # Recent git commits (v1.1)
```

### POST /search request shape
```json
{
  "query": "how does payment retry work",
  "project": "contextos",
  "type": "architecture",
  "domain": null,
  "limit": 5,
  "include_graph": false
}
```

### POST /context request shape
```json
{
  "query": "implement the memory manager",
  "project": "contextos",
  "max_tokens": 4000,
  "priority_order": ["context", "adr", "architecture", "domain", "workflow", "product"]
}
```

---

## Memory Management

When disk space is tight or a project is complete, use the memory manager:

```bash
# See disk usage breakdown
context memory status

# List all projects with sizes
context memory projects

# Archive a project (compresses index, keeps vault)
context memory archive <project-name>

# Purge a project's index (keeps vault, forces re-index on next use)
context memory purge <project-name>

# Clear embedding cache (re-downloads on next index)
context memory clear-embeddings

# Full reset of .contextos/ (keeps vault, wipes all indexes)
context memory reset
```

---

## Common Patterns

### Add a new CLI command
1. Add function to `contextos/cli.py` with `@app.command("name")`
2. Import dependencies lazily inside the function (not at module top)
3. Follow the UI spec: banner → status → rich panel result → next action hint
4. Add the command to `AGENTS.md` API reference

### Add a new API endpoint
1. Add route to `contextos/api.py`
2. Add request/response models to `contextos/schema.py`
3. Implement logic in the appropriate module (not inline in api.py)
4. Add to API reference in `AGENTS.md`

### Update the knowledge graph
After any significant change:
```bash
context index    # rebuilds chunks, embeddings, graph
context status   # verify document count increased
```

---

## Environment Variables

```bash
CONTEXTOS_TOKEN=ctx_<token>    # Bearer token for API auth
CONTEXTOS_PORT=8765            # Port override (default: 8080)
CONTEXTOS_LOG_LEVEL=info       # debug | info | warning
```

Add to your shell profile (`~/.bashrc`, `~/.zshrc`, `~/.profile`):
```bash
export CONTEXTOS_TOKEN=ctx_<your-token>
export CONTEXTOS_PORT=8765
```

---

## What Makes ContextOS Different

| Problem | ContextOS Solution |
|---|---|
| Agent forgets architecture between sessions | Persistent vault indexed and searchable |
| Context window bloat from re-explaining | `/context` endpoint returns only relevant chunks |
| Can't search codebase fast | `context grep` with ripgrep, sub-100ms |
| Need to read file sections | `context read file.py --lines 40:80` |
| Token waste on unchanged context | Content-hash change detection — only re-indexes changed files |
| Cloud lock-in | 100% local, zero network at runtime |

---

*ContextOS AGENTS.md — v1.0.0-rc1 — Keep this file updated as the system evolves.*
